 # DevMind-AI Docker 生产部署手册

> 适用场景：Linux 服务器（推荐 Ubuntu 22.04+ / CentOS 7+），Docker 运行 MySQL / Redis / Milvus，Nginx 托管前端静态资源，宿主机或 Docker 运行后端 API（8004）。

**生产服务器**：`8.211.188.59`

| 访问项 | 地址 |
|--------|------|
| 前端 | http://8.211.188.59/ |
| 健康检查 | http://8.211.188.59/health |
| API（经 Nginx 反代） | http://8.211.188.59/api/ |
| Locust 压测 UI | http://8.211.188.59:8089 |

## 流程自检清单（部署前）

| 模块 | 状态 | 说明 |
|------|------|------|
| 基础设施 | Docker Compose | MySQL / Redis / Milvus / etcd / MinIO |
| 后端 API | FastAPI 8004 | 用户、知识库、FAQ、检索 |
| 前端 | Vite 构建 + Nginx | 静态站点 + `/api` 反代 |
| 向量检索 | BGE-M3 + Milvus | 模型需单独下载（约 2GB+） |
| 单元测试 | `pytest tests/unit` | 当前 23 项通过 |

默认测试账号：`admin` / `123456`（仅开发/内网验收，生产请修改）。

---

## 3.1 第一步：打包

### 3.1.1 打包前端

```bash
cd front
npm ci
npm run build
# 产物目录：front/dist/
```

Windows PowerShell：

```powershell
cd front
npm ci
npm run build
```

生产环境 API 地址在构建时注入（Nginx 同域反代可留空）：

```bash
# 若 API 与前端不同域，构建前创建 front/.env.production：
echo 'VITE_API_BASE_URL=' > front/.env.production
```

### 3.1.2 打包后端（zip）

> **Windows 注意**：PowerShell 默认没有 `zip` 命令，请用下方 **PowerShell 脚本** 或 **`tar`**，不要直接复制 Linux 的 `zip -r` 命令。

**方式一：一键脚本（推荐）**

Linux / macOS / WSL：

```bash
chmod +x scripts/pack-release.sh
./scripts/pack-release.sh
```

Windows（在项目根目录执行）：

```powershell
cd E:\tianxuan\DevMind-AI
powershell -ExecutionPolicy Bypass -File .\scripts\pack-release.ps1
```

仅打包后端（跳过前端构建，适合已 `npm run build` 过）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pack-backend.ps1
```

输出目录：`dist/release/devmind-ai-frontend-*.zip`、`dist/release/devmind-ai-backend-*.zip`

**方式二：手动打包（Linux / macOS / WSL）**

```bash
cd /path/to/DevMind-AI
mkdir -p dist/release
DATE_TAG=$(date +%Y%m%d_%H%M%S)
zip -r "dist/release/devmind-ai-backend-${DATE_TAG}.zip" \
  backend base internal_kb_qa config.ini pyproject.toml uv.lock sql docker scripts locust_test.py \
  -x "**/__pycache__/*" "**/*.pyc" "**/.venv/*" "**/node_modules/*" "**/data/uploads/*" "**/logs/*" "**/.git/*" "**/internal_kb_qa/models/*"
```

**方式三：手动打包（Windows，无需安装 zip）**

Windows 10/11 自带 `tar`（推荐，内存占用低；**自动排除 models 目录**）：

```powershell
cd E:\tianxuan\DevMind-AI
$tag = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path dist\release | Out-Null
tar -a -cf "dist\release\devmind-ai-backend-$tag.zip" `
  --exclude=internal_kb_qa/models `
  --exclude=**/__pycache__ `
  backend base internal_kb_qa config.ini pyproject.toml uv.lock sql docker scripts locust_test.py
```

