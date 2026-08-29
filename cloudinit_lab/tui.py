"""Arrow-key interactive menu and the interactive main flow."""

import sys
import termios
import tty

from cloudinit_lab import __build_date__, __version__
from cloudinit_lab.scenarios import load_scenario, merge_overrides
from cloudinit_lab.vmctl import create_vm, destroy_vm, list_images, list_vms


class C:
    RST = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_BLUE = "\033[44m"


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


def menu(items: list[tuple], title: str = "") -> str | None:
    """
    Arrow-key menu. Items are (label, value) or (label, value, kind) tuples;
    value=None marks a non-selectable section header. kind="danger" renders
    the label in red when not selected (default kind="item"). Returns the
    selected value, or None if the user quits.
    """
    selectable_indices = [i for i, item in enumerate(items) if item[1] is not None]
    if not selectable_indices:
        return None
    cursor = selectable_indices[0]

    while True:
        sys.stdout.write("\033[2J\033[H")
        print(f"\n  {C.BOLD}{C.CYAN}cloudinit-lab{C.RST}  "
              f"{C.DIM}RHEL · Fedora · Debian · Ubuntu cloud-init lab{C.RST}")
        print(f"  {C.DIM}version {__version__} ({__build_date__}) by manumaiden{C.RST}")
        print(f"  {C.DIM}{'─' * 50}{C.RST}\n")
        if title:
            print(f"  {C.BOLD}{title}{C.RST}\n")
        for i, item in enumerate(items):
            label, value = item[0], item[1]
            kind = item[2] if len(item) > 2 else "item"
            if value is None:
                print(f"\n  {C.DIM}{C.BOLD}{label}{C.RST}")
            elif i == cursor:
                print(f"  {C.BG_BLUE}{C.WHITE}{C.BOLD}  {label:<32}  {C.RST}")
            elif kind == "danger":
                print(f"    {C.RED}{label}{C.RST}")
            else:
                print(f"    {label}")
        print(f"\n  {C.DIM}↑↓ navigate   Enter select   q quit{C.RST}")
        sys.stdout.flush()

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


def _pause() -> None:
    # menu() clears the screen on its next redraw, so give the user a
    # chance to actually read whatever was just printed before it's wiped.
    if sys.stdin.isatty():
        input(f"\n  {C.DIM}Press Enter to continue...{C.RST}")


def interactive_main(cfg: dict) -> int:
    while True:
        choice = menu([
            ("-- Provisioning --", None),
            ("Create VM", "create"),
            ("Destroy VM", "destroy", "danger"),
            ("-- Info --", None),
            ("List VMs", "list"),
            ("List images", "images"),
            ("List scenarios", "scenarios"),
            ("Quit", "quit"),
        ], title="Main menu")

        if choice in (None, "quit"):
            return 0

        if choice == "create":
            scenario_names = [p.stem for p in sorted(cfg["SCENARIOS_DIR"].glob("*.yaml"))]
            scenario_choice = menu(
                [(name, name) for name in scenario_names], title="Select a scenario"
            )
            if scenario_choice is None:
                continue

            images = list_images(cfg["IMAGES_DIR"])
            if not images:
                print("No images found.")
                _pause()
                continue
            image = menu(
                [(f"{img['os']:12} {img['path']} ({img['size_bytes']} bytes)", img["path"])
                 for img in images],
                title="Select an image",
            )
            if image is None:
                continue

            hostname = input("Hostname override (blank = use scenario default): ").strip() or None

            scenario = load_scenario(cfg["SCENARIOS_DIR"] / f"{scenario_choice}.yaml")
            overrides = {"hostname": hostname} if hostname else {}
            scenario = merge_overrides(scenario, overrides)
            result = create_vm(scenario.hostname, image, scenario, cfg["VMS_DIR"],
                                ram=cfg["DEFAULT_RAM"], vcpus=cfg["DEFAULT_VCPUS"])
            print(f"Created {result['name']} (IP {result['mgmt_ip']})")
            _pause()

        elif choice == "destroy":
            vms = list_vms()
            if not vms:
                print("No VMs found.")
                _pause()
                continue
            name = menu(
                [(f"{vm['name']:20} {vm['state']:12} {vm['mgmt_ip'] or '-'}", vm["name"], "danger")
                 for vm in vms],
                title="Select VM to destroy",
            )
            if name is None:
                continue
            if sys.stdin.isatty():
                answer = input(
                    f"Destroy VM '{name}'? This removes its disk permanently. [y/N] "
                ).strip().lower()
                if answer not in ("y", "yes"):
                    continue
            destroy_vm(name, cfg["VMS_DIR"])
            print(f"Destroyed {name}")
            _pause()

        elif choice == "list":
            for vm in list_vms():
                print(f"{vm['name']:20} {vm['state']:12} {vm['mgmt_ip'] or '-'}")
            _pause()

        elif choice == "images":
            for img in list_images(cfg["IMAGES_DIR"]):
                print(f"{img['os']:12} {img['path']} ({img['size_bytes']} bytes)")
            _pause()

        elif choice == "scenarios":
            for p in sorted(cfg["SCENARIOS_DIR"].glob("*.yaml")):
                print(p.stem)
            _pause()
