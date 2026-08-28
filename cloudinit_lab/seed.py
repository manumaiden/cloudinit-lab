"""Rendering of cloud-init NoCloud seed files and seed.iso building."""

import subprocess
import uuid
from pathlib import Path

import yaml

from cloudinit_lab.netconfig import render_dns_workaround_runcmd, render_network_config
from cloudinit_lab.scenarios import Scenario


def render_meta_data(hostname: str, instance_id: str | None = None) -> tuple[str, str]:
    instance_id = instance_id or str(uuid.uuid4())
    content = f"instance-id: {instance_id}\nlocal-hostname: {hostname}\n"
    return content, instance_id


def render_user_data(scenario: Scenario) -> str:
    runcmd_lines = render_dns_workaround_runcmd(scenario.nics)
    cloud_config = {
        "users": [{
            "name": scenario.user,
            "shell": "/bin/bash",
            "lock_passwd": False,
            "groups": "wheel",
            "sudo": "ALL=(ALL:ALL) NOPASSWD:ALL",
        }],
        "chpasswd": {"list": f"{scenario.user}:{scenario.password}\n", "expire": False},
        "ssh_pwauth": True,
    }
    if runcmd_lines:
        cloud_config["runcmd"] = runcmd_lines
    cloud_config["final_message"] = "cloud-init configuration has been completed!!"
    body = yaml.safe_dump(cloud_config, sort_keys=False)
    return f"#cloud-config\n{body}"


def write_seed_files(workdir: Path, scenario: Scenario) -> str:
    """Render meta-data/user-data/network-config into workdir. Returns instance_id."""
    workdir.mkdir(parents=True, exist_ok=True)
    meta_data, instance_id = render_meta_data(scenario.hostname)
    (workdir / "meta-data").write_text(meta_data)
    (workdir / "user-data").write_text(render_user_data(scenario))
    (workdir / "network-config").write_text(render_network_config(scenario.nics))
    return instance_id


def build_seed_iso(workdir: Path, output_path: Path) -> None:
    """Package the three seed files in workdir into a NoCloud seed.iso."""
    subprocess.run(
        [
            "genisoimage", "-output", str(output_path), "-volid", "cidata",
            "-joliet", "-rock", "user-data", "meta-data", "network-config",
        ],
        cwd=workdir, check=True, capture_output=True,
    )
