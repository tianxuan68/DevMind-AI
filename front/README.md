# front（DevMind-AI 前端）

React + Vite 实现，对接 `backend` 服务的接口。

## 功能

- 账号密码登录 / 注册 / 手机验证码登录
- 智能问答：调用后端 FAQ 搜索（后端内部使用 Redis 缓存）
- 高频 FAQ 列表与详情
- 知识库文档列表与详情
- 当前用户信息与退出登录

## 启动

```powershell
cd E:\tianxuan\DevMind-AI\front
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。

后端地址默认 `http://127.0.0.1:8004`，可通过 `front/.env` 配置：

```text
VITE_API_BASE_URL=http://127.0.0.1:8004
```