或使用项目脚本（同上逻辑）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pack-backend.ps1
```

> **为何排除 `internal_kb_qa/models/`？** 本地模型约 4GB+，打进 zip 会极慢且易内存溢出；请在服务器上用 `download_models` 下载（见 §3.4）。

---

## 3.2 第二步：上传

### 3.2.1 上传命令

在**本地开发机**执行，将 zip 传到服务器 `/opt/`：

```bash
scp dist/release/devmind-ai-frontend-*.zip root@8.211.188.59:/opt/
scp dist/release/devmind-ai-backend-*.zip root@8.211.188.59:/opt/
```

上传完成后，服务器 `/opt/` 应类似：

```
/opt/
├── devmind-ai/                              # 部署目录（可先 mkdir，解压时也会写入）
├── devmind-ai-frontend-20260824_072605.zip
└── devmind-ai-backend-20260824_072605.zip
```

> 日期后缀以你本地打包时间为准，每次打包都会变。

### 3.2.2 解压文件

登录服务器后操作（**全程使用绝对路径，不要 `cd /opt` 后用相对路径 `front/dist`**）：

```bash
ssh root@8.211.188.59

# 0. 依赖（若无 unzip）
yum install -y unzip    # CentOS / Aliyun Linux
# apt install -y unzip  # Ubuntu / Debian

# 1. 创建目标目录（必须，否则会报 cannot create extraction directory）
mkdir -p /opt/devmind-ai/front/dist

# 2. 确认 zip 存在
ls -lh /opt/devmind-ai-frontend-*.zip /opt/devmind-ai-backend-*.zip
```

**方式 A：文件名已知时（推荐，最不易错）**

将下方日期后缀 `20260824_072605` 换成你 `ls` 看到的实际文件名：

```bash
FRONT_ZIP=/opt/devmind-ai-frontend-20260824_072605.zip
BACKEND_ZIP=/opt/devmind-ai-backend-20260824_072605.zip

unzip -o "$FRONT_ZIP" -d /opt/devmind-ai/front/dist
unzip -o "$BACKEND_ZIP" -d /opt/devmind-ai
```

**方式 B：自动选 /opt 下最新一份 zip**

仅当 `/opt` 里**每种各只有一份** zip 时使用；若有多份旧包，请用方式 A 或先删除旧 zip：

```bash
FRONT_ZIP=$(ls -t /opt/devmind-ai-frontend-*.zip 2>/dev/null | head -1)
BACKEND_ZIP=$(ls -t /opt/devmind-ai-backend-*.zip 2>/dev/null | head -1)

echo "frontend: $FRONT_ZIP"
echo "backend:  $BACKEND_ZIP"

unzip -o "$FRONT_ZIP" -d /opt/devmind-ai/front/dist
unzip -o "$BACKEND_ZIP" -d /opt/devmind-ai
```

**验证解压结果：**

```bash
ls /opt/devmind-ai/front/dist/index.html
ls /opt/devmind-ai/backend/app/main.py
ls /opt/devmind-ai/config.ini /opt/devmind-ai/docker/docker-compose.yml
```

解压后目录结构：

```
/opt/devmind-ai/
├── backend/
├── base/
├── internal_kb_qa/
├── config.ini
├── docker/
├── front/dist/index.html    ← 前端静态页
├── pyproject.toml
└── uv.lock
```

**常见报错：**

| 报错 | 原因 | 处理 |
|------|------|------|
| `cannot create extraction directory: front/dist` | 未 `mkdir -p`，或在 `/opt` 下用了相对路径 | `mkdir -p /opt/devmind-ai/front/dist`，`-d` 写绝对路径 |
| `filename not matched` | 同一 glob 匹配到多个 zip | 用方式 A 指定完整文件名，或 `rm` 删除旧 zip 只留最新一份 |
| `unzip: command not found` | 未安装 unzip | `yum install -y unzip` |

**可选：解压后归档 zip（节省磁盘）**

```bash
mkdir -p /opt/devmind-ai/archives
mv /opt/devmind-ai-frontend-*.zip /opt/devmind-ai-backend-*.zip /opt/devmind-ai/archives/
```

---

## 3.3 第三步：安装配置 Nginx

### 3.3.1 安装命令

**Ubuntu / Debian：**

```bash
sudo apt update
sudo apt install -y nginx
```

**CentOS / RHEL：**

```bash
sudo yum install -y epel-release
sudo yum install -y nginx
sudo systemctl enable nginx
```

### 3.3.2 修改配置文件

```bash
sudo cp /opt/devmind-ai/docker/nginx/devmind.conf /etc/nginx/conf.d/devmind.conf
# server_name 已配置为 8.211.188.59；root 默认 /opt/devmind-ai/front/dist
sudo nginx -t
```

### 3.3.3 保存并重启

```bash
sudo systemctl enable nginx
sudo systemctl restart nginx
sudo systemctl status nginx
```

---

## 3.4 第四步：下载需要的模型

模型需放在 `internal_kb_qa/models/` 下：

| 目录 | 用途 |
|------|------|
| `internal_kb_qa/models/bge-m3` | 向量嵌入 |
| `internal_kb_qa/models/bge-reranker-v2-m3` | 精排（可选，低内存环境建议关闭） |

### 3.4.1 下载命令

> **Python 版本**：须使用 **3.12 或 3.13**。勿用 3.14（`unstructured` → `spacy` 尚无 cp314 wheel，会导致 `uv sync` 失败）。Docker 镜像与 `.python-version` 已固定为 3.12。

```bash
cd /opt/devmind-ai

