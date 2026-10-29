"""Rule protocol and shared finding/capture types.

Every WCAG rule lives in its own file under app/rules/ and registers itself in
app/rules/__init__.py. Findings are heuristic *candidates for human review*,
not compliance verdicts — keep wording cautious.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_bounds(value: str | None) -> list[int] | None:
    """Parse uiautomator '[l,t][r,b]' bounds into [l, t, r, b]."""
    match = BOUNDS_RE.fullmatch(value or "")
    if not match:
        return None
    return [int(part) for part in match.groups()]


@dataclass
class CaptureContext:
    """Everything a rule needs about one scanned screen."""

    udid: str
    scan_id: str
    scan_dir: Path  # per-scan evidence folder: screenshot.png / hierarchy.xml / nodes.json / report.json
    screenshot_path: Path  # captured at the device's normal font scale
    xml_normal_path: Path  # uiautomator XML at the current (normal) font scale
    density_dpi: int | None
    app_package: str | None = None  # used to filter out system-UI nodes


def make_finding(
    rule_id: str,
    title: str,
    evidence: str,
    node: dict[str, Any] | None = None,
    severity: str = "warning",
    confidence: str = "medium",
    note: str = "",
) -> dict[str, Any]:
    """Finding schema follows the reference CLI script's report.json."""
    return {
        "rule_id": rule_id,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "node": node or {},
        "confidence": confidence,
        "note": note,
    }


class Rule(Protocol):
    rule_id: str
    title: str

    def check(self, ctx: CaptureContext) -> list[dict[str, Any]]: ...
