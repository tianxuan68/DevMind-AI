# T11: 私有化部署镜像
# 参考基线：E:/study_project/Itcast_qa_system/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8003

CMD ["sh", "entrypoint.sh"]
