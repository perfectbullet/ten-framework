# Live2D 语音助手

一款集成了**Live2D角色**的语音助手，借助声网实时通信（Agora RTC）、深度语音转文字（Deepgram STT）、OpenAI大语言模型（LLM）及ElevenLabs文字转语音（TTS）技术，实现实时对话功能。本示例包含可动画交互的Live2D角色，能响应音频输入并同步匹配口型与表情，为用户带来沉浸式互动体验。

> **注意**：本示例与[语音助手](../voice-assistant/)示例共享相同的后端配置，区别在于新增了支持Live2D角色的增强型前端。


## 功能特点

- **Live2D角色集成**：可交互的Live2D模型，支持音频同步与口型驱动
- **链式模型实时语音交互**：完整的语音对话流程，包含STT（语音转文字）→ LLM（大语言模型）→ TTS（文字转语音）处理链路
- **实时语音通信**：基于声网实时通信（Agora RTC）技术实现


## 前置条件

### 必需的环境变量

1. **声网（Agora）账号**：从[声网控制台](https://console.agora.io/)获取凭证
   - `AGORA_APP_ID` - 您的声网应用ID（必需）

2. **Deepgram账号**：从[Deepgram控制台](https://console.deepgram.com/)获取凭证
   - `DEEPGRAM_API_KEY` - 您的Deepgram API密钥（必需）

3. **OpenAI账号**：从[OpenAI平台](https://platform.openai.com/)获取凭证
   - `OPENAI_API_KEY` - 您的OpenAI API密钥（必需）

4. **ElevenLabs账号**：从[ElevenLabs官网](https://elevenlabs.io/)获取凭证
   - `ELEVENLABS_TTS_KEY` - 您的ElevenLabs API密钥（必需）

### 可选的环境变量

- `AGORA_APP_CERTIFICATE` - 声网应用证书（可选）
- `OPENAI_MODEL` - OpenAI模型名称（可选，默认使用预配置模型）
- `OPENAI_PROXY_URL` - OpenAI API的代理地址（可选）
- `WEATHERAPI_API_KEY` - 天气工具所需的天气API密钥（可选）


## 部署步骤

### 1. 设置环境变量

在`.env`文件中添加以下内容：

```bash
# 声网（音频流传输必需）
AGORA_APP_ID=此处填入您的声网应用ID
AGORA_APP_CERTIFICATE=此处填入您的声网应用证书

# Deepgram（语音转文字必需）
DEEPGRAM_API_KEY=此处填入您的Deepgram API密钥

# OpenAI（大语言模型必需）
OPENAI_API_KEY=此处填入您的OpenAI API密钥
OPENAI_MODEL=gpt-4o

# ElevenLabs（文字转语音必需）
ELEVENLABS_TTS_KEY=此处填入您的ElevenLabs API密钥

# 可选配置
OPENAI_PROXY_URL=此处填入您的代理地址
WEATHERAPI_API_KEY=此处填入您的天气API密钥
```

### 2. 安装依赖

```bash
cd agents/examples/voice-assistant-live2d
task install
```

此命令将安装Python依赖包与前端组件。

### 3. 运行语音助手

```bash
cd agents/examples/voice-assistant-live2d
task run
```

运行后，语音助手将启用所有功能。

### 4. 访问应用

- **前端页面**：http://localhost:3000
- **API服务器**：http://localhost:8080
- **TMAN设计器**：http://localhost:49483


## Live2D模型

本应用包含预配置的Live2D模型：

- **Kei Vowels Pro** - 支持多语言与语音同步的角色模型
- 模型文件存储于`frontend/public/models/`目录，可轻松替换或扩展

### Live2D角色自定义

Live2D前端支持自定义角色模型，操作方式如下：

- 在`frontend/public/models/`目录下替换模型文件
- 支持的文件格式：`.model3.json`、`.moc3`、`.physics3.json`
- 在前端组件中配置角色相关设置


## 配置说明

语音助手的配置文件位于`tenapp/property.json`，内容如下：

```json
{
  "ten": {
    "predefined_graphs": [
      {
        "name": "voice_assistant",
        "auto_start": true,
        "graph": {
          "nodes": [
            {
              "name": "agora_rtc",
              "addon": "agora_rtc",
              "property": {
                "app_id": "${env:AGORA_APP_ID}",
                "app_certificate": "${env:AGORA_APP_CERTIFICATE|}",
                "channel": "ten_agent_test",
                "subscribe_audio": true,
                "publish_audio": true,
                "publish_data": true
              }
            },
            {
              "name": "stt",
              "addon": "deepgram_asr_python",
              "property": {
                "params": {
                  "api_key": "${env:DEEPGRAM_API_KEY}",
                  "language": "en-US"
                }
              }
            },
            {
              "name": "llm",
              "addon": "openai_llm2_python",
              "property": {
                "api_key": "${env:OPENAI_API_KEY}",
                "model": "${env:OPENAI_MODEL}",
                "max_tokens": 512,
                "greeting": "TEN Agent connected. How can I help you today?"
              }
            },
            {
              "name": "tts",
              "addon": "elevenlabs_tts2_python",
              "property": {
                "params": {
                  "key": "${env:ELEVENLABS_TTS_KEY}",
                  "model_id": "eleven_multilingual_v2",
                  "voice_id": "pNInz6obpgDQGcFmaJgB",
                  "output_format": "pcm_16000"
                }
              }
            }
          ]
        }
      }
    ]
  }
}
```

### 配置参数说明

| 参数名称                | 类型   | 默认值 | 说明                                 |
| ----------------------- | ------ | ------ | ------------------------------------ |
| `AGORA_APP_ID`          | 字符串 | -      | 您的声网应用ID（必需）               |
| `AGORA_APP_CERTIFICATE` | 字符串 | -      | 您的声网应用证书（可选）             |
| `DEEPGRAM_API_KEY`      | 字符串 | -      | Deepgram API密钥（必需）             |
| `OPENAI_API_KEY`        | 字符串 | -      | OpenAI API密钥（必需）               |
| `OPENAI_MODEL`          | 字符串 | -      | OpenAI模型名称（可选）               |
| `OPENAI_PROXY_URL`      | 字符串 | -      | OpenAI API的代理地址（可选）         |
| `ELEVENLABS_TTS_KEY`    | 字符串 | -      | ElevenLabs API密钥（必需）           |
| `WEATHERAPI_API_KEY`    | 字符串 | -      | 天气API密钥（可选）                  |


## 自定义扩展

语音助手采用模块化设计，您可通过TMAN设计器轻松替换STT（语音转文字）、LLM（大语言模型）或TTS（文字转语音）模块的服务商。

访问 http://localhost:49483 打开可视化设计器，即可自定义语音助手。详细使用说明请参考[TMAN设计器文档](https://theten.ai/docs/ten_agent/customize_agent/tman-designer)。


## 打包为Docker镜像

**注意**：以下命令需在非Docker容器环境中执行。

### 构建镜像

```bash
cd ai_agents
docker build -f agents/examples/voice-assistant-live2d/Dockerfile -t voice-assistant-live2d .
```

### 运行镜像

```bash
docker run --rm -it --env-file .env -p 8080:8080 -p 3000:3000 voice-assistant-live2d
```

### 访问应用

- 前端页面：http://localhost:3000
- API服务器：http://localhost:8080


## 了解更多

- [声网实时通信（Agora RTC）文档](https://docs.agora.io/en/rtc/overview/product-overview)
- [Deepgram API文档](https://developers.deepgram.com/)
- [OpenAI API文档](https://platform.openai.com/docs)
- [ElevenLabs API文档](https://docs.elevenlabs.io/)
- [Live2D文档](https://docs.live2d.com/)
- [TEN框架文档](https://doc.theten.ai)