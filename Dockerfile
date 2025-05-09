# 使用官方 Python 运行时作为父镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 将依赖文件复制到工作目录
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录内容复制到容器的 /app 目录
COPY . .

# 声明容器将监听的端口 (Gunicorn 将在此端口运行)
EXPOSE 8000

# 设置默认的环境变量 (可选, 仅作为示例)
# ENV TARGET_BASE_URL="http://your-default-target-api.com"
# ENV FLASK_DEBUG="false"

# 运行 app.py 时 Gunicorn 作为 WSGI 服务器
# Gunicorn 将在容器内的 0.0.0.0:8000 上运行
# 使用环境变量来配置 Gunicorn worker 数量等可以更灵活
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]