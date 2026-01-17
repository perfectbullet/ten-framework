# WebSocket TTS 接口文档

## 概述

WebSocket 接口提供持久连接支持，允许客户端在单个连接中发送多个文本合成请求，避免每次请求都创建新的 HTTP 连接。

## 连接地址

```
ws://192.168.8.230:50002/streaming/ws
```

## 请求格式

客户端向服务端发送 JSON 格式的消息：

```json
{
    "action": "synthesize",
    "text": "要合成的文本",
    "spk_id": "说话人ID",
    "chunk_id": 1
}
```

**参数说明：**
- `action` (string, 必需): 操作类型，固定为 `"synthesize"`
- `text` (string, 必需): 要合成的文本
- `spk_id` (string, 必需): 说话人 ID
- `chunk_id` (integer, 可选): 文本片段 ID，用于标识不同的文本，便于客户端匹配响应

## 响应格式

服务端返回三种消息类型：

### 1. 音频块 (audio_chunk)

```json
{
    "type": "audio",
    "chunk_id": 1,
    "data": "<base64_encoded_audio>",
    "done": false
}
```

- `type`: `"audio"` 表示这是音频数据
- `chunk_id`: 对应请求的 chunk_id
- `data`: Base64 编码的 PCM 音频数据（16000Hz, 16-bit, 单声道）
- `done`: `false` 表示还有更多音频块

### 2. 完成信号 (complete)

```json
{
    "type": "complete",
    "chunk_id": 1
}
```

表示该请求的所有音频块已发送完毕。

### 3. 错误信号 (error)

```json
{
    "type": "error",
    "chunk_id": 1,
    "data": "错误信息"
}
```

表示处理过程中发生错误。

## 关键特性

| 特性 | 说明 |
|-----|------|
| **持久连接** | 单个 WebSocket 连接处理整个会话的所有文本 |
| **chunk_id** | 客户端可通过 chunk_id 标识不同的文本片段，服务端返回时带上 chunk_id |
| **实时流式** | 音频数据逐块返回，支持实时播放 |
| **采样率** | 16000Hz, 16-bit PCM, 单声道 |
| **Base64 编码** | 音频数据通过 Base64 编码传输 |

## 使用流程

```
1. 客户端连接到 ws://host:port/streaming/ws
2. 发送请求 1 (chunk_id=1)
   └─ 服务端返回多个音频块
   └─ 服务端返回 complete 信号
3. 发送请求 2 (chunk_id=2)
   └─ 服务端返回多个音频块
   └─ 服务端返回 complete 信号
4. ... 重复步骤 2-3
5. 断开连接
```

## Python 客户端示例

```python
import asyncio
import json
import base64
import websockets

async def test_websocket():
    async with websockets.connect("ws://192.168.8.230:50002/streaming/ws") as ws:
        # 发送请求
        request = {
            "action": "synthesize",
            "text": "你好，世界",
            "spk_id": "班尼特",
            "chunk_id": 1
        }
        await ws.send(json.dumps(request))
        
        # 接收响应
        audio_chunks = []
        while True:
            message = await ws.recv()
            response = json.loads(message)
            
            if response["type"] == "audio":
                audio_data = base64.b64decode(response["data"])
                audio_chunks.append(audio_data)
            
            elif response["type"] == "complete":
                print("合成完成")
                break
            
            elif response["type"] == "error":
                print(f"错误: {response['data']}")
                break

asyncio.run(test_websocket())
```

## 测试脚本

使用提供的测试脚本 `test_websocket.py` 进行测试：

```bash
python tts_service/test_websocket.py
```

该脚本会：
1. 连接到 WebSocket 服务
2. 发送多个文本片段（分别带不同的 chunk_id）
3. 接收音频数据
4. 保存为 WAV 文件
5. 输出性能统计（TTFB、RTF 等）

## 与 HTTP/SSE 对比

| 方面 | WebSocket | HTTP/SSE |
|-----|-----------|----------|
| **连接** | 持久连接 | 每次请求创建新连接 |
| **多请求** | 单连接处理多个请求 | 每个请求独立 |
| **双向通信** | 支持 | 单向 |
| **标识匹配** | chunk_id | stream_id |
| **适合场景** | 大量短文本片段 | 单次大文本 |

## 错误处理

常见错误类型：

- **Invalid JSON format**: 消息格式不正确
- **Unknown action**: action 不是 "synthesize"
- **文本不能为空**: 未提供 text 参数
- **说话人ID不能为空**: 未提供 spk_id 参数
- **说话人 {id} 不存在**: 指定的说话人不存在
- **合成失败**: 模型推理失败

## 性能指标

通过 test_websocket.py 脚本可以获取以下性能指标：

- **TTFB (Time To First Byte)**: 首字节延迟，越短越好
- **接收耗时**: 接收所有音频块的耗时
- **音频时长**: 生成的音频总时长
- **RTF (Real Time Factor)**: 实时因子，RTF < 1.0 表示实时合成
