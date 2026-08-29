from cloudinit_lab import __main__ as cli_main
from cloudinit_lab.__main__ import build_parser


def test_version_flag():
    parser = build_parser()
    args = parser.parse_args(["--version"])
    assert args.version is True


def test_create_command_required_args():
    parser = build_parser()
    args = parser.parse_args([
        "create", "--os", "rhel", "--version", "10.2", "--scenario", "static-ip",
    ])
    assert args.command == "create"
    assert args.os == "rhel"
    assert args.os_version == "10.2"
    assert args.scenario == "static-ip"
    assert args.hostname is None


def test_create_command_with_overrides():
    parser = build_parser()
    args = parser.parse_args([
        "create", "--os", "fedora", "--version", "40", "--scenario", "default",
        "--hostname", "test2", "--dns", "1.1.1.1", "9.9.9.9",
    ])
    assert args.hostname == "test2"
    assert args.dns == ["1.1.1.1", "9.9.9.9"]


def test_top_level_version_flag_not_shadowed_by_create_os_version():
    # Regression guard: the top-level --version bool flag and create's
    # --version (OS version string) must not collide on the same dest.
    parser = build_parser()
    args = parser.parse_args(["create", "--os", "rhel", "--version", "10.2", "--scenario", "static-ip"])
    assert args.version is False
    assert args.os_version == "10.2"


def test_destroy_command():
    parser = build_parser()
    args = parser.parse_args(["destroy", "test-vm"])
    assert args.command == "destroy"
    assert args.name == "test-vm"


def test_list_command():
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert args.command == "list"


def test_images_command():
    parser = build_parser()
    args = parser.parse_args(["images"])
    assert args.command == "images"


def test_cmd_scenarios_prints_name_and_description(tmp_path, capsys):
    (tmp_path / "a-scenario.yaml").write_text("""
description: A short description of this scenario
hostname: h
user: manu
password: Test1234!
nics:
  - name: eth0
    mode: dhcp
""")
    rc = cli_main._cmd_scenarios(None, {"SCENARIOS_DIR": tmp_path})
    assert rc == 0
    out = capsys.readouterr().out
    assert "a-scenario" in out
    assert "A short description of this scenario" in out


def test_main_reports_missing_tools_and_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(cli_main, "check_dependencies", lambda: ["virt-install", "genisoimage"])
    rc = cli_main.main(["list"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "error: missing required tools: virt-install, genisoimage" in err


def test_main_handler_exception_is_caught_cleanly(monkeypatch, capsys):
    # Regression guard: an expected failure (RuntimeError/ValueError/
    # FileNotFoundError/OSError, or ScenarioValidationError which subclasses
    # ValueError) raised from a subcommand handler must not propagate out of
    # main() as a raw traceback — it should print a one-line error and
    # return 1.
    monkeypatch.setattr(cli_main, "check_dependencies", lambda: [])

    def fake_list(args, cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main, "_cmd_list", fake_list)
    rc = cli_main.main(["list"])
    assert rc == 1
    assert capsys.readouterr().err.strip() == "error: boom"


def test_main_scenario_validation_error_is_caught_cleanly(monkeypatch, capsys):
    from cloudinit_lab.scenarios import ScenarioValidationError

    monkeypatch.setattr(cli_main, "check_dependencies", lambda: [])

    def fake_create(args, cfg):
        raise ScenarioValidationError("bad scenario")

    monkeypatch.setattr(cli_main, "_cmd_create", fake_create)
    rc = cli_main.main([
        "create", "--os", "rhel", "--version", "10.2", "--scenario", "static-ip",
    ])
    assert rc == 1
    assert "error: bad scenario" in capsys.readouterr().err


def test_main_no_command_dispatches_to_tui_after_dependency_check(monkeypatch):
    monkeypatch.setattr(cli_main, "check_dependencies", lambda: [])
    monkeypatch.setattr(cli_main, "load_config", lambda: {"fake": "cfg"})
    called = []
    monkeypatch.setattr(
        "cloudinit_lab.tui.interactive_main", lambda cfg: called.append(cfg) or 0
    )
    rc = cli_main.main([])
    assert rc == 0
    assert called == [{"fake": "cfg"}]


def test_cmd_destroy_prompts_and_aborts_on_default_no(monkeypatch, capsys):
    monkeypatch.setattr(cli_main.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    called = []
    monkeypatch.setattr(cli_main, "destroy_vm", lambda name, vms_dir: called.append((name, vms_dir)))
    args = type("Args", (), {"name": "test-vm"})()
    rc = cli_main._cmd_destroy(args, {"VMS_DIR": "/tmp/vms"})
    assert rc == 0
    assert called == []
    assert "Aborted" in capsys.readouterr().out


def test_cmd_destroy_proceeds_on_explicit_yes(monkeypatch):
    monkeypatch.setattr(cli_main.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    called = []
    monkeypatch.setattr(cli_main, "destroy_vm", lambda name, vms_dir: called.append((name, vms_dir)))
    args = type("Args", (), {"name": "test-vm"})()
    rc = cli_main._cmd_destroy(args, {"VMS_DIR": "/tmp/vms"})
    assert rc == 0
    assert called == [("test-vm", "/tmp/vms")]


def test_cmd_destroy_skips_prompt_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(cli_main.sys.stdin, "isatty", lambda: False)
    called = []
    monkeypatch.setattr(cli_main, "destroy_vm", lambda name, vms_dir: called.append((name, vms_dir)))
    args = type("Args", (), {"name": "test-vm"})()
    rc = cli_main._cmd_destroy(args, {"VMS_DIR": "/tmp/vms"})
    assert rc == 0
    assert called == [("test-vm", "/tmp/vms")]
