"""CLI entry point for cloudinit-lab: argparse dispatch, or TUI with no args."""

import argparse
import sys

from cloudinit_lab import __version__
from cloudinit_lab.config import load_config
from cloudinit_lab.scenarios import load_scenario, merge_overrides
from cloudinit_lab.vmctl import check_dependencies, create_vm, destroy_vm, list_images, list_vms, resolve_image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloudinit-lab")
    parser.add_argument("--version", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    create_p = subparsers.add_parser("create", help="create a VM from a scenario")
    create_p.add_argument("--os", required=True)
    # dest="os_version": must not collide with the top-level --version bool flag,
    # which argparse would otherwise silently overwrite with this string value.
    create_p.add_argument("--version", required=True, dest="os_version")
    create_p.add_argument("--scenario", required=True)
    create_p.add_argument("--src", default=None)
    create_p.add_argument("--hostname", default=None)
    create_p.add_argument("--user", default=None)
    create_p.add_argument("--password", default=None)
    create_p.add_argument("--dns", nargs="+", default=None)
    create_p.add_argument("--dns-search", nargs="+", default=None, dest="dns_search")

    destroy_p = subparsers.add_parser("destroy", help="destroy a VM")
    destroy_p.add_argument("name")

    subparsers.add_parser("list", help="list VMs")
    subparsers.add_parser("images", help="list catalog images")
    subparsers.add_parser("scenarios", help="list available scenario profiles")

    return parser


def _cmd_create(args, cfg) -> int:
    scenario_path = cfg["SCENARIOS_DIR"] / f"{args.scenario}.yaml"
    scenario = load_scenario(scenario_path)

    overrides = {}
    for field_name in ("hostname", "user", "password", "dns", "dns_search"):
        value = getattr(args, field_name)
        if value is not None:
            overrides[field_name] = value
    scenario = merge_overrides(scenario, overrides)

    image = resolve_image(cfg["IMAGES_DIR"], args.os, args.os_version, explicit_src=args.src)
    vm_name = scenario.hostname
    result = create_vm(vm_name, image, scenario, cfg["VMS_DIR"],
                        ram=cfg["DEFAULT_RAM"], vcpus=cfg["DEFAULT_VCPUS"])
    print(f"Created {result['name']} (instance-id {result['instance_id']}, IP {result['mgmt_ip']})")
    return 0


def _cmd_destroy(args, cfg) -> int:
    if sys.stdin.isatty():
        answer = input(
            f"Destroy VM '{args.name}'? This removes its disk permanently. [y/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 0
    destroy_vm(args.name, cfg["VMS_DIR"])
    print(f"Destroyed {args.name}")
    return 0


def _cmd_list(args, cfg) -> int:
    for vm in list_vms():
        print(f"{vm['name']:20} {vm['state']:12} {vm['mgmt_ip'] or '-'}")
    return 0


def _cmd_images(args, cfg) -> int:
    for img in list_images(cfg["IMAGES_DIR"]):
        print(f"{img['os']:12} {img['path']} ({img['size_bytes']} bytes)")
    return 0


def _cmd_scenarios(args, cfg) -> int:
    for path in sorted(cfg["SCENARIOS_DIR"].glob("*.yaml")):
        print(path.stem)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        print(f"cloudinit-lab version {__version__}")
        return 0

    missing = check_dependencies()
    if missing:
        print(f"error: missing required tools: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        if args.command is None:
            from cloudinit_lab.tui import interactive_main
            return interactive_main(load_config())

        cfg = load_config()
        handlers = {
            "create": _cmd_create,
            "destroy": _cmd_destroy,
            "list": _cmd_list,
            "images": _cmd_images,
            "scenarios": _cmd_scenarios,
        }
        return handlers[args.command](args, cfg)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
