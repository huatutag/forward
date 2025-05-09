import os
import requests
from flask import Flask, request, Response

app = Flask(__name__)

# 从环境变量中获取目标服务器的基础 URL
# 例如：http://target-api.com 或 http://47.108.147.164:5001
TARGET_BASE_URL = os.environ.get('TARGET_BASE_URL')

if not TARGET_BASE_URL:
    # 如果在生产环境中未设置此变量，可以选择记录错误并退出或使用默认值（不推荐用于生产）
    app.logger.warning(
        "TARGET_BASE_URL environment variable not set. Using default: http://localhost:8080 (for testing only)")
    TARGET_BASE_URL = "http://localhost:8080"  # 仅为本地测试设置一个占位符

# 定义不应从客户端转发到目标服务器，或从目标服务器返回到客户端的 Hop-by-hop 头部
# 这些头部通常是针对单个TCP连接的，不应该被代理转发
# Content-Length 和 Host 通常由 requests 库或服务器自动处理/重写
HOP_BY_HOP_HEADERS = [
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade', 'content-encoding',
    # content-encoding 比较特殊，requests 会自动解压，如果想原样透传需要特殊处理，这里简单排除
    'content-length'  # requests 会重新计算
]


@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def forward_request(path):
    if not TARGET_BASE_URL:
        return "Proxy target not configured.", 503

    # 1. 构建目标 URL
    # request.query_string 是原始的查询字符串字节串，需要解码
    # request.full_path 包括了前导的 '/' 以及查询字符串
    # 我们这里拼接 TARGET_BASE_URL 和 客户端请求的完整路径（包括查询参数）
    # 如果 TARGET_BASE_URL 末尾有 / 而 path 开头也有 /，需要处理一下避免 //
    target_url_path = request.full_path
    if target_url_path.startswith('/'):
        target_url_path = target_url_path[1:]  # 移除前导 /，因为 TARGET_BASE_URL 通常不以 / 结尾，或者即使有，我们自己拼接

    final_target_url = f"{TARGET_BASE_URL.rstrip('/')}/{target_url_path.lstrip('/')}"

    app.logger.info(f"Forwarding {request.method} request to: {final_target_url}")

    # 2. 准备转发的头部
    # 从原始请求中复制头部，排除 hop-by-hop 头部
    forward_headers = {key: value for key, value in request.headers if key.lower() not in HOP_BY_HOP_HEADERS}
    # requests 库会正确设置 Host 头部指向目标服务器
    if 'Host' in forward_headers:  # 通常客户端的Host是指向代理的，所以移除，让requests库设置正确的
        del forward_headers['Host']

    # 3. 获取原始请求体
    request_body = request.get_data()

    # 4. 发送请求到目标服务器 (使用 stream=True 以便处理大文件和流式响应)
    try:
        target_resp = requests.request(
            method=request.method,
            url=final_target_url,
            headers=forward_headers,
            data=request_body,
            stream=True,  # 开启流模式
            allow_redirects=False,  # 通常代理不应自动处理重定向，而是将重定向响应返回给客户端
            timeout=30  # 设置超时 (例如30秒)
        )
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error connecting to target server {final_target_url}: {e}")
        return f"Proxy error: Could not connect to target server. {str(e)}", 502  # Bad Gateway

    # 5. 构建并返回给客户端的响应
    # 从目标响应中复制头部，排除 hop-by-hop 头部
    response_headers = []
    for key, value in target_resp.raw.headers.items():  # 使用 .raw.headers 获取原始头部
        if key.lower() not in HOP_BY_HOP_HEADERS:
            response_headers.append((key, value))

    # 使用 Flask 的 Response 对象，并流式传输内容
    # target_resp.iter_content 会一块一块地读取内容，避免一次性加载到内存
    # chunk_size 可以根据需要调整
    def generate_response_content():
        for chunk in target_resp.iter_content(chunk_size=8192):
            yield chunk

    # 创建 Flask 响应对象
    # target_resp.status_code 是目标服务器返回的状态码
    # response_headers 是我们处理过的头部
    # mimetype 通常可以从 target_resp.headers.get('Content-Type') 获取，或者让 Flask 自动处理
    # 直接使用 iter_content 作为响应体，Flask 会自动处理 Transfer-Encoding: chunked （如果 Content-Length 未设置）
    response_from_proxy = Response(generate_response_content(), status=target_resp.status_code,
                                   headers=response_headers)

    # 如果目标服务器发送了 'Content-Encoding' (例如 'gzip'), 并且我们没有在 HOP_BY_HOP_HEADERS 中排除它（或者特殊处理它），
    # 那么这个头部会传递给客户端。客户端的浏览器通常能处理。
    # 如果 requests 自动解压缩了，而我们又传递了 Content-Encoding 头，可能会出问题。
    # target_resp.raw.headers['content-encoding'] 是未经 requests 解压时的原始值。
    # requests(>=2.0) 会在响应头中删除 content-encoding 如果它已经为你解码了内容。
    # 如果使用了 stream=True，requests 通常不会自动解压，除非显式访问 .content 或 .text。
    # iter_content(decode_unicode=False) 保证获取原始字节。

    return response_from_proxy


if __name__ == '__main__':
    # 开发环境运行
    # Gunicorn 会在生产环境中处理
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')