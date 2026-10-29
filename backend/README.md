# App Accessibility Scanner — 后端

基于 AVD 的安卓 App 无障碍合规测试平台后端（FastAPI）。

## 环境要求

- Python 3.12+
- Android SDK（`adb`、`emulator`、`apkanalyzer`），路径见 `.env` 的 `ANDROID_SDK_ROOT`
- Node.js 18+（ws-scrcpy 需要）
- 至少一个已创建的 AVD（本机默认：`accessibility`）

## 安装

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 按需修改 SDK 路径与端口
```

### ws-scrcpy 一次性安装

```bash
cd backend/tools
git clone https://github.com/NetrisTV/ws-scrcpy.git
cd ws-scrcpy
# 关闭浏览器终端功能：node-pty 0.10 无法在 Node 22 上编译，而我们只需要视频流。
# 把 webpack/default.build.config.json 里的 "INCLUDE_ADB_SHELL" 改为 false（本仓库已改好）。
npm install --ignore-scripts
npm run dist
cd dist && npm install --omit=dev --ignore-scripts
```

> 端口不是命令行参数：后端启动子进程时会写入 `tools/ws-scrcpy/backend.yaml`
> 并通过环境变量 `WS_SCRCPY_CONFIG` 传入，端口来自 `.env` 的 `WS_SCRCPY_PORT`（默认 8100）。
> ws-scrcpy 上游已归档；若 Node 22 下构建失败，请使用 Node 18 运行它。

## 启动

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

预检：浏览器访问 `http://127.0.0.1:8000/api/health`，确认 adb / emulator /
apkanalyzer 均已解析且 `wsscrcpy_installed: true`。

## 目录

- `app/rules/` — 检测规则，每条规则单独一个文件：
  - `text_scale.py` — WCAG 1.4.4 文字大小自适应（双快照对比法）
  - `node_heuristics.py` — 通用节点启发式（ANDROID_NODE_001 可访问名称 / ANDROID_NODE_002 触控区域 ≥48dp）
  新规则实现 `Rule` 协议并在 `app/rules/__init__.py` 的 `RULES` 中注册。
- `uploads/` — 上传的 APK（按 sha256 前缀去重）
- `runs/<session_id>/<scan_id>/` — 每次扫描的证据目录（与参考脚本一致）：
  `device_info.json`、`screenshot.png`、`hierarchy.xml`、`hierarchy-scaled.xml`、
  `nodes.json`、`report.json`（含 summary 与 limitations）

## 说明

- UI 抓取使用纯 adb（`exec-out screencap` + `uiautomator dump`），不依赖 Appium。
- 扫描结果是**人工复核候选**，不是 WCAG 合规结论。
- 检测会话为单例：同时只能有一个 AVD 会话。
- `manual_android_accessibility_scan.py` 为早期 CLI 原型，保留作参考。
