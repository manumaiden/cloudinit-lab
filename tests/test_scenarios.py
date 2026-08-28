import pytest

from cloudinit_lab.netconfig import NicConfig
from cloudinit_lab.scenarios import (
    Scenario,
    ScenarioValidationError,
    load_scenario,
    merge_overrides,
    validate_scenario,
)


def _write(tmp_path, content):
    path = tmp_path / "scenario.yaml"
    path.write_text(content)
    return path


def test_load_valid_dhcp_scenario(tmp_path):
    path = _write(tmp_path, """
hostname: test1
user: manu
password: test-pass
nics:
  - name: eth0
    mode: dhcp
    dns: ["8.8.8.8"]
""")
    scenario = load_scenario(path)
    assert scenario.hostname == "test1"
    assert scenario.user == "manu"
    assert scenario.password == "test-pass"
    assert scenario.nics == [NicConfig(name="eth0", mode="dhcp", dns=["8.8.8.8"])]


def test_load_valid_static_scenario(tmp_path):
    path = _write(tmp_path, """
hostname: test-static
user: manu
password: test-pass
nics:
  - name: eth0
    mode: static
    address: 192.168.122.50/24
    gateway: 192.168.122.1
""")
    scenario = load_scenario(path)
    assert scenario.nics[0].address == "192.168.122.50/24"


def test_static_nic_missing_address_raises(tmp_path):
    path = _write(tmp_path, """
hostname: test1
user: manu
password: test-pass
nics:
  - name: eth0
    mode: static
    gateway: 192.168.122.1
""")
    with pytest.raises(ScenarioValidationError, match="requires 'address'"):
        load_scenario(path)


def test_static_nic_missing_gateway_raises(tmp_path):
    path = _write(tmp_path, """
hostname: test1
user: manu
password: test-pass
nics:
  - name: eth0
    mode: static
    address: 192.168.122.50/24
""")
    with pytest.raises(ScenarioValidationError, match="requires 'gateway'"):
        load_scenario(path)


def test_static_nic_malformed_cidr_raises(tmp_path):
    path = _write(tmp_path, """
hostname: test1
user: manu
password: test-pass
nics:
  - name: eth0
    mode: static
    address: not-an-ip
    gateway: 192.168.122.1
""")
    with pytest.raises(ScenarioValidationError, match="CIDR notation"):
        load_scenario(path)


def test_scenario_with_no_nics_raises(tmp_path):
    path = _write(tmp_path, """
hostname: test1
user: manu
password: test-pass
nics: []
""")
    with pytest.raises(ScenarioValidationError, match="at least one NIC"):
        load_scenario(path)


def test_validate_scenario_unknown_mode_raises():
    scenario = Scenario(
        hostname="test1", user="manu", password="pw",
        nics=[NicConfig(name="eth0", mode="bogus")],
    )
    with pytest.raises(ScenarioValidationError, match="unknown mode"):
        validate_scenario(scenario)


def _base_scenario():
    return Scenario(
        hostname="orig-host", user="manu", password="orig-pass",
        nics=[
            NicConfig(name="eth0", mode="dhcp", dns=["8.8.8.8"]),
            NicConfig(name="eth1", mode="dhcp"),
        ],
    )


def test_merge_overrides_hostname():
    merged = merge_overrides(_base_scenario(), {"hostname": "new-host"})
    assert merged.hostname == "new-host"
    assert merged.user == "manu"


def test_merge_overrides_dns_applies_to_all_nics():
    merged = merge_overrides(_base_scenario(), {"dns": ["1.1.1.1"]})
    assert merged.nics[0].dns == ["1.1.1.1"]
    assert merged.nics[1].dns == ["1.1.1.1"]


def test_merge_overrides_does_not_mutate_original():
    original = _base_scenario()
    merge_overrides(original, {"dns": ["1.1.1.1"]})
    assert original.nics[0].dns == ["8.8.8.8"]


def test_merge_overrides_empty_dict_returns_equivalent_scenario():
    original = _base_scenario()
    merged = merge_overrides(original, {})
    assert merged == original


def test_merge_overrides_revalidates_result():
    # Built directly (bypassing load_scenario's own validation) with a static
    # NIC missing 'gateway' — merge_overrides must still catch it, proving it
    # re-validates the merged result rather than trusting the input as-is.
    invalid_scenario = Scenario(
        hostname="h", user="u", password="p",
        nics=[NicConfig(name="eth0", mode="static", address="10.0.0.5/24")],
    )
    with pytest.raises(ScenarioValidationError, match="requires 'gateway'"):
        merge_overrides(invalid_scenario, {"hostname": "h2"})
