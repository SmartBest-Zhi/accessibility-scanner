# App Accessibility Scanner — 前端

基于 Vue 3 + Vite + Ant Design Vue 的扫描平台管理界面。

## 环境要求

- Node.js 18+

## 安装与启动

```bash
cd frontend
npm install
npm run dev
```

默认通过 Vite 代理访问后端（`http://127.0.0.1:8000`），请先启动后端，
见 [backend/README.md](../backend/README.md)。

## 构建

```bash
npm run build     # 类型检查（vue-tsc）+ 产物构建
npm run preview   # 本地预览构建产物
```

## 主要页面

- `src/view/AccessibilityTest/` — 无障碍扫描：APK 上传、扫描控制、报告与证据查看
- `src/view/AdminHome/`、`src/view/UserMgt/` — 管理后台首页与用户管理
- `src/view/Login/` — 登录

组件库参考：https://www.antdv.com/components/overview-cn
