# app.py
from flask import Flask
import threading
import time
import requests
import os
import logging

# --- 配置 ---
# 基本日志设置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从环境变量读取配置，并提供默认值（尽管在生产中最好不要硬编码敏感信息）
CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL')  # 例如: "https://<your-pages-url>/api/message"
CLOUDFLARE_API_KEY = os.environ.get('CLOUDFLARE_API_KEY')

TARGET_API_URL_BASE = os.environ.get('TARGET_API_URL_BASE', "http://47.108.147.164:5001/send")
TARGET_API_KEY = os.environ.get('TARGET_API_KEY', "sUpErS3cr3tK3y!")  # 从您的示例中获取

FORWARD_INTERVAL_SECONDS = int(os.environ.get('FORWARD_INTERVAL_SECONDS', "60"))

app = Flask(__name__)


def check_env_vars():
    """检查是否所有必需的环境变量都已设置。"""
    required_vars = {
        "CLOUDFLARE_API_URL": CLOUDFLARE_API_URL,
        "CLOUDFLARE_API_KEY": CLOUDFLARE_API_KEY,
        # TARGET_API_URL_BASE 和 TARGET_API_KEY 有默认值，但仍建议通过环境变量配置
    }
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logger.error(f"警告: 缺少关键环境变量: {', '.join(missing_vars)}. 转发功能可能无法正常工作。")
        return False
    logger.info("所有关键环境变量已配置。")
    return True


ENV_VARS_CONFIGURED = check_env_vars()


def fetch_and_forward():
    """从Cloudflare获取消息并将其转发到目标API。"""
    if not ENV_VARS_CONFIGURED:
        # 如果在启动时已经记录了错误，这里可以选择安静地跳过或记录一个更简洁的警告
        logger.debug("环境变量未完全配置。跳过此轮获取和转发。")
        return

    logger.info("开始尝试从Cloudflare获取消息...")
    try:
        # 1. 从Cloudflare获取消息
        if not CLOUDFLARE_API_URL or not CLOUDFLARE_API_KEY:
            logger.error("Cloudflare API URL或Key未配置。")
            return

        fetch_url = f"{CLOUDFLARE_API_URL}?key={CLOUDFLARE_API_KEY}"
        response = requests.get(fetch_url, timeout=10)  # 为请求设置超时
        response.raise_for_status()  # 如果状态码是4xx或5xx，则抛出HTTPError

        data = response.json()
        logger.debug(f"从Cloudflare接收到的数据: {data}")

        if data.get("success") and data.get("data"):
            message_data = data["data"]
            title = message_data.get("title", "无标题")  # 如果缺少标题，则使用默认值
            content = message_data.get("content")

            if not content:  # 内容是必需的
                logger.warning(f"获取到的消息 ID {message_data.get('id', 'N/A')} 没有内容。跳过转发。")
                return

            message_id_log = message_data.get('id', 'N/A')
            logger.info(f"获取到消息 ID {message_id_log}: '{title[:50]}...'")  # 记录标题的片段

            # 2. 将消息转发到目标API
            if not TARGET_API_URL_BASE or not TARGET_API_KEY:
                logger.error("目标API URL或Key未配置。")
                return

            forward_url = f"{TARGET_API_URL_BASE}?key={TARGET_API_KEY}"
            payload = {
                "title": title,
                "content": content
            }

            logger.debug(f"准备转发到 {forward_url}，内容: {payload}")
            forward_response = requests.post(forward_url, json=payload, timeout=15)  # 为转发设置超时
            forward_response.raise_for_status()

            logger.info(f"消息 ID {message_id_log} 已成功转发到目标。状态码: {forward_response.status_code}")

        elif data.get("success") and data.get("data") is None:
            logger.info("Cloudflare上没有可供转发的新消息。")
        else:
            logger.warning(f"未能从Cloudflare获取有效消息或收到意外响应。响应: {data}")

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP错误: {e.response.status_code} - {e.response.text} (请求URL: {e.request.url})")
    except requests.exceptions.Timeout:
        logger.error(f"请求超时 (URL: {fetch_url if 'fetch_url' in locals() else 'N/A'})")
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e} (URL: {e.request.url if e.request else 'N/A'})")
    except Exception as e:
        logger.error(f"在fetch_and_forward中发生意外错误: {e}", exc_info=True)


def scheduled_task_runner():
    """定期运行fetch_and_forward任务。"""
    if not ENV_VARS_CONFIGURED:
        # 此处不再重复记录错误，因为check_env_vars已在启动时记录
        return

    logger.info(f"调度器已启动。每 {FORWARD_INTERVAL_SECONDS} 秒运行一次 fetch_and_forward。")
    while True:
        fetch_and_forward()
        time.sleep(FORWARD_INTERVAL_SECONDS)


@app.route('/')
def health_check():
    """一个简单的服务健康检查端点。"""
    if ENV_VARS_CONFIGURED:
        # 检查后台线程是否仍在运行 (基本检查)
        if 'scheduler_thread' in globals() and scheduler_thread.is_alive():
            return "转发服务正在运行且已配置。调度器活动。", 200
        else:
            return "转发服务正在运行但调度器似乎未激活或配置不完整。", 500
    else:
        return "转发服务正在运行但未配置 (缺少环境变量)。", 503


# 当模块加载时启动后台调度器线程。
# 这意味着每个Gunicorn worker都会有自己的调度器线程。
if ENV_VARS_CONFIGURED:
    scheduler_thread = threading.Thread(target=scheduled_task_runner, daemon=True)
    scheduler_thread.start()
    logger.info("后台调度器线程已启动。")
else:
    logger.warning("由于缺少环境变量，后台调度器未启动。")

# 'app' 对象将被Gunicorn获取。
# 如果您直接运行 `python app.py`，您需要添加以下代码块来运行Flask开发服务器：
# if __name__ == "__main__":
#     # 注意：直接运行 app.run() 时，上面的 scheduler_thread 已经启动了。
#     # 对于生产环境，请使用Gunicorn。
#     app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
