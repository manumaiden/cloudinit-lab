import pytest

from cloudinit_lab import vmctl


def test_check_dependencies_reports_missing(monkeypatch):
    def fake_which(name):
        return None if name == "genisoimage" else f"/usr/bin/{name}"
    monkeypatch.setattr(vmctl.shutil, "which", fake_which)
    assert vmctl.check_dependencies() == ["genisoimage"]


def test_check_dependencies_empty_when_all_present(monkeypatch):
    monkeypatch.setattr(vmctl.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert vmctl.check_dependencies() == []


def test_resolve_image_explicit_src(tmp_path):
    img = tmp_path / "custom.qcow2"
    img.write_bytes(b"fake")
    resolved = vmctl.resolve_image(tmp_path, "rhel", "10.2", explicit_src=str(img))
    assert resolved == img


def test_resolve_image_explicit_src_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        vmctl.resolve_image(tmp_path, "rhel", "10.2", explicit_src=str(tmp_path / "missing.qcow2"))


def test_resolve_image_from_catalog(tmp_path):
    os_dir = tmp_path / "rhel"
    os_dir.mkdir()
    img = os_dir / "10.2-cloud.qcow2"
    img.write_bytes(b"fake")
    resolved = vmctl.resolve_image(tmp_path, "rhel", "10.2")
    assert resolved == img


def test_resolve_image_no_match_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        vmctl.resolve_image(tmp_path, "rhel", "10.2")


def test_resolve_image_ambiguous_match_raises(tmp_path):
    os_dir = tmp_path / "rhel"
    os_dir.mkdir()
    (os_dir / "10.2-a.qcow2").write_bytes(b"fake")
    (os_dir / "10.2-b.qcow2").write_bytes(b"fake")
    with pytest.raises(ValueError, match="Multiple images match"):
        vmctl.resolve_image(tmp_path, "rhel", "10.2")


def test_list_images_returns_catalog(tmp_path):
    os_dir = tmp_path / "fedora"
    os_dir.mkdir()
    (os_dir / "40.qcow2").write_bytes(b"fake-content")
    results = vmctl.list_images(tmp_path)
    assert len(results) == 1
    assert results[0]["os"] == "fedora"
    assert results[0]["path"] == os_dir / "40.qcow2"
    assert results[0]["size_bytes"] == len(b"fake-content")


def test_list_images_empty_dir_returns_empty_list(tmp_path):
    assert vmctl.list_images(tmp_path) == []


from pathlib import Path

from cloudinit_lab.netconfig import NicConfig


def test_build_virt_install_args_single_nic():
    args = vmctl.build_virt_install_args(
        "test-vm", Path("/vms/test-vm.qcow2"), Path("/vms/seed.iso"),
        [NicConfig(name="eth0", mode="dhcp")], ram=2048, vcpus=2,
    )
    assert args[:3] == ["virt-install", "--name", "test-vm"]
    assert "--memory" in args and args[args.index("--memory") + 1] == "2048"
    assert args.count("--network") == 1
    assert "/vms/test-vm.qcow2,device=disk,bus=virtio,format=qcow2" in args
    assert "/vms/seed.iso,device=cdrom" in args
    # Regression guard: without --noautoconsole, virt-install attaches to
    # the guest's serial console and blocks forever once its stdout is
    # piped (as create_vm's run(..., capture=True) does), instead of
    # returning control once the domain is defined and started.
    assert "--noautoconsole" in args


def test_build_virt_install_args_multi_nic():
    nics = [NicConfig(name="eth0", mode="dhcp"), NicConfig(name="eth1", mode="dhcp")]
    args = vmctl.build_virt_install_args(
        "test-vm", Path("/vms/test-vm.qcow2"), Path("/vms/seed.iso"), nics, ram=2048, vcpus=2,
    )
    assert args.count("--network") == 2


def test_wait_for_ip_returns_immediately_when_found(monkeypatch):
    calls = []
    monkeypatch.setattr(
        vmctl, "virsh",
        lambda *a: type("R", (), {"stdout": " eth0  52:54:00:aa:bb:cc  ipv4  192.168.122.50/24"})(),
    )
    result = vmctl._wait_for_ip("test-vm", sleep_fn=lambda s: calls.append(s))
    assert result == "192.168.122.50"
    assert calls == []


def test_wait_for_ip_retries_then_finds(monkeypatch):
    responses = iter([
        type("R", (), {"stdout": ""})(),
        type("R", (), {"stdout": " eth0  52:54:00:aa:bb:cc  ipv4  10.0.0.5/24"})(),
    ])
    monkeypatch.setattr(vmctl, "virsh", lambda *a: next(responses))
    sleeps = []
    result = vmctl._wait_for_ip("test-vm", sleep_fn=lambda s: sleeps.append(s))
    assert result == "10.0.0.5"
    assert sleeps == [2.0]


def test_wait_for_ip_gives_up_after_attempts(monkeypatch):
    monkeypatch.setattr(vmctl, "virsh", lambda *a: type("R", (), {"stdout": ""})())
    sleeps = []
    result = vmctl._wait_for_ip("test-vm", attempts=3, sleep_fn=lambda s: sleeps.append(s))
    assert result is None
    assert len(sleeps) == 3


def _fake_result(stdout="", returncode=0, stderr=""):
    return type("R", (), {"stdout": stdout, "returncode": returncode, "stderr": stderr})()


def test_destroy_vm_success(monkeypatch, tmp_path):
    calls = []

    def fake_virsh(*args):
        calls.append(args)
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        if args[0] == "undefine":
            return _fake_result(returncode=0)
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vmctl.destroy_vm("test-vm", tmp_path)
    assert ("undefine", "test-vm", "--remove-all-storage", "--snapshots-metadata") in calls


def test_destroy_vm_raises_on_failure(monkeypatch, tmp_path):
    def fake_virsh(*args):
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        return _fake_result(returncode=1, stderr="storage not managed by libvirt")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    with pytest.raises(RuntimeError, match="storage not managed"):
        vmctl.destroy_vm("test-vm", tmp_path)


def test_destroy_vm_warns_on_existing_snapshots(monkeypatch, capsys, tmp_path):
    def fake_virsh(*args):
        if args[0] == "snapshot-list":
            return _fake_result(stdout="snap1\nsnap2\n")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        return _fake_result(returncode=0)

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vmctl.destroy_vm("test-vm", tmp_path)
    assert "2 snapshot" in capsys.readouterr().out


def test_destroy_vm_powers_off_running_vm_before_undefine(monkeypatch, tmp_path):
    calls = []

    def fake_virsh(*args):
        calls.append(args[0])
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="running\n")
        if args[0] == "destroy":
            return _fake_result(returncode=0)
        if args[0] == "undefine":
            return _fake_result(returncode=0)
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vmctl.destroy_vm("test-vm", tmp_path)
    assert "destroy" in calls
    assert calls.index("destroy") < calls.index("undefine")


