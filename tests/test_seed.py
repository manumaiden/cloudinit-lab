import shutil
import uuid

import pytest
import yaml

from cloudinit_lab.netconfig import NicConfig
from cloudinit_lab.scenarios import Scenario
from cloudinit_lab.seed import (
    build_seed_iso,
    render_meta_data,
    render_user_data,
    write_seed_files,
)


def test_render_meta_data_generates_uuid_when_not_given():
    content, instance_id = render_meta_data("test-host")
    assert f"local-hostname: test-host" in content
    assert f"instance-id: {instance_id}" in content
    uuid.UUID(instance_id)  # raises if not a valid UUID


def test_render_meta_data_uses_given_instance_id():
    content, instance_id = render_meta_data("test-host", instance_id="fixed-id-123")
    assert instance_id == "fixed-id-123"
    assert "instance-id: fixed-id-123" in content


def test_render_user_data_dhcp_with_overrides_includes_runcmd():
    scenario = Scenario(
        hostname="h", user="manu", password="Test1234!",
        nics=[NicConfig(name="eth0", mode="dhcp", dns=["8.8.8.8"])],
    )
    content = render_user_data(scenario)
    assert content.startswith("#cloud-config\n")
    body = yaml.safe_load(content.removeprefix("#cloud-config\n"))
    assert body["users"][0]["name"] == "manu"
    assert body["chpasswd"]["list"] == "manu:Test1234!\n"
    assert "runcmd" in body
    assert 'nmcli con mod "cloud-init eth0" ipv4.dns "8.8.8.8"' in body["runcmd"]


def test_render_user_data_plain_dhcp_has_no_runcmd():
    scenario = Scenario(
        hostname="h", user="manu", password="Test1234!",
        nics=[NicConfig(name="eth0", mode="dhcp")],
    )
    body = yaml.safe_load(render_user_data(scenario).removeprefix("#cloud-config\n"))
    assert "runcmd" not in body


def test_write_seed_files_creates_three_files_when_network_config_needed(tmp_path):
    scenario = Scenario(
        hostname="h", user="manu", password="Test1234!",
        nics=[NicConfig(name="eth0", mode="dhcp", dns=["8.8.8.8"])],
    )
    workdir = tmp_path / "seed-work"
    instance_id = write_seed_files(workdir, scenario)
    assert (workdir / "meta-data").is_file()
    assert (workdir / "user-data").is_file()
    assert (workdir / "network-config").is_file()
    uuid.UUID(instance_id)


def test_write_seed_files_skips_network_config_for_vanilla_dhcp(tmp_path):
    # Regression guard: an explicit network-config naming an interface that
    # doesn't match the guest's real device leaves it completely
    # unconfigured on renderers with no auto-connect fallback (verified
    # live: systemd-networkd on Debian never got a DHCP lease). Omitting
    # network-config for a NIC that needs no customization lets cloud-init
    # generate its own fallback config from the real discovered interface.
    scenario = Scenario(
        hostname="h", user="manu", password="Test1234!",
        nics=[NicConfig(name="eth0", mode="dhcp")],
    )
    workdir = tmp_path / "seed-work"
    write_seed_files(workdir, scenario)
    assert (workdir / "meta-data").is_file()
    assert (workdir / "user-data").is_file()
    assert not (workdir / "network-config").exists()


def test_write_seed_files_writes_network_config_if_any_nic_is_not_vanilla(tmp_path):
    scenario = Scenario(
        hostname="h", user="manu", password="Test1234!",
        nics=[
            NicConfig(name="eth0", mode="dhcp"),
            NicConfig(name="eth1", mode="static", address="10.10.10.100/24", gateway="10.10.10.1"),
        ],
    )
    workdir = tmp_path / "seed-work"
    write_seed_files(workdir, scenario)
    assert (workdir / "network-config").is_file()


@pytest.mark.skipif(shutil.which("genisoimage") is None, reason="genisoimage not installed")
def test_build_seed_iso_produces_nonempty_iso(tmp_path):
    scenario = Scenario(
        hostname="h", user="manu", password="Test1234!",
        nics=[NicConfig(name="eth0", mode="dhcp")],
    )
    workdir = tmp_path / "seed-work"
    write_seed_files(workdir, scenario)
    iso_path = tmp_path / "seed.iso"
    build_seed_iso(workdir, iso_path)
    assert iso_path.is_file()
    assert iso_path.stat().st_size > 0
