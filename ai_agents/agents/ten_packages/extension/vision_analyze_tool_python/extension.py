#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import json
import uuid
from datetime import datetime
from ten_ai_base.struct import (
    EventType,
    LLMMessage,
    LLMMessageContent,
    LLMRequest,
    parse_llm_response,
)
from ten_runtime import (
    AudioFrame,
    StatusCode,
    VideoFrame,
    AsyncTenEnv,
    Cmd,
    Data,
)
from pathlib import Path
from PIL import Image
from io import BytesIO
from base64 import b64encode
import requests
import base64
from ten_ai_base.types import (
    LLMToolMetadata,
    LLMToolMetadataParameter,
    LLMToolResult,
    LLMToolResultLLMResult,
)
from ten_ai_base.llm_tool import AsyncLLMToolBaseExtension


def rgb2base64jpeg(rgb_data, width, height):
    """
    Convert RGB/RGBA image data to base64 JPEG format.
    Automatically detects the image format based on data length.
    """
    if not rgb_data or width <= 0 or height <= 0:
        raise ValueError("Invalid image data or dimensions")

    # Convert to bytes if not already
    if not isinstance(rgb_data, bytes):
        rgb_data = bytes(rgb_data)

    expected_pixels = width * height
    data_length = len(rgb_data)

    # Determine image format based on data length
    if data_length == expected_pixels * 4:
        # RGBA format (4 bytes per pixel)
        mode = "RGBA"
    elif data_length == expected_pixels * 3:
        # RGB format (3 bytes per pixel)
        mode = "RGB"
    elif data_length == expected_pixels:
        # Grayscale format (1 byte per pixel)
        mode = "L"
    else:
        raise ValueError(
            f"Unsupported image format. Expected {expected_pixels * 4} (RGBA), {expected_pixels * 3} (RGB), or {expected_pixels} (L) bytes, got {data_length}"
        )

    try:
        # Convert the image data to a PIL Image
        pil_image = Image.frombytes(mode, (width, height), rgb_data)

        # Convert to RGB if needed (JPEG doesn't support RGBA or L directly)
        if mode in ["RGBA", "L"]:
            pil_image = pil_image.convert("RGB")

        # Resize the image while maintaining its aspect ratio
        pil_image = resize_image_keep_aspect(pil_image, 512)

        # Save the image to a BytesIO object in JPEG format
        buffered = BytesIO()
        pil_image.save(buffered, format="JPEG", quality=85)

        # Get the byte data of the JPEG image
        jpeg_image_data = buffered.getvalue()

        # Convert the JPEG byte data to a Base64 encoded string
        base64_encoded_image = b64encode(jpeg_image_data).decode("utf-8")

        # Create the data URL
        mime_type = "image/jpeg"
        base64_url = f"data:{mime_type};base64,{base64_encoded_image}"
        return base64_url

    except Exception as e:
        raise ValueError(f"Failed to process image data: {str(e)}") from e


def resize_image_keep_aspect(image, max_size=512):
    """
    Resize an image while maintaining its aspect ratio, ensuring the larger dimension is max_size.
    If both dimensions are smaller than max_size, the image is not resized.

    :param image: A PIL Image object
    :param max_size: The maximum size for the larger dimension (width or height)
    :return: A PIL Image object (resized or original)
    """
    # Get current width and height
    width, height = image.size

    # If both dimensions are already smaller than max_size, return the original image
    if width <= max_size and height <= max_size:
        return image

    # Calculate the aspect ratio
    aspect_ratio = width / height

    # Determine the new dimensions
    if width > height:
        new_width = max_size
        new_height = int(max_size / aspect_ratio)
    else:
        new_height = max_size
        new_width = int(max_size * aspect_ratio)

    # Resize the image with the new dimensions
    resized_image = image.resize((new_width, new_height))

    return resized_image


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



def base64_to_jpeg(image_base64: str, save_path: str = "output.jpg"):
    """
    从 JSON 文件中提取 base64 格式的 image_url，解码并保存为 JPEG 图片

    Args:
        image_base64: image_base64
        save_path: 输出 JPEG 图片路径（默认 output.jpg）
    """
    try:
        # 2. 提取 image_url 字段（容错：处理字段不存在的情况）
        if not image_base64:
            raise KeyError("JSON 中未找到 'image_url' 字段")

        # 3. 去除 Base64 前缀（如 "data:image/jpeg;base64,"）
        # 兼容带前缀和不带前缀的两种格式
        if "base64," in image_base64:
            image_base64 = image_base64.split("base64,")[-1]

        # 4. Base64 解码（处理可能的空格/换行符）
        image_base64 = image_base64.strip().replace("\n", "").replace(" ", "")
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)  # validate=True 校验 Base64 合法性
        except base64.binascii.Error as e:
            raise ValueError(f"Base64 编码无效：{str(e)}")

        # 5. 保存为 JPEG 图片
        with open(save_path, "wb") as f:
            f.write(image_bytes)

        print(f"图片保存成功！路径：{save_path}")
        return save_path

    except Exception as e:
        print(f"处理失败：{str(e)}")
        return None


