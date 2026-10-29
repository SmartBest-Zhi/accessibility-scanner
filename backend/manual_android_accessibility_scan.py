#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual Android accessibility evidence collector.
Requirements: Python 3.9+ and Android SDK platform-tools (adb).
Does NOT modify the target APK and does NOT run Google's ATF directly.
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

def run(cmd, check=True, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, shell=False)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"Command failed ({p.returncode}): {' '.join(map(str, cmd))}\n"
            f"{p.stdout}\n{p.stderr}".strip()
        )
    return p

def adb_base(serial=None):
    return ["adb"] + (["-s", serial] if serial else [])

def adb(args, serial=None, check=True, timeout=60):
    return run(adb_base(serial) + args, check=check, timeout=timeout)

def devices():
    out = adb(["devices"]).stdout.splitlines()[1:]
    return [line.split()[0] for line in out if "\tdevice" in line]

def require_device(serial=None):
    ds = devices()
    if serial:
        if serial not in ds:
            raise RuntimeError(f"设备 {serial} 不在线。adb devices 当前设备：{ds}")
        return serial
    if not ds:
        raise RuntimeError("没有可用设备。先启动 AVD，再执行 adb devices。")
    if len(ds) > 1:
        raise RuntimeError(f"发现多个设备 {ds}。请使用 --serial 指定，例如 --serial {ds[0]}")
    return ds[0]

def packages(serial):
    out = adb(["shell", "pm", "list", "packages", "-3"], serial).stdout
    return {x.replace("package:", "").strip() for x in out.splitlines() if x.strip()}

def install_apk(apk, serial=None):
    serial = require_device(serial)
    apk = Path(apk).expanduser().resolve()
    if not apk.is_file():
        raise FileNotFoundError(f"APK 不存在：{apk}")
    before = packages(serial)
    print(adb(["install", "-r", str(apk)], serial, timeout=180).stdout.strip())
    after = packages(serial)
    added = sorted(after - before)
    if len(added) == 1:
        print(f"\n新安装包名：{added[0]}")
        print(f"启动命令：python manual_android_accessibility_scan.py launch --package {added[0]}")
    elif added:
        print("\n新出现的第三方包：")
        for p in added:
            print("  " + p)
        print("请用 info 子命令确认目标包名。")
    else:
        print("\n没有检测到新包（可能是覆盖安装）。请执行 info 查看包名。")

def package_info(package, serial=None):
    serial = require_device(serial)
    result = adb(["shell", "dumpsys", "package", package], serial, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"找不到包 {package}。请先安装 APK，并确认包名。")
    print(f"包名：{package}")
    for line in result.stdout.splitlines():
        s = line.strip()
        if s.startswith(("versionCode=", "versionName=", "firstInstallTime=", "lastUpdateTime=")):
            print(s)
    print("\n当前前台 Activity：")
    print(adb(["shell", "dumpsys", "activity", "activities"], serial).stdout[-3500:])

def launch(package, serial=None):
    serial = require_device(serial)
    print(adb(["shell", "monkey", "-p", package, "-c",
               "android.intent.category.LAUNCHER", "1"], serial, timeout=60).stdout.strip())
    time.sleep(2)
    print("已发送启动请求。请在模拟器中确认 App 是否正常打开。")

def screen_density(serial=None):
    out = adb(["shell", "wm", "density"], serial, check=False).stdout
    m = re.search(r"(?:Override|Physical) density:\s*(\d+)", out)
    if m:
        return int(m.group(1)) / 160.0
    # Fallback to emulator default; report it so the user can adjust if needed.
    return 1.0

def screen_size(serial=None):
    out = adb(["shell", "wm", "size"], serial, check=False).stdout
    m = re.search(r"(?:Override|Physical) size:\s*(\d+)x(\d+)", out)
    return [int(m.group(1)), int(m.group(2))] if m else None

def parse_bounds(value):
    m = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value or "")
    return tuple(map(int, m.groups())) if m else None

def analyze_xml(xml_path, density):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    nodes = []
    findings = []
    for idx, el in enumerate(root.iter("node")):
        a = el.attrib
        bounds = parse_bounds(a.get("bounds", ""))
        text = (a.get("text") or "").strip()
        desc = (a.get("content-desc") or "").strip()
        clickable = a.get("clickable") == "true"
        long_clickable = a.get("long-clickable") == "true"
        focusable = a.get("focusable") == "true"
        visible = a.get("visible-to-user", "true") == "true"
        item = {
            "index": idx, "class": a.get("class"), "resource_id": a.get("resource-id"),
            "text": text, "content_desc": desc, "clickable": clickable,
            "long_clickable": long_clickable, "focusable": focusable,
            "enabled": a.get("enabled"), "visible_to_user": visible,
            "bounds": a.get("bounds"), "checked": a.get("checked"),
            "selected": a.get("selected")
        }
        nodes.append(item)
        if not visible:
            continue
        label = text or desc
        if (clickable or long_clickable) and not label:
            findings.append({
                "rule_id": "ANDROID_NODE_001",
                "severity": "warning",
                "title": "可交互节点可能缺少可访问名称",
                "evidence": f"节点 {idx} 是 clickable/long-clickable，但 text 和 content-desc 均为空",
                "node": item,
                "confidence": "medium",
                "note": "需结合屏幕视觉、父子节点和 TalkBack 实际朗读人工复核。"
            })
        if bounds and (clickable or long_clickable):
            x1, y1, x2, y2 = bounds
            width_dp = (x2 - x1) / density
            height_dp = (y2 - y1) / density
            if width_dp < 48 or height_dp < 48:
                findings.append({
                    "rule_id": "ANDROID_NODE_002",
                    "severity": "warning",
                    "title": "可交互节点触控区域可能小于 48dp",
                    "evidence": f"节点 {idx} 的边界约为 {width_dp:.1f} × {height_dp:.1f} dp",
                    "node": item,
                    "confidence": "medium",
                    "note": "这是启发式检查；可点击区域可能由父节点或自定义 View 扩大，需人工确认。"
                })
    return nodes, findings

