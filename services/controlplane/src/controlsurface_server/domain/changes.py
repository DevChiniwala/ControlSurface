"""Canonical tool contracts and explainable compatibility results."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Compatibility(StrEnum):
    BREAKING = "breaking"
    POSSIBLY_BREAKING = "possibly_breaking"
    COMPATIBLE = "compatible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ContractChange:
    path: str
    description: str
    compatibility: Compatibility


@dataclass(frozen=True)
class ContractDiff:
    before_fingerprint: str
    after_fingerprint: str
    compatibility: Compatibility
    changes: tuple[ContractChange, ...]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(schema: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(schema).encode("utf-8")).hexdigest()


def compare_contracts(before: dict[str, Any], after: dict[str, Any]) -> ContractDiff:
    changes: list[ContractChange] = []
    old_props = before.get("properties")
    new_props = after.get("properties")
    if not isinstance(old_props, dict) or not isinstance(new_props, dict):
        changes.append(
            ContractChange("$", "Unsupported or missing object properties", Compatibility.UNKNOWN)
        )
    else:
        old_required = set(before.get("required", []))
        new_required = set(after.get("required", []))
        for name in sorted(old_props.keys() - new_props.keys()):
            changes.append(ContractChange(name, "Field removed", Compatibility.BREAKING))
        for name in sorted(new_required - old_required):
            changes.append(ContractChange(name, "Required field added", Compatibility.BREAKING))
        for name in sorted(old_props.keys() & new_props.keys()):
            old_field, new_field = old_props[name], new_props[name]
            if not isinstance(old_field, dict) or not isinstance(new_field, dict):
                changes.append(
                    ContractChange(name, "Field shape cannot be compared", Compatibility.UNKNOWN)
                )
                continue
            if old_field.get("type") != new_field.get("type"):
                changes.append(ContractChange(name, "Field type changed", Compatibility.BREAKING))
            old_enum, new_enum = old_field.get("enum"), new_field.get("enum")
            if (
                isinstance(old_enum, list)
                and isinstance(new_enum, list)
                and set(old_enum) - set(new_enum)
            ):
                changes.append(
                    ContractChange(name, "Allowed values removed", Compatibility.BREAKING)
                )
            elif old_enum is None and new_enum is not None:
                changes.append(
                    ContractChange(
                        name, "Allowed values restricted", Compatibility.POSSIBLY_BREAKING
                    )
                )
        for name in sorted(new_props.keys() - old_props.keys() - new_required):
            changes.append(ContractChange(name, "Optional field added", Compatibility.COMPATIBLE))

    severity = (
        Compatibility.BREAKING
        if any(change.compatibility is Compatibility.BREAKING for change in changes)
        else Compatibility.UNKNOWN
        if any(change.compatibility is Compatibility.UNKNOWN for change in changes)
        else Compatibility.POSSIBLY_BREAKING
        if any(change.compatibility is Compatibility.POSSIBLY_BREAKING for change in changes)
        else Compatibility.COMPATIBLE
    )
    return ContractDiff(fingerprint(before), fingerprint(after), severity, tuple(changes))
