# docker（私有化部署）

基础设施：`docker/docker-compose.yml`（MySQL / Redis / Milvus / Neo4j）

可选后端容器：`docker-compose -f docker-compose.yml -f docker-compose.app.yml up -d --build`

完整 8 步生产部署见根目录 **[DEPLOYMENT.md](../DEPLOYMENT.md)**。

启动基础设施：

```powershell
cd E:\tianxuan\DevMind-AI\docker
copy .env.example .env
docker compose up -d
```

> `base_app/` 和 `milvus_redis/` 下的旧 compose 文件已废弃，仅保留说明。
