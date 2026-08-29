"""VM lifecycle management: virt-install/virsh wrappers and image catalog."""

import shutil
import subprocess
import sys
import time
import socket
from pathlib import Path

from cloudinit_lab.netconfig import NicConfig
from cloudinit_lab.scenarios import Scenario
from cloudinit_lab.seed import build_seed_iso, write_seed_files

REQUIRED_BINARIES = ["virt-install", "virsh", "qemu-img", "genisoimage"]


def run(cmd, sudo=False, capture=False, check=True):
    if sudo:
        cmd = ["sudo"] + list(cmd)
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, check=check)
    return subprocess.run(cmd, check=check)


def virsh(*args):
    return subprocess.run(["sudo", "virsh"] + list(args), capture_output=True, text=True)


def check_dependencies() -> list[str]:
    return [b for b in REQUIRED_BINARIES if shutil.which(b) is None]


def resolve_image(images_dir: Path, os_name: str, version: str, explicit_src: str | None = None) -> Path:
    if explicit_src:
        path = Path(explicit_src).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")
        return path

    os_dir = images_dir / os_name
    candidates = sorted(os_dir.glob(f"{version}*.qcow2")) if os_dir.is_dir() else []
    if not candidates:
        raise FileNotFoundError(f"No image found for {os_name}/{version} in {os_dir}")
    if len(candidates) > 1:
        raise ValueError(f"Multiple images match {os_name}/{version}, pass --src explicitly: {candidates}")
    return candidates[0]


def list_images(images_dir: Path) -> list[dict]:
    results = []
    if not images_dir.is_dir():
        return results
    for os_dir in sorted(p for p in images_dir.iterdir() if p.is_dir()):
        for img in sorted(os_dir.glob("*.qcow2")):
            stat = img.stat()
            results.append({"os": os_dir.name, "path": img, "size_bytes": stat.st_size})
    return results


def build_virt_install_args(
    name: str, disk_path: Path, iso_path: Path, nics: list[NicConfig], ram: int, vcpus: int
) -> list[str]:
    args = [
        "virt-install",
        "--name", name,
        "--memory", str(ram),
        "--vcpus", str(vcpus),
        "--disk", f"{disk_path},device=disk,bus=virtio,format=qcow2",
        "--disk", f"{iso_path},device=cdrom",
        "--os-variant", "detect=on,require=off",
        "--graphics", "none",
        "--import",
        "--noautoconsole",
    ]
    for _ in nics:
        args += ["--network", "network=default,model=virtio"]
    return args


def _wait_for_ip(name: str, attempts: int = 30, interval: float = 2.0, sleep_fn=time.sleep) -> str | None:
    for _ in range(attempts):
        result = virsh("domifaddr", name, "--source", "lease")
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and "/" in parts[-1]:
                return parts[-1].split("/")[0]
        sleep_fn(interval)
    return None


def _wait_for_ssh_port(ip: str, timeout: int = 90) -> bool:
    deadline = time.monotonic() + timeout
    last_feedback = time.monotonic()
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((ip, 22), timeout=2):
                return True
        except OSError:
            if time.monotonic() - last_feedback >= 10:
                print(f"  ... waiting for sshd on {ip}")
                last_feedback = time.monotonic()
            time.sleep(1)
    return False


def _offer_ssh(ip: str, user: str, password: str) -> None:
    if not sys.stdin.isatty():
        return
    answer = input(
        f"Connect via SSH now? (user: {user}, password: {password}) [Y/n] "
    ).strip().lower()
    if answer not in ("", "y", "yes"):
        return
    if not _wait_for_ssh_port(ip):
        print(f"  Timed out waiting for SSH. Connect manually: ssh {user}@{ip}")
        return
    subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", f"{user}@{ip}"])


def create_vm(
    name: str, image_src: Path, scenario: Scenario, vms_dir: Path,
    ram: int = 2048, vcpus: int = 2,
) -> dict:
    missing = check_dependencies()
    if missing:
        raise RuntimeError(f"Missing required tools: {', '.join(missing)}")

    existing = virsh("dominfo", name)
    if existing.returncode == 0:
        raise RuntimeError(f"A VM named {name!r} already exists")

    vm_dir = vms_dir / name
    vm_dir.mkdir(parents=True, exist_ok=True)
    disk_path = vm_dir / f"{name}.qcow2"
    run(["cp", str(image_src), str(disk_path)], sudo=True)

    rendered_dir = vm_dir / "rendered"
    instance_id = write_seed_files(rendered_dir, scenario)
    iso_path = vm_dir / "seed.iso"
    build_seed_iso(rendered_dir, iso_path)

    args = build_virt_install_args(name, disk_path, iso_path, scenario.nics, ram, vcpus)
    result = run(["sudo"] + args, capture=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"virt-install failed: {result.stderr}")

    has_dhcp = any(nic.mode == "dhcp" for nic in scenario.nics)
    if has_dhcp:
        mgmt_ip = _wait_for_ip(name)
    else:
        mgmt_ip = scenario.nics[0].address.split("/")[0]

    if mgmt_ip:
        _offer_ssh(mgmt_ip, scenario.user, scenario.password)

    return {"name": name, "instance_id": instance_id, "mgmt_ip": mgmt_ip}


def destroy_vm(name: str, vms_dir: Path) -> None:
    snap_result = virsh("snapshot-list", name, "--name")
    snapshots = [s for s in snap_result.stdout.splitlines() if s.strip()]
    if snapshots:
        print(f"  Warning: {name} has {len(snapshots)} snapshot(s); they will be removed too.")

    state_result = virsh("domstate", name)
    if state_result.stdout.strip() == "running":
        # Force power-off first: undefine on a running domain either gets
        # refused or converts it to transient and removes the backing disk
        # out from under the still-running guest.
        destroy_result = virsh("destroy", name)
        if destroy_result.returncode != 0:
            raise RuntimeError(f"Failed to power off {name}: {destroy_result.stderr}")

    result = virsh("undefine", name, "--remove-all-storage", "--snapshots-metadata")
    if result.returncode != 0:
        raise RuntimeError(f"Failed to remove {name}: {result.stderr}")

    # Best-effort cleanup of the non-libvirt-managed working directory
    # (rendered/ seed sources, seed.iso); never fail destroy over this.
    shutil.rmtree(vms_dir / name, ignore_errors=True)


def list_vms() -> list[dict]:
    names = [n for n in virsh("list", "--all", "--name").stdout.splitlines() if n.strip()]
    vms = []
    for name in names:
        state = virsh("domstate", name).stdout.strip()
        mgmt_ip = None
        if state == "running":
            addr_result = virsh("domifaddr", name, "--source", "lease")
            for line in addr_result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 4 and "/" in parts[-1]:
                    mgmt_ip = parts[-1].split("/")[0]
                    break
        vms.append({"name": name, "state": state, "mgmt_ip": mgmt_ip})
    return vms
