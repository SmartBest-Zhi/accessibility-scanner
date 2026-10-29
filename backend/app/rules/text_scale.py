"""WCAG 1.4.4 Resize text — Android 系统字体缩放自适应规则（单独文件维护）。

双快照探测：先在设备当前（正常）字号下抓取一次 UI 层级，再把
``system font_scale`` 调到测试值抓第二次，逐节点对比：

* ``TEXT_SCALE_NO_RESIZE``      — 文本节点高度几乎未增长（< 1.1x）。
  文字大小很可能写死为 dp（或被 maxLines/固定布局裁剪），未跟随系统字号（sp）。
* ``TEXT_SCALE_PARTIAL_RESIZE`` — 高度有增长但明显小于缩放系数，可能部分裁剪。
* ``TEXT_SCALE_TRUNCATED``      — 放大后文本出现省略号截断，信息可能丢失。
* ``TEXT_SCALE_NODE_MISSING``   — 正常字号下存在的文本节点放大后消失，
  内容可能被挤出屏幕或被裁剪。

所有结论均为**人工复核候选**而非 WCAG 判定：WebView / React Native / 自绘
控件本就不跟随系统字号，动态内容（计时器、动画）也会干扰节点匹配。

设备 font_scale 始终在 ``finally`` 中恢复。
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

from ..config import get_settings
from ..services import capture
from .base import CaptureContext, make_finding, parse_bounds

_SCALE_SETTLE_S = 2.5
_NO_RESIZE_RATIO = 1.1
_TEXT_CLASSES = ("textview", "button", "edittext")


def _is_text_node(node: ET.Element) -> bool:
    if (node.attrib.get("text") or "").strip():
        return True
    class_name = node.attrib.get("class", "").lower()
    return any(marker in class_name for marker in _TEXT_CLASSES)


def _index_text_nodes(root: ET.Element, app_package: str | None) -> dict[tuple, dict[str, Any]]:
    """Index text-bearing nodes by a stable key (resource-id preferred)."""
    indexed: dict[tuple, dict[str, Any]] = {}
    occurrences: dict[tuple, int] = {}
    for node in root.iter():
        if not _is_text_node(node):
            continue
        if app_package and node.attrib.get("package") not in (None, app_package):
            continue
        resource_id = node.attrib.get("resource-id") or ""
        class_name = node.attrib.get("class", "")
        text = (node.attrib.get("text") or "").strip()
        base_key = (resource_id,) if resource_id else (class_name, text)
        occurrence = occurrences.get(base_key, 0)
        occurrences[base_key] = occurrence + 1
        indexed[(base_key, occurrence)] = {
            "class_name": class_name,
            "resource_id": resource_id,
            "text": text,
            "bounds": parse_bounds(node.attrib.get("bounds")),
        }
    return indexed


def _height(bounds: list[int] | None) -> int | None:
    if not bounds:
        return None
    height = bounds[3] - bounds[1]
    return height if height > 0 else None


class TextScaleRule:
    rule_id = "WCAG_1_4_4_TEXT_SCALE"
    title = "文字大小自适应（WCAG 1.4.4 Resize text）"

    def check(self, ctx: CaptureContext) -> list[dict[str, Any]]:
        settings = get_settings()
        test_scale = settings.FONT_SCALE_TEST_VALUE

        try:
            root_normal = ET.fromstring(ctx.xml_normal_path.read_text(encoding="utf-8"))
        except ET.ParseError as exc:
            return [
                make_finding(
                    "SCAN_XML_PARSE_ERROR",
                    "无法解析 UI 层级 XML",
                    f"正常字号快照解析失败：{exc}",
                    severity="error",
                    confidence="high",
                    note="截图已保存，可人工复核当前页面。",
                )
            ]

        scale_before = capture.get_font_scale(ctx.udid)
        if scale_before >= test_scale:
            return [
                make_finding(
                    "TEXT_SCALE_SKIPPED",
                    "设备已处于大字体模式，跳过文字缩放探测",
                    f"当前 font_scale={scale_before} ≥ 测试值 {test_scale}，未修改系统设置。",
                    severity="info",
                    confidence="high",
                )
            ]

        xml_scaled_path = ctx.scan_dir / "hierarchy-scaled.xml"
        try:
            capture.set_font_scale(ctx.udid, test_scale)
            time.sleep(_SCALE_SETTLE_S)  # re-layout is asynchronous
            xml_scaled_path.write_text(capture.dump_ui_xml(ctx.udid), encoding="utf-8")
        except Exception as exc:
            return [
                make_finding(
                    "TEXT_SCALE_PROBE_FAILED",
                    "大字体快照获取失败",
                    f"{exc}",
                    severity="error",
                    confidence="high",
                    note="正常字号截图仍可人工复核。",
                )
            ]
        finally:
            try:
                capture.set_font_scale(ctx.udid, scale_before)
                time.sleep(1)
            except Exception:
                pass

        try:
            root_scaled = ET.fromstring(xml_scaled_path.read_text(encoding="utf-8"))
        except ET.ParseError as exc:
            return [
                make_finding(
                    "SCAN_XML_PARSE_ERROR",
                    "无法解析 UI 层级 XML",
                    f"大字体快照解析失败：{exc}",
                    severity="error",
                    confidence="high",
                )
            ]

        normal_nodes = _index_text_nodes(root_normal, ctx.app_package)
        scaled_nodes = _index_text_nodes(root_scaled, ctx.app_package)

        findings: list[dict[str, Any]] = []
        for key, node_a in normal_nodes.items():
            node_b = scaled_nodes.get(key)
            node_info = {
                "class_name": node_a["class_name"],
                "resource_id": node_a["resource_id"],
                "text": node_a["text"],
                "bounds_normal": node_a["bounds"],
                "bounds_scaled": node_b["bounds"] if node_b else None,
            }

            if node_b is None:
                findings.append(
                    make_finding(
                        "TEXT_SCALE_NODE_MISSING",
                        "放大字体后该文本节点消失",
                        f"文本「{node_a['text'][:30]}」在 font_scale={test_scale} 下未在 UI 层级中找到",
                        node_info,
                        note="内容可能被挤出屏幕或被裁剪；动态内容也可能导致误报，请人工复核。",
                    )
                )
                continue

            text_a, text_b = node_a["text"], node_b["text"]
            if text_a and text_b.endswith("…") and not text_a.endswith("…"):
                findings.append(
                    make_finding(
                        "TEXT_SCALE_TRUNCATED",
                        "放大字体后文本被省略号截断",
                        f"放大后文本变为「{text_b}」，原始内容被截断",
                        node_info,
                        note="信息可能丢失，请人工复核完整内容是否仍可获得。",
                    )
                )
                continue

            height_a = _height(node_a["bounds"])
            height_b = _height(node_b["bounds"])
            if not height_a or not height_b or not text_a:
                continue
            ratio = round(height_b / height_a, 2)
            node_info["height_ratio"] = ratio

            if ratio < _NO_RESIZE_RATIO:
                findings.append(
                    make_finding(
                        "TEXT_SCALE_NO_RESIZE",
                        "文本高度未随系统字体放大",
                        f"font_scale 调至 {test_scale} 后该文本高度几乎不变（×{ratio}）",
                        node_info,
                        note="文字大小可能写死为 dp 而非 sp，或被固定高度裁剪，疑似不满足 WCAG 1.4.4，请人工复核。",
                    )
                )
            elif ratio < test_scale - 0.1:
                findings.append(
                    make_finding(
                        "TEXT_SCALE_PARTIAL_RESIZE",
                        "文本放大幅度明显小于系统字号比例",
                        f"font_scale ×{test_scale}，文本高度仅 ×{ratio}",
                        node_info,
                        note="可能存在部分裁剪，请人工复核。",
                    )
                )

        return findings
