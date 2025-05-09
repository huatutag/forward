import os
import requests
from flask import Flask, request, Response, jsonify  # 增加了 jsonify

app = Flask(__name__)

# 从环境变量中获取目标服务器的基础 URL
TARGET_BASE_URL = os.environ.get('TARGET_BASE_URL')

if not TARGET_BASE_URL:
    app.logger.warning(
        "TARGET_BASE_URL environment variable not set. Using default: http://localhost:8080 (for testing only)")
    TARGET_BASE_URL = "http://localhost:8080"

HOP_BY_HOP_HEADERS = [
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-encoding',
    'content-length'
]


# 新增：简单的 GET /hello 接口
@app.route('/hello', methods=['GET'])
def hello_world():
    app.logger.info("Received request for /hello endpoint.")
    # 为了与接口风格统一，也可以返回 JSON 格式
    # return "hello"
    return jsonify({"message": "hello"}), 200


# 通用转发接口 (捕获所有其他路径)
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def forward_request(path):
    # 确保 /hello 路径不会进入这里 (虽然 Flask 路由优先级通常会处理好)
    if request.path == '/hello':
        # 此检查理论上不需要，因为 /hello 路由会先匹配
        # 但作为双重保险或用于日志记录特定情况
        app.logger.debug("Forward request logic explicitly skipping /hello path.")
        # 实际上，如果 Flask 路由正确，这段代码块不会被执行
        return hello_world()  # 或者返回一个错误，表明不应通过此路径访问

    if not TARGET_BASE_URL:
        app.logger.error("TARGET_BASE_URL not configured for forwarding.")
        return jsonify({"error": "Proxy target not configured."}), 503

    target_url_path = request.full_path
    if target_url_path.startswith('/'):
        target_url_path = target_url_path[1:]

    final_target_url = f"{TARGET_BASE_URL.rstrip('/')}/{target_url_path.lstrip('/')}"

    app.logger.info(f"Forwarding {request.method} request from {request.remote_addr} to: {final_target_url}")

    forward_headers = {key: value for key, value in request.headers if key.lower() not in HOP_BY_HOP_HEADERS}
    if 'Host' in forward_headers:
        del forward_headers['Host']

    request_body = request.get_data()

    try:
        target_resp = requests.request(
            method=request.method,
            url=final_target_url,
            headers=forward_headers,
            data=request_body,
            stream=True,
            allow_redirects=False,
            timeout=30
        )
    except requests.exceptions.Timeout:
        app.logger.error(f"Timeout error connecting to target server {final_target_url}")
        return jsonify(
            {"error": f"Proxy error: Timeout connecting to target server {final_target_url}"}), 504  # Gateway Timeout
    except requests.exceptions.ConnectionError:
        app.logger.error(f"Connection error connecting to target server {final_target_url}")
        return jsonify(
            {"error": f"Proxy error: Could not connect to target server {final_target_url}"}), 502  # Bad Gateway
    except requests.exceptions.RequestException as e:
        app.logger.error(f"General request error connecting to target server {final_target_url}: {e}")
        return jsonify({"error": f"Proxy error: {str(e)}"}), 500

    response_headers = []
    for key, value in target_resp.raw.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            response_headers.append((key, value))

    def generate_response_content():
        try:
            for chunk in target_resp.iter_content(chunk_size=8192):
                yield chunk
        finally:
            target_resp.close()  # 确保在流完成后关闭连接

    response_from_proxy = Response(generate_response_content(), status=target_resp.status_code,
                                   headers=response_headers)

    return response_from_proxy


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')