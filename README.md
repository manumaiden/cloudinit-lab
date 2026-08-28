# cloudinit-lab

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Spin up disposable RHEL/Fedora/Debian/Ubuntu VMs with cloud-init in seconds,
with parametrized network scenarios.**

Reproducing a cloud-init network configuration problem usually means editing
`meta-data`/`user-data`/`network-config` by hand, regenerating a `seed.iso`,
and re-running `virt-install` every time a detail changes. `cloudinit-lab`
turns that into one command: pick a reusable network scenario (DHCP with DNS
overrides, static IP, or independent multi-NIC configuration), point at a
cloud image, and get a running VM with the exact seed data used saved
alongside it for later comparison.

Built for local KVM/libvirt lab work focused on **network configuration
troubleshooting** — not a general-purpose provisioner, and not a replacement
for [labvirt](https://github.com/manumaiden/labvirt) (which covers
bonding/teaming lab topologies from raw installer images instead).

## Supported OS

Any RHEL, Fedora, Debian, or Ubuntu **cloud** image (already ships with
cloud-init preinstalled) — no curated version table, `virt-install
--os-variant detect=on,require=off` auto-detects the guest OS.

## Requirements

- Linux host with KVM enabled
- `libvirt`, `virt-install`, `qemu-img`, `genisoimage`
- Python 3.10+
- `pyyaml` (`pip install -r requirements.txt`)
- Cloud qcow2 images downloaded from the distro's official cloud image portal

## Installation

```bash
git clone <repo-url> cloudinit-lab
cd cloudinit-lab
pip install -r requirements.txt
./install.sh
source ~/.bashrc   # first time only, if ~/bin wasn't already in PATH
```

## Usage

### Interactive menu

```bash
cloudinit-lab
```

Arrow keys to navigate, `Enter` to select, `q` to quit.

### Direct CLI

```bash
# Place cloud images under images/<os>/<version>*.qcow2, or pass --src explicitly
cloudinit-lab create --os rhel --version 10.2 --scenario dhcp-dns-override --hostname test1

cloudinit-lab list
cloudinit-lab images
cloudinit-lab scenarios
cloudinit-lab destroy test1
```

## Scenario profiles

A scenario is a YAML file describing hostname, user, password, and one or
more NICs (`mode: dhcp` or `mode: static`, with DNS/route overrides). See
`scenarios/` for the three bundled examples. CLI flags (`--hostname`,
`--dns`, ...) override individual fields at run time without editing the
profile.

## What gets applied

For DHCP NICs with DNS-related fields set, `cloudinit-lab` generates an
`nmcli`-based `runcmd` workaround in `user-data` in addition to
`network-config` — several NetworkManager renderer versions silently ignore
`dhcp4-overrides`/`nameservers` from `network-config` alone. Static NICs
don't need this; their addressing and DNS apply natively.

## Static addressing caveat

`cloudinit-lab` does **not** check a static `address` in a scenario against
the libvirt network's DHCP range — that collision detection isn't
implemented, so it's on you to avoid it. Libvirt's default network
(`virsh net-dumpxml default`) is typically `192.168.122.0/24` with DHCP
handing out roughly `.2`-`.254`. If a static NIC's address falls inside that
range, `virt-install`/NetworkManager won't stop you, and you can end up with
an IP conflict against whatever the DHCP server hands out next. Pick a
static address clearly outside the DHCP pool (e.g. `.200`-`.254`), or point
the scenario at a different libvirt network with its own non-overlapping
range. The bundled `scenarios/static-ip.yaml` uses `192.168.122.200/24` for
this reason.

## Project structure

```
cloudinit-lab/
├── cloudinit_lab/       # package: netconfig, scenarios, seed, vmctl, config, tui
├── scenarios/            # bundled example scenario profiles
├── configs/lab.conf       # config template, copied to ~/.cloudinit-lab.conf on install
├── tests/
├── install.sh
└── cloudinit-lab.py       # entry point, symlinked into ~/bin
```

## License

MIT — see [LICENSE](LICENSE).
