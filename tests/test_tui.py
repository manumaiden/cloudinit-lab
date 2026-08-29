from dataclasses import replace

from cloudinit_lab import tui
from cloudinit_lab.netconfig import NicConfig
from cloudinit_lab.scenarios import Scenario


def test_menu_returns_selected_value(monkeypatch):
    # Simulate: down arrow, down arrow, enter -> selects the 3rd item
    keys = iter(["DOWN", "DOWN", "ENTER"])
    monkeypatch.setattr(tui, "_read_key", lambda: next(keys))
    result = tui.menu([("First", "first"), ("Second", "second"), ("Third", "third")])
    assert result == "third"


def test_menu_skips_non_selectable_headers(monkeypatch):
    # Items: header (None value), then two real entries. Cursor starts on
    # the first selectable item, one DOWN then ENTER selects the second.
    keys = iter(["DOWN", "ENTER"])
    monkeypatch.setattr(tui, "_read_key", lambda: next(keys))
    items = [("-- Section --", None), ("A", "a"), ("B", "b")]
    result = tui.menu(items)
    assert result == "b"


def test_menu_quit_returns_none(monkeypatch):
    monkeypatch.setattr(tui, "_read_key", lambda: "QUIT")
    result = tui.menu([("A", "a"), ("B", "b")])
    assert result is None


def test_menu_clears_screen_before_each_redraw(monkeypatch, capsys):
    # Regression guard: menu() must repaint in place, never stack redraws
    # below each other (the bug reported when running the TUI for real).
    keys = iter(["DOWN", "ENTER"])
    monkeypatch.setattr(tui, "_read_key", lambda: next(keys))
    tui.menu([("A", "a"), ("B", "b")])
    out = capsys.readouterr().out
    assert out.count("\033[2J\033[H") == 2  # one redraw per loop iteration


def test_menu_renders_danger_item_in_red_when_not_selected(monkeypatch, capsys):
    monkeypatch.setattr(tui, "_read_key", lambda: "ENTER")
    tui.menu([("Safe", "safe"), ("Dangerous", "dangerous", "danger")])
    out = capsys.readouterr().out
    assert f"{tui.C.RED}Dangerous{tui.C.RST}" in out


def test_menu_legacy_two_tuples_still_work(monkeypatch):
    # Backward compatibility: plain (label, value) tuples default to kind="item".
    monkeypatch.setattr(tui, "_read_key", lambda: "ENTER")
    result = tui.menu([("A", "a"), ("B", "b")])
    assert result == "a"


