"""扫描编排：截图 + UI XML + 规则执行 + 证据落盘。

每次扫描产出一个独立证据目录，内容与参考脚本
manual_android_accessibility_scan(2).py 的 capture 保持一致：

    runs/<session_id>/<scan_id>/
      device_info.json      # captured_at / device_serial / package / screen_size_px / density_scale
      screenshot.png        # 正常字号截图（前端浮动标注叠加在此图上）
      hierarchy.xml         # 正常字号 UI 层级
      hierarchy-scaled.xml  # font_scale=1.3 时的 UI 层级（文字缩放规则产生）
      nodes.json            # 结构化节点列表
      report.json           # findings + summary + limitations
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..rules import RULES, CaptureContext
from ..rules.node_heuristics import parse_nodes
from . import capture

if TYPE_CHECKING:
    from ..state import Session

LIMITATIONS = [
    "这是基于当前可访问性节点 XML 的启发式检查，不是 Google ATF 的执行结果。",
    "WebView、Canvas、自绘控件或未暴露给无障碍服务的内容可能无法完整出现在 XML 中。",
    "不能仅凭本报告宣称符合或不符合完整 WCAG 2.2。",
]


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def perform_scan(session: "Session", label: str) -> dict[str, Any]:
    """Run one scan against the live session device. Blocking — call in a thread."""
    if not session.udid:
        raise RuntimeError("Session has no online device.")

    scan_id = f"screen-{len(session.scans) + 1:03d}"
    scan_dir = session.run_dir / scan_id
    scan_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path = scan_dir / "screenshot.png"
    xml_normal_path = scan_dir / "hierarchy.xml"

    # 设备信息（与参考脚本的 device_info.json 一致）
    density_dpi = capture.read_density_dpi(session.udid)
    density_scale = (density_dpi or 160) / 160.0
    size = capture.read_screen_size(session.udid)
    info: dict[str, Any] = {
        "captured_at": now_iso(),
        "device_serial": session.udid,
        "package": session.apk_metadata.get("application_id"),
        "screen_size_px": size,
        "density_scale": density_scale,
    }
    _write_json(scan_dir / "device_info.json", info)

    # 截图（exec-out，二进制安全）
    capture.capture_screenshot(session.udid, screenshot_path)

    # UI 层级 dump
    dump_message = ""
    xml_ok = False
    try:
        xml_normal_path.write_text(capture.dump_ui_xml(session.udid), encoding="utf-8")
        dump_message = "UI hierchary dumped OK"
        xml_ok = True
    except Exception as exc:
        dump_message = str(exc)
        xml_normal_path.write_text(
            f"<!-- UI hierarchy capture failed: {exc} -->\n", encoding="utf-8"
        )

    package, activity = capture.current_focus(session.udid)

    # 节点解析 + 规则执行
    findings: list[dict[str, Any]] = []
    node_count = 0
    xml_parse_error: str | None = None
    if xml_ok:
        try:
            nodes = parse_nodes(xml_normal_path)
            node_count = len(nodes)
            _write_json(scan_dir / "nodes.json", nodes)
        except Exception as exc:
            xml_parse_error = str(exc)
            nodes = []
        if xml_parse_error is None:
            ctx = CaptureContext(
                udid=session.udid,
                scan_id=scan_id,
                scan_dir=scan_dir,
                screenshot_path=screenshot_path,
                xml_normal_path=xml_normal_path,
                density_dpi=density_dpi,
                app_package=session.apk_metadata.get("application_id"),
            )
            for rule in RULES:
                try:
                    findings.extend(rule.check(ctx))
                except Exception as exc:
                    findings.append(
                        {
                            "rule_id": getattr(rule, "rule_id", "UNKNOWN_RULE"),
                            "severity": "error",
                            "title": f"规则执行异常：{getattr(rule, 'title', rule)}",
                            "evidence": str(exc),
                            "node": {},
                            "confidence": "high",
                            "note": "规则自身报错，不代表被测应用的问题。",
                        }
                    )
    else:
        xml_parse_error = (
            "没有取得 hierarchy.xml；页面可能不支持 dump、设备命令失败或界面仍在加载。"
        )
        findings.append(
            {
                "rule_id": "SCAN_UI_HIERARCHY_CAPTURE_FAILED",
                "severity": "error",
                "title": "UI 层级获取失败",
                "evidence": dump_message,
                "node": {},
                "confidence": "high",
                "note": "截图已保存，可人工复核当前页面。",
            }
        )

    # 与参考脚本一致的 report.json
    report = {
        **info,
        "capture_name": label or scan_id,
        "screenshot": "screenshot.png",
        "hierarchy": "hierarchy.xml" if xml_ok else None,
        "uiautomator_dump_message": dump_message,
        "findings": findings,
        "summary": {"node_count": node_count, "finding_count": len(findings)},
        "limitations": LIMITATIONS,
    }
    if xml_parse_error:
        report["xml_parse_error"] = xml_parse_error
    _write_json(scan_dir / "report.json", report)

    png = capture.png_size(screenshot_path)
    scan: dict[str, Any] = {
        "scan_id": scan_id,
        "label": label,
        "captured_at": info["captured_at"],
        "screenshot_url": f"/api/session/scans/{scan_id}/screenshot",
        "image_width": png[0] if png else None,
        "image_height": png[1] if png else None,
        "current_package": package,
        "current_activity": activity,
        "node_count": node_count,
        "finding_count": len(findings),
        "ui_hierarchy_capture_error": None if xml_ok else dump_message,
        "limitations": LIMITATIONS,
        "findings": findings,
    }
    session.scans.append(scan)
    return scan