# 安装 uv 与 Python 3.12（若尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv python install 3.12

# 若曾用 3.14 创建过 .venv，先删除再同步
rm -rf .venv
uv sync --python 3.12

# 下载全部模型（HuggingFace / ModelScope 自动回退）
uv run python -m internal_kb_qa.scripts.download_models all

# 或单独下载
uv run python -m internal_kb_qa.scripts.download_models bge-m3
uv run python -m internal_kb_qa.scripts.download_models bge-reranker-v2-m3
```

国内服务器可设置镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

---

## 3.5 第五步：配置环境变量

### 3.5.1 配置命令

**1）启动 Docker 基础设施：**

```bash
cd /opt/devmind-ai/docker
cp .env.example .env
# 编辑 .env 修改 MYSQL_ROOT_PASSWORD 等
docker compose up -d
docker compose ps
```

**2）后端环境变量：**

```bash
cp /opt/devmind-ai/backend/.env.example /opt/devmind-ai/backend/.env
vi /opt/devmind-ai/backend/.env
```

生产最小配置示例：

```ini
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=<你的密码>
MYSQL_DATABASE=internal_tech_kb

REDIS_HOST=127.0.0.1
REDIS_PORT=16379

JWT_SECRET=<至少32位随机字符串>
APP_DEBUG=false

# OSS（文档直传；OSS_ENABLED=true 时必填，凭证仅走环境变量）
OSS_ENABLED=true
OSS_ACCESS_KEY_ID=<你的 RAM AccessKey ID>
OSS_ACCESS_KEY_SECRET=<你的 RAM AccessKey Secret>

# DashScope（Query 改写 / 意图分类 / RAG；建议生产配置）
DASHSCOPE_API_KEY=<你的百炼 API Key>
```

> 敏感凭证（`OSS_ACCESS_KEY_*`、`DASHSCOPE_API_KEY`）**只写在 `backend/.env`**，由 systemd `EnvironmentFile` 或 Docker `env_file` 注入，不要写入 `config.ini` 或提交仓库。

**3）同步 `config.ini` 中 MySQL/Redis/Milvus 地址与端口。**

> 注意：Docker 映射 Redis 为 `16379:6379`，宿主机连接用 `16379`；容器内互联用 `6379`。

---

## 3.6 第六步：运行启动

### 3.6.1 运行项目

**方式 A：宿主机运行后端（推荐，便于调试模型）**

```bash
cd /opt/devmind-ai
uv sync
export OMP_NUM_THREADS=1
export RETRIEVAL_WARMUP=false

# 前台启动（验证）
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8004

