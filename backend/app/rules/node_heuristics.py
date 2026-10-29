"""通用节点启发式规则（移植自 manual_android_accessibility_scan(2).py 的 analyze_xml）。

* ``ANDROID_NODE_001`` — 可交互节点可能缺少可访问名称（clickable/long-clickable
  但 text 与 content-desc 均为空）。
* ``ANDROID_NODE_002`` — 可交互节点触控区域可能小于 48dp。

同时导出 ``parse_nodes``：把 uiautomator XML 解析为结构化节点列表，供扫描器
落盘 nodes.json（与参考脚本保持一致）。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .base import CaptureContext, make_finding, parse_bounds


def parse_nodes(xml_path: Path) -> list[dict[str, Any]]:
    """Parse a uiautomator hierarchy XML into the reference script's node shape."""
    root = ET.parse(xml_path).getroot()
    nodes: list[dict[str, Any]] = []
    for idx, el in enumerate(root.iter("node")):
        a = el.attrib
        nodes.append(
            {
                "index": idx,
                "class": a.get("class"),
                "resource_id": a.get("resource-id"),
                "text": (a.get("text") or "").strip(),
                "content_desc": (a.get("content-desc") or "").strip(),
                "clickable": a.get("clickable") == "true",
                "long_clickable": a.get("long-clickable") == "true",
                "focusable": a.get("focusable") == "true",
                "enabled": a.get("enabled"),
                "visible_to_user": a.get("visible-to-user", "true") == "true",
                "bounds": a.get("bounds"),
                "checked": a.get("checked"),
                "selected": a.get("selected"),
            }
        )
    return nodes


class NodeHeuristicsRule:
    rule_id = "ANDROID_NODE_HEURISTICS"
    title = "通用节点启发式（可访问名称 / 触控区域）"

    def check(self, ctx: CaptureContext) -> list[dict[str, Any]]:
        density_scale = (ctx.density_dpi or 160) / 160.0
        nodes = parse_nodes(ctx.xml_normal_path)
        findings: list[dict[str, Any]] = []
        for item in nodes:
            if not item["visible_to_user"]:
                continue
            interactive = item["clickable"] or item["long_clickable"]
            label = item["text"] or item["content_desc"]
            # 供前端浮动标注使用的数值边界
            numeric_bounds = parse_bounds(item["bounds"])

            if interactive and not label:
                findings.append(
                    make_finding(
                        "ANDROID_NODE_001",
                        "可交互节点可能缺少可访问名称",
                        f"节点 {item['index']} 是 clickable/long-clickable，但 text 和 content-desc 均为空",
                        node={**item, "bounds_normal": numeric_bounds},
                        note="需结合屏幕视觉、父子节点和 TalkBack 实际朗读人工复核。",
                    )
                )
            if interactive and numeric_bounds:
                x1, y1, x2, y2 = numeric_bounds
                width_dp = (x2 - x1) / density_scale
                height_dp = (y2 - y1) / density_scale
                if width_dp < 48 or height_dp < 48:
                    findings.append(
                        make_finding(
                            "ANDROID_NODE_002",
                            "可交互节点触控区域可能小于 48dp",
                            f"节点 {item['index']} 的边界约为 {width_dp:.1f} × {height_dp:.1f} dp",
                            node={**item, "bounds_normal": numeric_bounds, "width_dp": round(width_dp, 1), "height_dp": round(height_dp, 1)},
                            note="这是启发式检查；可点击区域可能由父节点或自定义 View 扩大，需人工确认。",
                        )
                    )
        return findings