def capture(name=None, outdir="scan_results", serial=None, package=None):
    serial = require_device(serial)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name or "screen")
    folder = Path(outdir).expanduser().resolve() / f"{stamp}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)

    info = {
        "captured_at": dt.datetime.now().astimezone().isoformat(),
        "device_serial": serial,
        "package": package,
        "screen_size_px": screen_size(serial),
        "density_scale": screen_density(serial),
    }
    (folder / "device_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    # Capture screenshot via a device-side file so binary PNG bytes are preserved on Windows.
    remote_shot = "/sdcard/accessibility_scan_screenshot.png"
    adb(["shell", "screencap", "-p", remote_shot], serial, timeout=30)
    adb(["pull", remote_shot, str(folder / "screenshot.png")], serial, timeout=30)

    # Dump the currently exposed UI/accessibility hierarchy.
    remote = "/sdcard/window_dump.xml"
    dump = adb(["shell", "uiautomator", "dump", remote], serial, check=False, timeout=60)
    pull = adb(["pull", remote, str(folder / "hierarchy.xml")], serial, check=False, timeout=60)
    xml_file = folder / "hierarchy.xml"
    report = {
        **info,
        "capture_name": safe_name,
        "screenshot": "screenshot.png",
        "hierarchy": "hierarchy.xml" if xml_file.exists() else None,
        "uiautomator_dump_message": (dump.stdout + "\n" + dump.stderr).strip(),
        "findings": [],
        "summary": {"node_count": 0, "finding_count": 0},
        "limitations": [
            "这是基于当前可访问性节点 XML 的启发式检查，不是 Google ATF 的执行结果。",
            "WebView、Canvas、自绘控件或未暴露给无障碍服务的内容可能无法完整出现在 XML 中。",
            "不能仅凭本报告宣称符合或不符合完整 WCAG 2.2。"
        ]
    }
    if xml_file.exists() and xml_file.stat().st_size > 0:
        try:
            nodes, findings = analyze_xml(xml_file, info["density_scale"])
            report["summary"] = {"node_count": len(nodes), "finding_count": len(findings)}
            report["findings"] = findings
            (folder / "nodes.json").write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            report["xml_parse_error"] = str(e)
    else:
        report["xml_parse_error"] = "没有取得 hierarchy.xml；页面可能不支持 dump、设备命令失败或界面仍在加载。"
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存证据：{folder}")
    print(f"截图：{folder / 'screenshot.png'}")
    print(f"节点 XML：{folder / 'hierarchy.xml'}")
    print(f"报告：{folder / 'report.json'}")
    print(f"节点数：{report['summary']['node_count']}；启发式问题数：{report['summary']['finding_count']}")
    if report.get("xml_parse_error"):
        print("XML 提示：" + report["xml_parse_error"])
    return folder

def main():
    parser = argparse.ArgumentParser(description="手动 Android 无障碍扫描证据采集器（ADB + XML + 启发式规则）")
    parser.add_argument("--serial", help="ADB 设备序列号；多个设备时必填")
    sub = parser.add_subparsers(dest="command", required=True)
    p_install = sub.add_parser("install", help="安装 APK 并尝试识别新包名")
    p_install.add_argument("--apk", required=True)
    p_info = sub.add_parser("info", help="查看目标包的版本信息和 Activity 状态")
    p_info.add_argument("--package", required=True)
    p_launch = sub.add_parser("launch", help="启动目标 App")
    p_launch.add_argument("--package", required=True)
    p_capture = sub.add_parser("capture", help="为当前屏幕保存截图、XML 和 JSON 报告")
    p_capture.add_argument("--name", default="screen")
    p_capture.add_argument("--outdir", default="scan_results")
    p_capture.add_argument("--package")
    p_session = sub.add_parser("session", help="手动操作 App，每按一次回车采集一个页面；输入 q 退出")
    p_session.add_argument("--package")
    p_session.add_argument("--outdir", default="scan_results")
    args = parser.parse_args()
    try:
        require_device(args.serial)
        if args.command == "install":
            install_apk(args.apk, args.serial)
        elif args.command == "info":
            package_info(args.package, args.serial)
        elif args.command == "launch":
            launch(args.package, args.serial)
        elif args.command == "capture":
            capture(args.name, args.outdir, args.serial, args.package)
        elif args.command == "session":
            print("请在模拟器中手动操作 App。到达一个需要检查的页面后回到此终端按回车采集。输入 q 退出。")
            while True:
                value = input("页面名称（回车使用默认名称，q 退出）：").strip()
                if value.lower() == "q":
                    break
                capture(value or "screen", args.outdir, args.serial, args.package)
    except KeyboardInterrupt:
        print("\n已停止。")
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
