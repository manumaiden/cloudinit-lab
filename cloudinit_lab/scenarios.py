"""Scenario profile loading, validation, and CLI-override merging."""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from cloudinit_lab.netconfig import NicConfig

_CIDR_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}/\d{1,2}$")


@dataclass
class Scenario:
    hostname: str
    user: str
    password: str
    nics: list[NicConfig] = field(default_factory=list)
    description: str = ""


class ScenarioValidationError(ValueError):
    """Raised when a scenario profile fails validation."""


def load_scenario(path: Path) -> Scenario:
    with open(path) as f:
        data = yaml.safe_load(f)
    nics = [NicConfig(**nic_data) for nic_data in data.get("nics", [])]
    scenario = Scenario(
        hostname=data["hostname"],
        user=data["user"],
        password=data["password"],
        nics=nics,
        description=data.get("description", ""),
    )
    validate_scenario(scenario)
    return scenario


def validate_scenario(scenario: Scenario) -> None:
    if not scenario.nics:
        raise ScenarioValidationError("Scenario must define at least one NIC")
    for nic in scenario.nics:
        if nic.mode not in ("dhcp", "static"):
            raise ScenarioValidationError(f"NIC {nic.name!r}: unknown mode {nic.mode!r}")
        if nic.mode == "static":
            if not nic.address:
                raise ScenarioValidationError(f"NIC {nic.name!r}: mode=static requires 'address'")
            if not _CIDR_RE.match(nic.address):
                raise ScenarioValidationError(
                    f"NIC {nic.name!r}: 'address' must be CIDR notation, got {nic.address!r}"
                )
            if not nic.gateway:
                raise ScenarioValidationError(f"NIC {nic.name!r}: mode=static requires 'gateway'")


def merge_overrides(scenario: Scenario, overrides: dict) -> Scenario:
    """
    Shallow-merge CLI override values onto a loaded scenario. `hostname`,
    `user`, and `password` override the scenario's top-level fields; `dns`
    and `dns_search` (if present in `overrides`) replace those fields on
    every NIC — CLI overrides don't address individual NICs by name, only
    scenario profiles do that. Returns a new Scenario; never mutates the
    input.
    """
    nics = []
    for nic in scenario.nics:
        new_nic = replace(nic)
        if "dns" in overrides:
            new_nic.dns = overrides["dns"]
        if "dns_search" in overrides:
            new_nic.dns_search = overrides["dns_search"]
        nics.append(new_nic)

    merged = Scenario(
        hostname=overrides.get("hostname", scenario.hostname),
        user=overrides.get("user", scenario.user),
        password=overrides.get("password", scenario.password),
        nics=nics,
        description=scenario.description,
    )
    validate_scenario(merged)
    return merged
