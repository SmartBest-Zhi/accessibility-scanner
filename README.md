# App Accessibility Scanner

安卓 App 无障碍（Accessibility）合规扫描平台：上传 APK，在 AVD 中自动安装、
遍历界面并依据 WCAG 相关规则生成检测报告与证据（截图 / UI 层级 / 节点明细）。

> 扫描结果是**人工复核候选**，不是 WCAG 合规结论。

## 项目结构

```
├── frontend/   # Vue 3 + Vite + Ant Design Vue 管理界面
└── backend/    # FastAPI 后端：设备管理（adb/AVD）、扫描规则、ws-scrcpy 实时画面
```

## 功能

- APK 上传与解析（`apkanalyzer`，按 sha256 去重）
- AVD 会话管理（单例），远程实时画面（ws-scrcpy）
- 无障碍规则扫描：
  - WCAG 1.4.4 文字大小自适应（双快照对比法）
  - 通用节点启发式（可访问名称、触控区域 ≥48dp）
- 每次扫描产出证据目录：截图、hierarchy.xml、nodes.json、report.json

## 快速开始

**后端**（详见 [backend/README.md](backend/README.md)）：

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # 按需修改 Android SDK 路径与端口
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**前端**（详见 [frontend/README.md](frontend/README.md)）：

```bash
cd frontend
npm install
npm run dev
```

## 环境要求

- Python 3.12+，Node.js 18+
- Android SDK（`adb` / `emulator` / `apkanalyzer`）与至少一个 AVD