def test_destroy_vm_skips_power_off_when_already_shut_off(monkeypatch, tmp_path):
    calls = []

    def fake_virsh(*args):
        calls.append(args[0])
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        if args[0] == "undefine":
            return _fake_result(returncode=0)
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vmctl.destroy_vm("test-vm", tmp_path)
    assert "destroy" not in calls


def test_destroy_vm_raises_when_power_off_fails(monkeypatch, tmp_path):
    def fake_virsh(*args):
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="running\n")
        if args[0] == "destroy":
            return _fake_result(returncode=1, stderr="failed to destroy domain")
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    with pytest.raises(RuntimeError, match="Failed to power off"):
        vmctl.destroy_vm("test-vm", tmp_path)


def test_destroy_vm_removes_working_directory(monkeypatch, tmp_path):
    vm_dir = tmp_path / "test-vm"
    vm_dir.mkdir()
    (vm_dir / "rendered").mkdir()
    (vm_dir / "test-vm.qcow2").write_bytes(b"fake")

    def fake_virsh(*args):
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        if args[0] == "undefine":
            return _fake_result(returncode=0)
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vmctl.destroy_vm("test-vm", tmp_path)
    assert not vm_dir.exists()


def test_destroy_vm_missing_working_directory_does_not_crash(monkeypatch, tmp_path):
    def fake_virsh(*args):
        if args[0] == "snapshot-list":
            return _fake_result(stdout="")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        if args[0] == "undefine":
            return _fake_result(returncode=0)
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vmctl.destroy_vm("test-vm", tmp_path)  # tmp_path/test-vm was never created


def test_list_vms_reports_state_and_ip(monkeypatch):
    def fake_virsh(*args):
        if args[0] == "list":
            return _fake_result(stdout="test-vm\n")
        if args[0] == "domstate":
            return _fake_result(stdout="running\n")
        if args[0] == "domifaddr":
            return _fake_result(stdout=" eth0  52:54:00:aa:bb:cc  ipv4  192.168.122.50/24")
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vms = vmctl.list_vms()
    assert vms == [{"name": "test-vm", "state": "running", "mgmt_ip": "192.168.122.50"}]


def test_list_vms_no_ip_when_shutoff(monkeypatch):
    def fake_virsh(*args):
        if args[0] == "list":
            return _fake_result(stdout="test-vm\n")
        if args[0] == "domstate":
            return _fake_result(stdout="shut off\n")
        raise AssertionError(f"unexpected virsh call: {args}")

    monkeypatch.setattr(vmctl, "virsh", fake_virsh)
    vms = vmctl.list_vms()
    assert vms == [{"name": "test-vm", "state": "shut off", "mgmt_ip": None}]
