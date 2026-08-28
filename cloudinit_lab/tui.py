"""Arrow-key interactive menu and the interactive main flow."""

import sys
import termios
import tty

from cloudinit_lab.scenarios import load_scenario, merge_overrides
from cloudinit_lab.vmctl import create_vm, destroy_vm, list_images, list_vms, resolve_image


def _read_key() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.buffer.read(1)
        if ch == b"\x1b":
            ch2 = sys.stdin.buffer.read(2)
            if ch2 == b"[A":
                return "UP"
            if ch2 == b"[B":
                return "DOWN"
            return "QUIT"
        if ch in (b"\r", b"\n"):
            return "ENTER"
        if ch in (b"q", b"Q"):
            return "QUIT"
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def menu(items: list[tuple[str, str | None]], title: str = "") -> str | None:
    """
    Arrow-key menu. Items are (label, value) pairs; value=None marks a
    non-selectable section header. Returns the selected value, or None if
    the user quits.
    """
    selectable_indices = [i for i, (_, v) in enumerate(items) if v is not None]
    if not selectable_indices:
        return None
    cursor = selectable_indices[0]

    while True:
        if title:
            print(title)
        for i, (label, value) in enumerate(items):
            marker = "> " if i == cursor else "  "
            print(f"{marker}{label}")

        key = _read_key()
        if key == "QUIT":
            return None
        if key == "ENTER":
            return items[cursor][1]
        if key in ("UP", "DOWN"):
            pos = selectable_indices.index(cursor)
            if key == "DOWN":
                pos = (pos + 1) % len(selectable_indices)
            else:
                pos = (pos - 1) % len(selectable_indices)
            cursor = selectable_indices[pos]


def interactive_main(cfg: dict) -> int:
    while True:
        choice = menu([
            ("-- Provisioning --", None),
            ("Create VM", "create"),
            ("Destroy VM", "destroy"),
            ("-- Info --", None),
            ("List VMs", "list"),
            ("List images", "images"),
            ("List scenarios", "scenarios"),
            ("Quit", "quit"),
        ], title="cloudinit-lab")

        if choice in (None, "quit"):
            return 0

        if choice == "create":
            scenario_names = [p.stem for p in sorted(cfg["SCENARIOS_DIR"].glob("*.yaml"))]
            scenario_choice = menu(
                [(name, name) for name in scenario_names], title="Select a scenario"
            )
            if scenario_choice is None:
                continue
            os_name = input("OS (e.g. rhel): ").strip()
            version = input("Version (e.g. 10.2): ").strip()
            hostname = input("Hostname override (blank = use scenario default): ").strip() or None

            scenario = load_scenario(cfg["SCENARIOS_DIR"] / f"{scenario_choice}.yaml")
            overrides = {"hostname": hostname} if hostname else {}
            scenario = merge_overrides(scenario, overrides)
            image = resolve_image(cfg["IMAGES_DIR"], os_name, version)
            result = create_vm(scenario.hostname, image, scenario, cfg["VMS_DIR"],
                                ram=cfg["DEFAULT_RAM"], vcpus=cfg["DEFAULT_VCPUS"])
            print(f"Created {result['name']} (IP {result['mgmt_ip']})")

        elif choice == "destroy":
            name = input("VM name to destroy: ").strip()
            if name:
                if sys.stdin.isatty():
                    answer = input(
                        f"Destroy VM '{name}'? This removes its disk permanently. [y/N] "
                    ).strip().lower()
                    if answer not in ("y", "yes"):
                        continue
                destroy_vm(name, cfg["VMS_DIR"])
                print(f"Destroyed {name}")

        elif choice == "list":
            for vm in list_vms():
                print(f"{vm['name']:20} {vm['state']:12} {vm['mgmt_ip'] or '-'}")

        elif choice == "images":
            for img in list_images(cfg["IMAGES_DIR"]):
                print(f"{img['os']:12} {img['path']} ({img['size_bytes']} bytes)")

        elif choice == "scenarios":
            for p in sorted(cfg["SCENARIOS_DIR"].glob("*.yaml")):
                print(p.stem)
