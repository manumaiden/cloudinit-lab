"""Config cascade: ~/.cloudinit-lab.conf if present, else configs/lab.conf."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
USER_CONFIG = Path.home() / ".cloudinit-lab.conf"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "lab.conf"


def config_file_path() -> Path:
    return USER_CONFIG if USER_CONFIG.exists() else DEFAULT_CONFIG


def load_config(path: Path | None = None) -> dict:
    path = path or config_file_path()
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                cfg[key.strip()] = value.strip().strip('"')

    cfg["IMAGES_DIR"] = Path(cfg["IMAGES_DIR"]).expanduser() if cfg.get("IMAGES_DIR") else REPO_ROOT / "images"
    cfg["VMS_DIR"] = Path(cfg["VMS_DIR"]).expanduser() if cfg.get("VMS_DIR") else REPO_ROOT / "vms"
    cfg["SCENARIOS_DIR"] = Path(cfg["SCENARIOS_DIR"]).expanduser() if cfg.get("SCENARIOS_DIR") else REPO_ROOT / "scenarios"
    cfg["DEFAULT_RAM"] = int(cfg.get("DEFAULT_RAM") or 2048)
    cfg["DEFAULT_VCPUS"] = int(cfg.get("DEFAULT_VCPUS") or 2)
    return cfg