# 或使用 systemd 守护（推荐生产）
sudo cp docker/systemd/devmind-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable devmind-backend
sudo systemctl start devmind-backend
sudo systemctl status devmind-backend
```

**方式 B：Docker 运行后端**

```bash
cd /opt/devmind-ai/docker
docker compose -f docker-compose.yml -f docker-compose.app.yml up -d --build
```

**导入知识库文档（可选）：**

```bash
cd /opt/devmind-ai
uv run python -m internal_kb_qa.scripts.ingest_documents --dir internal_kb_qa/data/raw
```

访问地址：

- 前端：http://8.211.188.59/
- API 文档：http://8.211.188.59/api/ → 反代到 `http://127.0.0.1:8004`
- 健康检查：http://8.211.188.59/health

---

## 3.7 第七步：测试系统功能

### 3.7.1 测试步骤

```bash
# 1. 基础设施
docker compose -f /opt/devmind-ai/docker/docker-compose.yml ps

# 2. 后端健康
curl http://127.0.0.1:8004/health

# 3. 登录
curl -X POST http://127.0.0.1:8004/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"account":"admin","password":"123456"}'

# 4. FAQ 问答
TOKEN=<上一步 access_token>
curl -X POST http://127.0.0.1:8004/api/faq/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"生产环境如何配置统一身份认证？"}'

# 5. 检索测试（首次约 15s 加载模型）
curl -X POST http://127.0.0.1:8004/api/knowledge/retrieval/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Milvus","top_k":5,"use_rerank":false,"use_llm_rewrite":false}'

# 6. 浏览器验收
# - 打开 http://8.211.188.59/ 登录
# - 工作台提问、知识库上传、检索测试页运行检索

# 7. 外网验收（在本地电脑执行）
curl http://8.211.188.59/health
```

---

## 3.8 第八步：系统压力测试

### 3.8.1 压力测试步骤

使用项目内置 Locust 脚本：

```bash
cd /opt/devmind-ai
uv sync

# Web UI 模式（浏览器打开 http://8.211.188.59:8089）
uv run locust -f locust_test.py --host http://127.0.0.1:8004 --web-host 0.0.0.0

# 无 UI 压测示例：50 并发，持续 2 分钟
uv run locust -f locust_test.py --host http://127.0.0.1:8004 \
  --headless -u 50 -r 5 --run-time 2m \
  --csv=dist/locust_report
```

验收参考：

- 健康检查 `/health`：p95 < 200ms
- FAQ `/api/faq/search`：p95 < 1s（缓存命中）
- 检索 `/api/knowledge/retrieval/search`：p95 < 15s（首次加载模型后）

低内存服务器（<16GB）压测时务必关闭精排（`use_rerank: false`）。

> **安全组**：阿里云控制台需放行 `80`（Nginx）、`8089`（Locust UI，可选）、`22`（SSH）。后端 `8004` 仅本机监听，无需对外暴露。

---

## 附录 A：常见问题

| 现象 | 处理 |
|------|------|
| 问答/检索 HTTP 500 | 检查 `systemctl status devmind-backend`；查看 `logs/backend.log` |
| 检索中文无结果 | 确认 `internal_kb_qa/models/bge-m3` 已下载 |
| 上传失败 | OSS 未配置时走本地上传；检查 `data/uploads` 目录权限 |
| MySQL 无表 | 确认 `docker/base_app/docker/mysql/init/` 已执行或手动跑 `sql/schema.sql` |
| Nginx 502 | 后端未启动或 8004 端口未监听 |

## 附录 B：开发环境快速启动

```powershell
# 基础设施
cd docker && docker compose up -d

# 后端（开发端口 8020）
cd ..
$env:MYSQL_HOST="127.0.0.1"; $env:REDIS_HOST="127.0.0.1"
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8020

# 前端
cd front && npm run dev
```

## 附录 C：目录与端口

| 组件 | 端口 |
|------|------|
| Nginx | 80 |
| 后端 API（生产） | 8004 |
| 后端 API（开发） | 8020 |
| MySQL | 3306 |
| Redis | 16379 |
| Milvus | 19530 |
