# Local CosyVoice Service Integration

## 概述

该扩展现在支持两种 TTS 服务模式：
1. **在线服务**：使用阿里云 Dashscope TTS 服务
2. **本地服务**：使用本地部署的 CosyVoice WebSocket 服务

## 配置说明

### 使用本地服务

在 `property.json` 中配置以下参数：

```json
{
  "use_local_service": true,
  "local_service_url": "ws://192.168.8.230:50002/streaming/ws",
  "voice": "班尼特",
  "local_spk_id": "班尼特",
  "sample_rate": 16000
}
```

**参数说明：**

- `use_local_service` (bool): 是否使用本地服务，设置为 `true` 启用本地服务
- `local_service_url` (string): 本地 WebSocket 服务地址
- `voice` (string): 说话人 ID（当 `local_spk_id` 未设置时使用）
- `local_spk_id` (string): 本地服务专用的说话人 ID（可选）
- `sample_rate` (int): 音频采样率，默认 16000Hz

### 使用在线服务

在 `property.json` 中配置以下参数：

```json
{
  "use_local_service": false,
  "api_key": "your-dashscope-api-key",
  "model": "cosyvoice-v1",
  "voice": "longxiaochun",
  "sample_rate": 16000
}
```

**参数说明：**

- `use_local_service` (bool): 设置为 `false` 使用在线服务
- `api_key` (string): Dashscope API Key
- `model` (string): 模型名称
- `voice` (string): 音色名称
- `sample_rate` (int): 音频采样率

## 本地服务接口

本地服务基于 WebSocket 协议，接口详情请参考 [websocket_interface.md](websocket_interface.md)。

### 关键特性

- **持久连接**：单个 WebSocket 连接处理多个请求
- **实时流式**：音频数据逐块返回
- **采样率**：16000Hz, 16-bit PCM, 单声道
- **Base64 编码**：音频数据通过 Base64 编码传输

### 请求格式

```json
{
    "action": "synthesize",
    "text": "要合成的文本",
    "spk_id": "说话人ID",
    "chunk_id": 1
}
```

### 响应格式

三种消息类型：

1. **音频块** (`audio`)：包含 Base64 编码的音频数据
2. **完成信号** (`complete`)：所有音频已发送完毕
3. **错误信号** (`error`)：处理过程中发生错误

## 测试

### 测试本地服务连接

使用提供的测试脚本：

```bash
cd ai_agents/agents/ten_packages/extension/cosy_tts_python_local
python test_local_service.py
```

该脚本会：
1. 连接到本地 WebSocket 服务
2. 发送测试文本
3. 接收并统计音频数据
4. 可选保存为 WAV 文件

### 测试输出示例

```
============================================================
Testing Local CosyVoice WebSocket TTS Service
============================================================

Configuration:
  Service URL: ws://192.168.8.230:50002/streaming/ws
  Speaker ID: 班尼特
  Test Text: 你好，这是一个测试。

✓ WebSocket connection opened
✓ First audio chunk received (TTFB: 152.34ms, size: 4096 bytes)
✓ Audio chunk received (size: 4096 bytes)
...
✓ TTS synthesis completed

============================================================
Test Results:
============================================================
✓ Test PASSED

Statistics:
  Audio chunks received: 15
  Total audio bytes: 61440
  Audio duration: 1.92s
  Total time: 0.89s
  RTF: 0.463 (real-time)
  TTFB: 152.34ms
```

## 代码结构

```
cosy_tts_python_local/
├── extension.py              # TTS 扩展主类
├── cosy_tts.py              # TTS 客户端（支持在线和本地服务）
├── local_speech_synthesizer.py  # 本地服务实现
├── config.py                # 配置类
├── test_local_service.py    # 本地服务测试脚本
├── websocket_interface.md   # WebSocket 接口文档
└── LOCAL_INTEGRATION.md     # 本文件
```

## 实现细节

### 统一接口

`CosyTTSClient` 类提供统一的接口，根据 `use_local_service` 配置自动选择使用：
- `DashscopeSynthesizer`：阿里云在线服务
- `LocalSpeechSynthesizer`：本地 WebSocket 服务

### 回调机制

两种服务都实现了 `ResultCallback` 接口：
- `on_open()`: 连接建立
- `on_data(bytes)`: 接收音频数据
- `on_complete()`: 合成完成
- `on_error(str)`: 错误处理
- `on_close()`: 连接关闭

### 音频格式

支持多种采样率的 PCM 格式：
- 8000Hz, 16-bit, 单声道
- 16000Hz, 16-bit, 单声道（默认）
- 22050Hz, 16-bit, 单声道
- 24000Hz, 16-bit, 单声道
- 44100Hz, 16-bit, 单声道
- 48000Hz, 16-bit, 单声道

## 故障排除

### 连接失败

如果连接本地服务失败：
1. 检查服务是否运行：`curl http://192.168.8.230:50002/health`
2. 检查网络连接和防火墙设置
3. 确认 WebSocket URL 格式正确（`ws://` 协议）

### 说话人不存在

如果提示说话人不存在：
1. 查看服务日志获取可用的说话人列表
2. 确认 `voice` 或 `local_spk_id` 配置正确

### 音频质量问题

如果音频质量不佳：
1. 检查采样率配置是否与服务匹配
2. 确认网络带宽充足
3. 查看服务端日志排查模型推理问题

## 性能指标

- **TTFB (Time To First Byte)**：首字节延迟，通常 < 200ms
- **RTF (Real Time Factor)**：实时因子，应 < 1.0 以保证实时合成
- **音频质量**：16kHz, 16-bit 单声道 PCM

## 迁移指南

从纯 Dashscope 版本迁移：

1. **更新依赖**：确保安装了 `websocket-client`
   ```bash
   pip install websocket-client
   ```

2. **更新配置**：在 `property.json` 中添加本地服务配置

3. **无需修改代码**：扩展会根据配置自动选择服务

4. **测试连接**：运行测试脚本验证连接

## 注意事项

1. **API Key 要求**：使用在线服务时必须提供有效的 API Key
2. **网络延迟**：本地服务通常延迟更低，但需要额外的服务器资源
3. **说话人 ID**：本地服务的说话人 ID 可能与在线服务不同
4. **并发连接**：本地服务支持持久连接，可减少连接开销

## 未来改进

- [ ] 支持更多音频格式（WAV、MP3 等）
- [ ] 添加连接池管理优化性能
- [ ] 支持流式文本输入
- [ ] 添加重连机制提高稳定性
- [ ] 支持自定义音频参数（音量、语速等）
