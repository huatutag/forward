# 使用官方Python运行时作为父镜像
FROM python:3.9-slim

# 设置容器内的工作目录
WORKDIR /app

# 将requirements.txt复制到容器的/app目录下
COPY requirements.txt .

# 安装requirements.txt中指定的任何所需包
# --no-cache-dir 减少镜像大小
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录内容（主要是app.py）复制到容器的/app目录下
COPY app.py .

# 使容器的8000端口可供外部访问
# Gunicorn将绑定到此端口
EXPOSE 8000

# 定义环境变量 (这些是默认值，可以在docker run时覆盖)
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# 以下环境变量应在 `docker run` 命令中提供，或通过其他方式（如docker-compose）设置
# ENV CLOUDFLARE_API_URL="https://<your-pages-url>/api/message"
# ENV CLOUDFLARE_API_KEY="your_cloudflare_api_key_for_get_message"
# ENV TARGET_API_URL_BASE="http://47.108.147.164:5001/send"
# ENV TARGET_API_KEY="sUpErS3cr3tK3y!"
# ENV FORWARD_INTERVAL_SECONDS=60

# 运行应用程序的命令 (使用Gunicorn)
# 绑定到 0.0.0.0 以便从容器外部访问。
# --workers 1: 使用单个worker。如果您的Cloudflare Function中的“获取并删除”操作是原子性的，
# 或者您不担心偶尔的并发冲突（D1的重试逻辑应有所帮助），可以增加worker数量。
# 对于简单的转发任务，单个worker通常足够且能避免不必要的复杂性。
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "app:app"]