def test_interactive_create_uses_merge_overrides_not_direct_mutation(monkeypatch, tmp_path):
    # Regression guard: the create flow must go through merge_overrides()
    # (which re-validates) rather than mutating the loaded Scenario in
    # place, so the original object returned by load_scenario is untouched.
    original_scenario = Scenario(
        hostname="orig-host", user="manu", password="x",
        nics=[NicConfig(name="eth0", mode="dhcp")],
    )
    monkeypatch.setattr(tui, "load_scenario", lambda path: original_scenario)

    merge_calls = []

    def fake_merge_overrides(scenario, overrides):
        merge_calls.append((scenario, overrides))
        return replace(scenario, hostname=overrides.get("hostname", scenario.hostname))

    monkeypatch.setattr(tui, "merge_overrides", fake_merge_overrides)
    image_path = tmp_path / "img.qcow2"
    monkeypatch.setattr(tui, "list_images", lambda images_dir: [
        {"os": "rhel", "path": image_path, "size_bytes": 123},
    ])

    create_calls = []

    def fake_create_vm(name, image, scenario, vms_dir, ram, vcpus):
        create_calls.append((name, scenario.hostname))
        return {"name": name, "instance_id": "id-1", "mgmt_ip": "1.2.3.4"}

    monkeypatch.setattr(tui, "create_vm", fake_create_vm)

    menu_returns = iter(["create", "demo", image_path, "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))

    inputs = iter(["new-host"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cfg = {
        "SCENARIOS_DIR": tmp_path, "IMAGES_DIR": tmp_path, "VMS_DIR": tmp_path,
        "DEFAULT_RAM": 2048, "DEFAULT_VCPUS": 2,
    }
    rc = tui.interactive_main(cfg)

    assert rc == 0
    assert merge_calls == [(original_scenario, {"hostname": "new-host"})]
    assert original_scenario.hostname == "orig-host"
    assert create_calls == [("new-host", "new-host")]


def test_interactive_create_no_images_found(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(tui, "list_images", lambda images_dir: [])

    menu_returns = iter(["create", "demo", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))

    inputs = iter([""])  # the pause prompt
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    cfg = {
        "SCENARIOS_DIR": tmp_path, "IMAGES_DIR": tmp_path, "VMS_DIR": tmp_path,
        "DEFAULT_RAM": 2048, "DEFAULT_VCPUS": 2,
    }
    rc = tui.interactive_main(cfg)

    assert rc == 0
    assert "No images found." in capsys.readouterr().out


def test_interactive_create_image_selection_cancelled_does_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(tui, "list_images", lambda images_dir: [
        {"os": "rhel", "path": tmp_path / "img.qcow2", "size_bytes": 123},
    ])

    menu_returns = iter(["create", "demo", None, "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))

    def fail_input(prompt=""):
        raise AssertionError("input() should not be called when image selection is cancelled")

    monkeypatch.setattr("builtins.input", fail_input)

    create_calls = []
    monkeypatch.setattr(tui, "create_vm", lambda *a, **kw: create_calls.append(1))

    cfg = {
        "SCENARIOS_DIR": tmp_path, "IMAGES_DIR": tmp_path, "VMS_DIR": tmp_path,
        "DEFAULT_RAM": 2048, "DEFAULT_VCPUS": 2,
    }
    rc = tui.interactive_main(cfg)

    assert rc == 0
    assert create_calls == []


def test_interactive_destroy_prompts_and_aborts_on_no(monkeypatch):
    # Regression guard: destroy must offer a selectable list of existing
    # VMs (labvirt-style), not a free-typed name.
    menu_returns = iter(["destroy", "test-vm", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui, "list_vms", lambda: [{"name": "test-vm", "state": "running", "mgmt_ip": "1.2.3.4"}])

    inputs = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    destroy_calls = []
    monkeypatch.setattr(tui, "destroy_vm", lambda name, vms_dir: destroy_calls.append((name, vms_dir)))

    rc = tui.interactive_main({"VMS_DIR": "/tmp/vms", "SCENARIOS_DIR": "/tmp"})
    assert rc == 0
    assert destroy_calls == []


def test_interactive_destroy_proceeds_on_yes(monkeypatch):
    menu_returns = iter(["destroy", "test-vm", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui, "list_vms", lambda: [{"name": "test-vm", "state": "running", "mgmt_ip": "1.2.3.4"}])

    inputs = iter(["y", ""])  # trailing "" answers the post-action pause
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    destroy_calls = []
    monkeypatch.setattr(tui, "destroy_vm", lambda name, vms_dir: destroy_calls.append((name, vms_dir)))

    rc = tui.interactive_main({"VMS_DIR": "/tmp/vms", "SCENARIOS_DIR": "/tmp"})
    assert rc == 0
    assert destroy_calls == [("test-vm", "/tmp/vms")]


def test_interactive_destroy_skips_prompt_when_not_a_tty(monkeypatch):
    menu_returns = iter(["destroy", "test-vm", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(tui, "list_vms", lambda: [{"name": "test-vm", "state": "running", "mgmt_ip": "1.2.3.4"}])

    def fail_input(prompt=""):
        raise AssertionError("input() should not be called when stdin isn't a tty")

    monkeypatch.setattr("builtins.input", fail_input)

    destroy_calls = []
    monkeypatch.setattr(tui, "destroy_vm", lambda name, vms_dir: destroy_calls.append((name, vms_dir)))

    rc = tui.interactive_main({"VMS_DIR": "/tmp/vms", "SCENARIOS_DIR": "/tmp"})
    assert rc == 0
    assert destroy_calls == [("test-vm", "/tmp/vms")]


def test_interactive_destroy_selection_cancelled_does_nothing(monkeypatch):
    # Quitting the VM-selection submenu (None) must return to the main menu
    # without prompting for confirmation or destroying anything.
    menu_returns = iter(["destroy", None, "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui, "list_vms", lambda: [{"name": "test-vm", "state": "running", "mgmt_ip": "1.2.3.4"}])

    def fail_input(prompt=""):
        raise AssertionError("input() should not be called when selection is cancelled")

    monkeypatch.setattr("builtins.input", fail_input)

    destroy_calls = []
    monkeypatch.setattr(tui, "destroy_vm", lambda name, vms_dir: destroy_calls.append((name, vms_dir)))

    rc = tui.interactive_main({"VMS_DIR": "/tmp/vms", "SCENARIOS_DIR": "/tmp"})
    assert rc == 0
    assert destroy_calls == []


def test_interactive_destroy_no_vms_found(monkeypatch, capsys):
    menu_returns = iter(["destroy", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui, "list_vms", lambda: [])

    inputs = iter([""])  # the pause prompt
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    rc = tui.interactive_main({"VMS_DIR": "/tmp/vms", "SCENARIOS_DIR": "/tmp"})
    assert rc == 0
    assert "No VMs found." in capsys.readouterr().out


def test_interactive_images_pauses_before_next_redraw_clears_it(monkeypatch, tmp_path, capsys):
    # Regression guard: menu() clears the screen on every redraw, so listing
    # output (images/VMs/scenarios) must wait for the user to press Enter
    # before looping back into it, or the result is wiped before it's read.
    menu_returns = iter(["images", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(tui, "list_images", lambda images_dir: [
        {"os": "fedora", "path": tmp_path / "f.qcow2", "size_bytes": 123},
    ])

    inputs = iter([""])  # the pause prompt
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    rc = tui.interactive_main({"IMAGES_DIR": tmp_path})

    assert rc == 0
    assert "fedora" in capsys.readouterr().out


def test_interactive_images_skips_pause_when_not_a_tty(monkeypatch, tmp_path):
    menu_returns = iter(["images", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))
    monkeypatch.setattr(tui.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(tui, "list_images", lambda images_dir: [])

    def fail_input(prompt=""):
        raise AssertionError("input() should not be called when stdin isn't a tty")

    monkeypatch.setattr("builtins.input", fail_input)

    rc = tui.interactive_main({"IMAGES_DIR": tmp_path})
    assert rc == 0


def test_interactive_scenarios_prints_name_and_description(monkeypatch, tmp_path, capsys):
    (tmp_path / "a-scenario.yaml").write_text("""
description: A short description of this scenario
hostname: h
user: manu
password: Test1234!
nics:
  - name: eth0
    mode: dhcp
""")
    menu_returns = iter(["scenarios", "quit"])
    monkeypatch.setattr(tui, "menu", lambda *a, **kw: next(menu_returns))

    inputs = iter([""])  # the pause prompt
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    rc = tui.interactive_main({"SCENARIOS_DIR": tmp_path})

    assert rc == 0
    out = capsys.readouterr().out
    assert "a-scenario" in out
    assert "A short description of this scenario" in out
