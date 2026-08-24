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
  backend base internal_kb_qa mysql_qa rag_qa \
  new_main.py app.py config.ini pyproject.toml uv.lock .python-version \
  sql docker scripts locust_test.py \
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
  backend base internal_kb_qa mysql_qa rag_qa `
  new_main.py app.py config.ini pyproject.toml uv.lock .python-version `
  sql docker scripts locust_test.py
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

| 目录 | 用途 | 体积约 | 是否必须 |
|------|------|--------|----------|
| `internal_kb_qa/models/bge-m3` | 向量嵌入 | ~2GB | **必须** |
| `internal_kb_qa/models/bge-reranker-v2-m3` | 精排 | ~2GB | 可选（低内存/带宽紧张可先跳过） |

> **重要（国内服务器）**：直连 HuggingFace 官方常只有约 1MB/s，下完整模型可能要几十分钟到数小时。  
> **必须先设置镜像**，再执行下载命令（见下方）。

### 3.4.1 环境与依赖（若尚未完成）

> **Python 版本**：须使用 **3.12 或 3.13**。勿用 3.14（`unstructured` → `spacy` 尚无 cp314 wheel）。  
> 命令必须在项目目录执行：`cd /opt/devmind-ai`，使用 `uv run`，不要用系统全局 Python。

```bash
cd /opt/devmind-ai

curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv python install 3.12

# 若曾用 3.14 创建过 .venv，先删除再同步
# rm -rf .venv
uv sync --python 3.12
# 已有可用 .venv 时优先：
# uv sync --frozen --python 3.12
```

### 3.4.2 下载命令（推荐：ModelScope，国内更稳）

> 说明：`HF_ENDPOINT=hf-mirror` 在部分服务器上仍会报  
> `Distant resource does not seem to be on huggingface.co`，且半截目录会导致  
> `local file already exists` 不再重下大文件。  
> **国内生产环境默认优先用 ModelScope**。

```bash
cd /opt/devmind-ai

# 安装 ModelScope（若尚未安装）
uv pip install modelscope

# 清掉半截目录并强制重下（必做，若曾中断过）
rm -rf internal_kb_qa/models/bge-m3
rm -rf internal_kb_qa/models/bge-reranker-v2-m3

# 先下必须的嵌入模型
uv run python -m internal_kb_qa.scripts.download_models bge-m3 --source modelscope --force

# 可选：精排模型
uv run python -m internal_kb_qa.scripts.download_models bge-reranker-v2-m3 --source modelscope --force

# 或一次下全部（默认 auto：先 ModelScope，失败再 HF）
# uv run python -m internal_kb_qa.scripts.download_models all --force
```

### 3.4.2b 备选：HuggingFace 镜像

仅在 ModelScope 不可用时使用：

```bash
cd /opt/devmind-ai
export HF_ENDPOINT=https://hf-mirror.com
grep -q 'HF_ENDPOINT' ~/.bashrc || echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc

rm -rf internal_kb_qa/models/bge-m3
uv run python -m internal_kb_qa.scripts.download_models bge-m3 --source hf --force
```

脚本优先级：参考目录复制 →（`--source auto`）ModelScope → HuggingFace。

### 3.4.3 备选：ModelScope 一行脚本（脚本不可用时）

```bash
cd /opt/devmind-ai
uv pip install modelscope   # 若环境尚无该包

uv run python - <<'PY'
from modelscope import snapshot_download
from pathlib import Path

root = Path("internal_kb_qa/models")
for name, mid in [
    ("bge-m3", "BAAI/bge-m3"),
    ("bge-reranker-v2-m3", "BAAI/bge-reranker-v2-m3"),
]:
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    print(f"downloading {mid} -> {target}")
    snapshot_download(model_id=mid, local_dir=str(target))
    print(f"done {name}")
PY
```

### 3.4.4 可选项：本机下载后上传解压（服务器下很慢时）

> **适用**：本机宽带快，但服务器即使用 `HF_ENDPOINT` / ModelScope 仍然很慢。  
> **不适用**：本机上传带宽也很差（见下方自测）——此时继续在服务器用镜像下更合适。

#### （1）先测本机 → 服务器上传带宽（可选但推荐）

在**本机 PowerShell** 执行：

```powershell
# 生成约 100MB 测试文件
fsutil file createnew $env:TEMP\speedtest.bin 104857600

# 上传并计时（改成你的服务器 IP）
Measure-Command {
  scp $env:TEMP\speedtest.bin root@8.211.188.59:/tmp/speedtest.bin
}
```

粗算：`速度(MB/s) ≈ 100 ÷ 上传秒数`。例如 100MB 用了 50 秒 ≈ **2 MB/s**。

