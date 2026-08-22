# backend（DevMind-AI 后端服务）

FastAPI + aiomysql + Redis + PyJWT。

## 功能

- 用户注册 / 登录 / 手机验证码 / 退出登录（JWT）
- 知识库文档查看（列表/详情）
- 高频 FAQ 查看（列表/详情/问题搜索）
- Redis 单独 db 缓存用户问题，解决缓存穿透/雪崩/击穿
  - db 1：短信验证码
  - db 2：用户问题缓存（空值短 TTL + 随机 TTL + Redis 锁指数退避）
  - db 3：JWT 黑名单

## 启动

```powershell
cd E:\tianxuan\DevMind-AI\backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
```

先执行根目录 `sql/schema.sql` 初始化数据库。

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/send-code | 发送手机验证码 |
| POST | /api/auth/register | 注册 |
| POST | /api/auth/login | 账号密码登录 |
| POST | /api/auth/login/sms | 手机验证码登录 |
| POST | /api/auth/logout | 退出登录 |
| GET | /api/user/me | 当前用户 |
| GET | /api/knowledge/docs | 知识库文档列表 |
| GET | /api/knowledge/docs/{id} | 文档详情 |
| GET | /api/faq | FAQ 列表 |
| GET | /api/faq/{id} | FAQ 详情 |
| POST | /api/faq/search | 用户问题搜索（走 Redis 缓存） |
