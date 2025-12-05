import requests
import base64
from pathlib import Path


def call_qwen25vl(prompt: str, image_path: str = None):
    """
    调用 qwen2.5vl:32b 模型
    :param prompt: 文本提示（如问答、指令）
    :param image_path: 本地图像路径（可选，支持 JPG/PNG）
    :return: 模型响应结果
    """
    # Ollama API 地址（默认本地）
    url = "http://192.168.8.231:11434/api/generate"

    # 构建请求数据（核心：多模态输入需用 "images" 字段传 Base64 图像）
    data = {
        "model": "qwen2.5vl:32b",
        "prompt": prompt,
        "stream": False,  # 关闭流式输出，直接获取完整响应
        "options": {
            "temperature": 0.3,  # 温度参数（越低越稳定）
            "top_p": 0.9  # 采样参数
        }
    }

    # 若传入图像，转换为 Base64 编码（Ollama 要求图像用 Base64 传输）
    if image_path and Path(image_path).exists():
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        data["images"] = [image_base64]  # 支持多图输入，传入列表即可

    # 发送 POST 请求调用模型
    response = requests.post(url, json=data, timeout=60)  # 32B 模型响应较慢，超时设为 60s
    response.raise_for_status()  # 抛出 HTTP 错误（如服务未启动）

    # 解析响应结果
    return response.json()["response"]


# ------------------- 调用示例 -------------------
if __name__ == "__main__":
    # 示例 1：纯文本问答
    # text_prompt = "解释什么是多模态模型？用简单的语言说明"
    # text_response = call_qwen25vl(text_prompt)
    # print("纯文本响应：")
    # print(text_response)
    # print("-" * 50)

    # 示例 2：图文问答（传入本地图像路径）
    image_path = "zj.jpg"  # 替换为你的图像路径（JPG/PNG）
    image_prompt = "简单分析图片主要内容"
    image_response = call_qwen25vl(image_prompt, image_path)
    print("图文问答响应：")
    print(image_response)