import pytest
import yaml

from cloudinit_lab.netconfig import NicConfig, render_network_config


def test_single_dhcp_nic():
    nics = [NicConfig(name="eth0", mode="dhcp")]
    parsed = yaml.safe_load(render_network_config(nics))
    assert parsed == {
        "network": {
            "version": 2,
            "ethernets": {"eth0": {"dhcp4": True}},
        }
    }


def test_static_nic_with_dns():
    nics = [NicConfig(
        name="eth0", mode="static",
        address="192.168.122.50/24", gateway="192.168.122.1",
        dns=["8.8.8.8", "1.1.1.1"], dns_search=["example.com"],
    )]
    parsed = yaml.safe_load(render_network_config(nics))
    eth0 = parsed["network"]["ethernets"]["eth0"]
    assert eth0["addresses"] == ["192.168.122.50/24"]
    assert eth0["routes"] == [{"to": "0.0.0.0/0", "via": "192.168.122.1"}]
    assert eth0["nameservers"] == {
        "addresses": ["8.8.8.8", "1.1.1.1"],
        "search": ["example.com"],
    }


def test_static_nic_without_gateway_has_no_routes_key():
    nics = [NicConfig(name="eth0", mode="static", address="10.0.0.5/24")]
    parsed = yaml.safe_load(render_network_config(nics))
    assert "routes" not in parsed["network"]["ethernets"]["eth0"]


def test_static_nic_without_dns_has_no_nameservers_key():
    nics = [NicConfig(name="eth0", mode="static", address="10.0.0.5/24", gateway="10.0.0.1")]
    parsed = yaml.safe_load(render_network_config(nics))
    assert "nameservers" not in parsed["network"]["ethernets"]["eth0"]


def test_multi_nic_mixed_modes():
    nics = [
        NicConfig(name="eth0", mode="dhcp"),
        NicConfig(name="eth1", mode="static", address="10.10.10.5/24", gateway="10.10.10.1"),
    ]
    parsed = yaml.safe_load(render_network_config(nics))
    ethernets = parsed["network"]["ethernets"]
    assert set(ethernets.keys()) == {"eth0", "eth1"}
    assert ethernets["eth0"] == {"dhcp4": True}
    assert ethernets["eth1"]["addresses"] == ["10.10.10.5/24"]


def test_unknown_mode_raises():
    nics = [NicConfig(name="eth0", mode="bogus")]
    with pytest.raises(ValueError, match="Unknown NIC mode"):
        render_network_config(nics)


from cloudinit_lab.netconfig import render_dns_workaround_runcmd


def test_dhcp_nic_with_dns_override_generates_nmcli_lines():
    nics = [NicConfig(
        name="enp1s0", mode="dhcp",
        dns=["8.8.8.8", "1.1.1.1"], dns_search=["tst.example.com"],
        ignore_auto_dns=True, dhcp_hostname="dummyname.tst.example.com",
    )]
    lines = render_dns_workaround_runcmd(nics)
    assert lines == [
        'nmcli con mod "cloud-init enp1s0" connection.interface-name ""',
        'nmcli con mod "cloud-init enp1s0" match.interface-name "en*"',
        'nmcli con mod "cloud-init enp1s0" ipv4.ignore-auto-dns yes',
        'nmcli con mod "cloud-init enp1s0" ipv4.dns "8.8.8.8 1.1.1.1"',
        'nmcli con mod "cloud-init enp1s0" ipv4.dns-search "tst.example.com"',
        'nmcli con mod "cloud-init enp1s0" ipv4.dhcp-hostname "dummyname.tst.example.com"',
        'nmcli con up "cloud-init enp1s0"',
    ]


def test_dhcp_nic_without_dns_fields_generates_no_lines():
    nics = [NicConfig(name="eth0", mode="dhcp")]
    assert render_dns_workaround_runcmd(nics) == []


def test_static_nic_never_generates_runcmd_lines():
    nics = [NicConfig(
        name="eth0", mode="static", address="10.0.0.5/24",
        gateway="10.0.0.1", dns=["8.8.8.8"],
    )]
    assert render_dns_workaround_runcmd(nics) == []


def test_multiple_dhcp_nics_generate_independent_blocks():
    nics = [
        NicConfig(name="eth0", mode="dhcp", dns=["8.8.8.8"]),
        NicConfig(name="eth1", mode="dhcp", dns=["1.1.1.1"]),
    ]
    lines = render_dns_workaround_runcmd(nics)
    assert lines == [
        'nmcli con mod "cloud-init eth0" connection.interface-name ""',
        'nmcli con mod "cloud-init eth0" match.interface-name "en*"',
        'nmcli con mod "cloud-init eth0" ipv4.dns "8.8.8.8"',
        'nmcli con up "cloud-init eth0"',
        'nmcli con mod "cloud-init eth1" connection.interface-name ""',
        'nmcli con mod "cloud-init eth1" match.interface-name "en*"',
        'nmcli con mod "cloud-init eth1" ipv4.dns "1.1.1.1"',
        'nmcli con up "cloud-init eth1"',
    ]


def test_dhcp_nic_with_dns_override_clears_literal_interface_binding():
    # Regression guard: cloud-init's NM renderer hardcodes
    # connection.interface-name to the netplan id regardless of what the
    # guest's kernel actually names the device (verified live: a scenario
    # named "enp1s0" produced a profile that failed to activate on a real
    # device named "ens2"). The workaround must clear that literal binding
    # and rebind via NM's own match.interface-name glob before activating.
    nics = [NicConfig(name="enp1s0", mode="dhcp", dns=["8.8.8.8"])]
    lines = render_dns_workaround_runcmd(nics)
    assert lines[0] == 'nmcli con mod "cloud-init enp1s0" connection.interface-name ""'
    assert lines[1] == 'nmcli con mod "cloud-init enp1s0" match.interface-name "en*"'
    assert lines[-1] == 'nmcli con up "cloud-init enp1s0"'