| 本机上传（scp 实测） | 服务器镜像下载 | 建议 |
|----------------------|----------------|------|
| ≥ 5 MB/s | ≤ 2 MB/s | **用本选项：本地下好再传** |
| ≤ 2 MB/s | ≥ 5 MB/s | 不用本选项，按 §3.4.2 / §3.4.3 在服务器下 |
| 两边都慢 | — | 试 ModelScope，或经同地域 OSS 中转 |

测完后在服务器删除测试文件：`rm -f /tmp/speedtest.bin`。

#### （2）本机准备模型并打包

**若本机项目里已有完整模型：**

```powershell
# Windows（在 models 目录的上一级）
cd E:\tianxuan\DevMind-AI\internal_kb_qa\models
tar -czf D:\models.tgz bge-m3 bge-reranker-v2-m3
```

**若本机还没有，先下再打包：**

```powershell
cd E:\tianxuan\DevMind-AI
$env:HF_ENDPOINT = "https://hf-mirror.com"
uv run python -m internal_kb_qa.scripts.download_models bge-m3
uv run python -m internal_kb_qa.scripts.download_models bge-reranker-v2-m3

cd internal_kb_qa\models
tar -czf D:\models.tgz bge-m3 bge-reranker-v2-m3
```

打包前确认本机文件齐全（尤其 `pytorch_model.bin` / `model.safetensors`），半截包传上去等于白传。两个模型合计约 **4GB+**，压缩后可能仍有 2～3GB。

#### （3）上传到服务器并解压

```powershell
# 本机
scp D:\models.tgz root@8.211.188.59:/opt/devmind-ai/
# 大文件可用（Git Bash / WSL，支持断点与进度）：
# rsync -avP --partial D:/models.tgz root@8.211.188.59:/opt/devmind-ai/
```

```bash
# 服务器
cd /opt/devmind-ai
mkdir -p internal_kb_qa/models
tar -xzf models.tgz -C internal_kb_qa/models/

# 校验
ls -lh internal_kb_qa/models/bge-m3/pytorch_model.bin
ls -lh internal_kb_qa/models/bge-reranker-v2-m3/model.safetensors

# 可选：删掉压缩包省磁盘
rm -f models.tgz
```

解压后目录应类似：

```
/opt/devmind-ai/internal_kb_qa/models/
├── bge-m3/
│   ├── config.json
│   └── pytorch_model.bin
└── bge-reranker-v2-m3/
    ├── config.json
    └── model.safetensors
```

#### （4）只传必须模型（进一步省时间）

带宽紧张时可只打包 `bge-m3`，精排以后再补：

```powershell
tar -czf D:\models-bge-m3.tgz bge-m3
scp D:\models-bge-m3.tgz root@8.211.188.59:/opt/devmind-ai/
```

```bash
tar -xzf models-bge-m3.tgz -C /opt/devmind-ai/internal_kb_qa/models/
```

---

### 3.4.5 校验是否下全

```bash
ls -lh internal_kb_qa/models/bge-m3/pytorch_model.bin \
       internal_kb_qa/models/bge-m3/config.json
ls -lh internal_kb_qa/models/bge-reranker-v2-m3/model.safetensors \
       internal_kb_qa/models/bge-reranker-v2-m3/config.json
```

缺 `model.safetensors` / `pytorch_model.bin` 即未下全，删目录后按 §3.4.2 重下，或改用 §3.4.4 本机上传。

### 3.4.6 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 速度约 1MB/s、进度几乎不动 | 未设镜像 / 直连 HF 官方 | 改用 `--source modelscope`（§3.4.2） |
| `Distant resource does not seem to be on huggingface.co` | HF 镜像与当前 hub 版本不兼容或半截缓存 | **删目录**后用 ModelScope：`--source modelscope --force` |
| `local file already exists` 但不下大文件 | 半截下载残留 | `rm -rf` 对应模型目录，加 `--force` |
| `No module named 'internal_kb_qa'` | 不在项目目录，或用了系统 Python 3.14 | `cd /opt/devmind-ai` 后用 `uv run ...` |
| `[FAIL] 缺少: ['pytorch_model.bin']` | 仓库已改为 safetensors，或未下完 | 新脚本接受 safetensors；不完整则 `--force` 重下 |
| 服务器下很慢、本机网快 | 机房到 HF/镜像差 | **可选项 §3.4.4**：本地下好再上传（先测上传带宽） |
| 本机 scp 也很慢（约 1MB/s） | 上传带宽不足 | 不要本机传模型；继续服务器 ModelScope |
| 内存紧张 | reranker 再占约 2GB | 可只下/只传 `bge-m3`，配置里关闭精排 |

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

# T8 问答鉴权：与 JWT_SECRET 一致，工作台登录 token 可调用 /api/query、/api/stream
SSO_MODE=jwt
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
