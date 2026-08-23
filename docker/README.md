# docker（T11 私有化部署）

所有服务已合并到单文件：`docker/docker-compose.yml`

包含服务：

- MySQL
- Redis
- etcd
- MinIO
- Milvus
- Neo4j

启动：

```powershell
cd E:\tianxuan\DevMind-AI\docker
docker compose up -d
```

> `base_app/` 和 `milvus_redis/` 下的旧 compose 文件已废弃，仅保留说明。
