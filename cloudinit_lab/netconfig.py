"""Network configuration model and netplan v2 rendering."""

from dataclasses import dataclass, field

import yaml


@dataclass
class NicConfig:
    name: str = "eth0"
    mode: str = "dhcp"  # "dhcp" | "static"
    address: str | None = None
    gateway: str | None = None
    routes: list[dict] = field(default_factory=list)
    dns: list[str] = field(default_factory=list)
    dns_search: list[str] = field(default_factory=list)
    ignore_auto_dns: bool = False
    dhcp_hostname: str | None = None


def render_network_config(nics: list[NicConfig]) -> str:
    """Render a netplan v2 network-config YAML document for the given NICs."""
    ethernets = {}
    for nic in nics:
        entry = {}
        if nic.mode == "dhcp":
            entry["dhcp4"] = True
        elif nic.mode == "static":
            entry["addresses"] = [nic.address]
            routes = list(nic.routes)
            if nic.gateway:
                routes.insert(0, {"to": "0.0.0.0/0", "via": nic.gateway})
            if routes:
                entry["routes"] = routes
            if nic.dns or nic.dns_search:
                nameservers = {}
                if nic.dns:
                    nameservers["addresses"] = nic.dns
                if nic.dns_search:
                    nameservers["search"] = nic.dns_search
                entry["nameservers"] = nameservers
        else:
            raise ValueError(f"Unknown NIC mode: {nic.mode!r}")
        ethernets[nic.name] = entry

    config = {"network": {"version": 2, "ethernets": ethernets}}
    return yaml.safe_dump(config, sort_keys=False)


def render_dns_workaround_runcmd(nics: list[NicConfig]) -> list[str]:
    """
    Build the nmcli runcmd lines that force DNS-related settings onto a DHCP
    NIC after boot. Generated unconditionally whenever a DHCP NIC has a
    DNS-related field set — not gated by OS/version, since the workaround is
    harmless when the target renderer would have applied the values anyway.
    Static NICs never need this: network-config applies their nameservers
    natively.
    """
    lines = []
    for nic in nics:
        if nic.mode != "dhcp":
            continue
        if not (nic.dns or nic.dns_search or nic.ignore_auto_dns or nic.dhcp_hostname):
            continue
        con_name = f"cloud-init {nic.name}"
        if nic.ignore_auto_dns:
            lines.append(f'nmcli con mod "{con_name}" ipv4.ignore-auto-dns yes')
        if nic.dns:
            lines.append(f'nmcli con mod "{con_name}" ipv4.dns "{" ".join(nic.dns)}"')
        if nic.dns_search:
            lines.append(f'nmcli con mod "{con_name}" ipv4.dns-search "{" ".join(nic.dns_search)}"')
        if nic.dhcp_hostname:
            lines.append(f'nmcli con mod "{con_name}" ipv4.dhcp-hostname "{nic.dhcp_hostname}"')
        lines.append(f'nmcli con up "{con_name}"')
    return lines