class VisionAnalyzeToolExtension(AsyncLLMToolBaseExtension):
    image_data = None
    image_width = 0
    image_height = 0

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_init")

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_start")
        await super().on_start(ten_env)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_stop")

        # TODO: clean up resources

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_deinit")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))

        await super().on_cmd(ten_env, cmd)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        data_name = data.get_name()
        ten_env.log_debug("on_data name {}".format(data_name))

    async def on_audio_frame(
            self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        audio_frame_name = audio_frame.get_name()
        ten_env.log_debug("on_audio_frame name {}".format(audio_frame_name))

    async def on_video_frame(
            self, ten_env: AsyncTenEnv, video_frame: VideoFrame
    ) -> None:
        video_frame_name = video_frame.get_name()
        ten_env.log_debug("on_video_frame name {}".format(video_frame_name))

        self.image_data = video_frame.get_buf()
        self.image_width = video_frame.get_width()
        self.image_height = video_frame.get_height()

    def get_tool_metadata(self, ten_env: AsyncTenEnv) -> list[LLMToolMetadata]:
        return [
            LLMToolMetadata(
                name="get_vision_chat_completion",
                description="Get the image analyze result from camera. Call this whenever you need to understand the input camera image like you have vision capability, for example when user asks 'What can you see in my camera?' or 'Can you see me?'",
                parameters=[
                    LLMToolMetadataParameter(
                        name="query",
                        type="string",
                        description="The vision completion query.",
                        required=True,
                    ),
                ],
            ),
        ]

    async def run_tool(
            self, ten_env: AsyncTenEnv, name: str, args: dict
    ) -> LLMToolResult | None:
        if name == "get_vision_chat_completion":
            if self.image_data is None:
                ten_env.log_error("No image data available")
                raise ValueError("No image data available")

            if "query" not in args:
                ten_env.log_error("Missing query parameter")
                raise ValueError("Failed to get property")

            query = args["query"]
            ten_env.log_info(f"Processing vision query: {query}")
            ten_env.log_info(
                f"Image dimensions: {self.image_width}x{self.image_height}, data length: {len(self.image_data) if self.image_data else 0}"
            )

            try:
                base64_image = rgb2base64jpeg(
                    self.image_data, self.image_width, self.image_height
                )
                ten_env.log_info("Successfully converted image to base64")
            except Exception as e:
                ten_env.log_error(
                    f"Failed to convert image to base64: {str(e)}"
                )
                raise ValueError(f"Image processing failed: {str(e)}") from e
            # return LLMToolResult(message=LLMCompletionArgsMessage(role="user", content=[result]))
            # cmd: Cmd = Cmd.create(CMD_CHAT_COMPLETION_CALL)
            # message: LLMChatCompletionUserMessageParam = (
            #     LLMChatCompletionUserMessageParam(
            #         role="user",
            #         content=[
            #             {"type": "text", "text": query},
            #             {
            #                 "type": "image_url",
            #                 "image_url": {"url": base64_image},
            #             },
            #         ],
            #     )
            # )
            # cmd.set_property_from_json(
            #     "arguments", json.dumps({"messages": [message]})
            # )
            # ten_env.log_info("send_cmd {}".format(message))
            # [cmd_result, _] = await ten_env.send_cmd(cmd)
            # result, _ = cmd_result.get_property_to_json("response")


            # 生成格式：年-月-日_时-分-秒（如：2025-11-24_15-30-45）
            current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            file_name = f"output_{current_time}.jpg"
            base64_to_jpeg(base64_image, file_name)

            request_id = str(uuid.uuid4())
            # messages: list[LLMMessage] = []
            # messages.append(
            #     LLMMessageContent(
            #         role="user",
            #         content=[
            #             {"type": "text", "text": query},
            #             {
            #                 "type": "image_url",
            #                 "image_url": {"url": base64_image},
            #             },
            #         ],
            #     )
            # )
            # llm_input = LLMRequest(
            #     request_id=request_id,
            #     messages=messages,
            #     model="qwen2.5vl:32b",
            #     streaming=False,
            #     parameters={"temperature": 0.7},
            #     tools=[],
            # )
            # input_json = llm_input.model_dump()
            # cmd = Cmd.create("chat_completion")
            # cmd.set_property_from_json(None, json.dumps(input_json))
            # response = ten_env.send_cmd_ex(cmd)
            #
            # # response = _send_cmd_ex(ten_env, "chat_completion", "llm", input_json)
            #
            # result = ""
            #
            # async for cmd_result, _ in response:
            #     if cmd_result and cmd_result.is_final() is False:
            #         if cmd_result.get_status_code() == StatusCode.OK:
            #             response_json, _ = cmd_result.get_property_to_json(None)
            #             ten_env.log_info(f"tool: response_json {response_json}")
            #             completion = parse_llm_response(response_json)
            #             if completion.type == EventType.MESSAGE_CONTENT_DONE:
            #                 result = completion.content
            #                 break
            # ten_env.log_info(f"Processing vision result is: {result}")


            content = call_qwen25vl('简单描述图片主要内容', file_name)
            ten_env.log_info(f"Processing vision content is: {content}")
            result = {
                "response_id": request_id,
                "role": "assistant",
                "content": content,
                "type": "message_content_delta"
            }
            return LLMToolResultLLMResult(
                type="llmresult",
                content=json.dumps(result),
            )
