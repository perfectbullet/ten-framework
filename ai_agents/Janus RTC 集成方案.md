# Janus WebRTC 服务器集成方案

## 目录

1. [方案概述](#方案概述)
2. [架构设计](#架构设计)
3. [实施步骤](#实施步骤)
4. [代码实现](#代码实现)
5. [配置说明](#配置说明)
6. [部署指南](#部署指南)
7. [测试计划](#测试计划)

---

## 方案概述

### 背景

当前系统使用 Agora RTC 声网（云端 SaaS），在内网环境中无法访问 Agora 云端服务。需要替代为开源的本地 WebRTC 服务器。

### 目标

- ✅ 完全内网部署，不依赖外网
- ✅ 开源可控，可自主维护
- ✅ 保持现有 STT/LLM/TTS 流程不变
- ✅ 替换 agora_rtc 扩展为 janus_rtc

### 技术选型

| 方案 | 选定 | 原因 |
|------|--------|------|
| Janus WebRTC | ✅ | 成熟稳定、插件化、文档完善 |
| mediasoup | ❌ | API 更底层，开发难度高 |
| Kurento | ❌ | 功能冗余，过度设计 |
| Jitsi | ❌ | 完整会议方案，不适合作为组件 |

---

## 架构设计

### 整体架构

```
┌───────────────────────────────────────────────────────────────────┐
│                    内网环境                                │
├───────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────┐       │
│  │        前端/移动端                            │       │
│  │  ┌────────────────────────────────────────┐        │       │
│  │  │  WebRTC 浏览器/客户端            │        │       │
│  │  └────────────────┬───────────────────────┘        │       │
│  │                   │ WebSocket                │       │
│  │                   ▼                         │       │
│  └──────────────────┬─────────────────────────────────────┘       │
│                     │                                   │
│  ┌────────────▼────────────────────────────────────────┐      │
│  │          Janus Gateway                    │      │
│  │  ┌────────────────────────────────────────┐        │      │
│  │  │  - Plugin: janus.plugin.videoroom    │      │
│  │  │  - Plugin: janus.plugin.audiobridge  │      │
│  │  │  - Plugin: janus.plugin.streaming    │      │
│  │  └────────────────┬───────────────────────┘        │      │
│  │                │ HTTP/WebSocket               │      │
│  │                ▼                            │      │
│  └───────────────┬──────────────────────────────────────┘      │
│                │                                     │
│  ┌────────────▼──────────────────────────────────────┐       │
│  │        TEN Agent                        │       │
│  │  ┌────────────────────────────────────────┐    │       │
│  │  │  janus_rtc Extension (Go/C)        │    │       │
│  │  │  - WebSocket 连接到 Janus         │    │       │
│  │  │  - 接收音频流                     │    │       │
│  │  │  - 发布音频流                     │    │       │
│  │  │  - 处理用户事件                   │    │       │
│  │  └────────────────┬───────────────────────┘    │       │
│  │                │                            │       │
│  │  ┌────────────▼────────────────────────────┐    │       │
│  │  │  Stream ID Adapter                    │    │       │
│  │  └────────────────┬───────────────────────┘    │       │
│  │                │                            │       │
│  │  ┌────────────▼──────┐ ┌────────────▼──┐    │       │
│  │  │  VAD             │ │  STT            │    │       │
│  │  └────────────────────┘ └────────────────────┘    │       │
│  │                │                            │       │
│  └────────────────┬────────────────────────────────────┘       │
│                │                                     │
└────────────────┼───────────────────────────────────────────────┘
                 │
                 ▼
         LLM ──→ TTS
```

### 数据流

#### 音频输入流

```
用户说话
    ↓
浏览器 → WebRTC → Janus Server
    ↓
WebSocket (janus_rtc Extension)
    ↓
Audio Frame (PCM)
    ↓
Stream ID Adapter
    ↓
分发到:
  - VAD (语音活动检测)
  - STT (语音识别)
```

#### 音频输出流

```
TTS 生成音频
    ↓
PCM Frame
    ↓
WebSocket (janus_rtc Extension)
    ↓
Janus Server
    ↓
WebRTC
    ↓
用户听到 AI 回复
```

#### 用户事件流

```
用户加入
    ↓
Janus 触发事件
    ↓
WebSocket Event
    ↓
janus_rtc Extension
    ↓
发送 on_user_joined Command
    ↓
main_control Extension
```

---

## 实施步骤

### 阶段 1：环境准备（第 1-3 天）

#### 1.1 部署 Janus 服务器

**目标**：在本地内网搭建 Janus Gateway

```bash
# 1. 拉取镜像
docker pull meetecho/janus-gateway:latest

# 2. 创建数据目录
mkdir -p /data/janus/{data,recordings}

# 3. 启动容器
docker run -d \
  --name janus-server \
  -p 8088:8088 \
  -p 8188:8188 \
  -v /data/janus/data:/opt/janus/share/janus/cfg \
  -v /data/janus/recordings:/opt/janus/share/janus/recordings \
  -e JANUS_SERVER=http://0.0.0.0:8088 \
  -e JANUS_ADMINSECRET=janusrocks \
  meetecho/janus-gateway:latest
```

**验证**：
```bash
# 访问 Janus Gateway
curl http://localhost:8088/janus/info

# 访问 Admin API
curl -X POST http://localhost:7088/admin \
  -H "Content-Type: application/json" \
  -H "Admin-Secret: janusrocks" \
  -d '{"janus": "create", "transaction": "create_session"}'
```

#### 1.2 准备开发环境

```bash
# 1. 创建扩展目录
cd /home/zj/ten-framework/ai_agents/agents/ten_packages/extension
mkdir -p janus_rtc/src

# 2. 初始化 Go 模块
cd janus_rtc/src
go mod init janus_rtc

# 3. 安装依赖
go get github.com/TEN-framework/ten_runtime_go
```

---

### 阶段 2：janus_rtc 扩展开发（第 4-10 天）

#### 2.1 目录结构

```
janus_rtc/
├── src/
│   ├── main.go              # 入口文件
│   ├── janus_client.go      # Janus WebSocket 客户端
│   ├── audio_handler.go      # 音频流处理
│   ├── event_handler.go      # 事件处理（加入/离开）
│   └── go.mod              # Go 模块定义
├── manifest.json            # TEN 扩展清单
├── property.json           # 默认配置
└── README.md              # 使用文档
```

#### 2.2 核心功能实现

##### 功能清单

| 功能 | 优先级 | 工作量 |
|------|---------|---------|
| WebSocket 连接到 Janus | P0 | 2 天 |
| 订阅远程音频流 | P0 | 3 天 |
| 发布本地音频流 | P0 | 3 天 |
| 处理用户加入事件 | P1 | 2 天 |
| 处理用户离开事件 | P1 | 2 天 |
| 实现 flush 命令（清空缓冲） | P1 | 2 天 |
| 完整的日志和错误处理 | P1 | 1 天 |
| 配置管理和环境变量 | P2 | 1 天 |

##### 实现顺序

**第 1 周：基础连接**
1. WebSocket 客户端实现
2. Janus Gateway 集成
3. Session 和 Handle 管理

**第 2 周：音频处理**
1. 音频订阅和发布
2. PCM 数据帧处理
3. 流 ID 适配

**第 3 周：事件和控制**
1. 用户加入/离开事件
2. flush 命令实现
3. 错误处理和重连

---

### 阶段 3：配置集成（第 11-12 天）

#### 3.1 修改 property.json

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
              "type": "extension",
              "name": "janus_rtc",
              "addon": "janus_rtc",
              "extension_group": "default",
              "property": {
                "janus_server": "${env:JANUS_SERVER|http://localhost:8088}",
                "room": "${env:JANUS_ROOM|agent_room}",
                "user_id": "${env:JANUS_USER_ID|agent}",
                "subscribe_audio": true,
                "publish_audio": true,
                "publish_data": true
              }
            },
            {
              "type": "extension",
              "name": "stt",
              "addon": "aliyun_asr_bigmodel_local_python",
              "extension_group": "stt",
              // ... 保持不变
            },
            {
              "type": "extension",
              "name": "llm",
              "addon": "openai_llm2_python",
              "extension_group": "chatgpt",
              // ... 保持不变
            },
            {
              "type": "extension",
              "name": "tts",
              "addon": "cosy_tts_python_local",
              "extension_group": "tts",
              // ... 保持不变
            },
            {
              "type": "extension",
              "name": "main_control",
              "addon": "main_python",
              "extension_group": "control",
              // ... 保持不变
            },
            {
              "type": "extension",
              "name": "streamid_adapter",
              "addon": "streamid_adapter",
              "property": {}
            },
            {
              "type": "extension",
              "name": "vad",
              "addon": "silero_vad_python",
              "property": {}
            }
          ],
          "connections": [
            {
              "extension": "main_control",
              "cmd": [
                {
                  "names": [
                    "on_user_joined",
                    "on_user_left"
                  ],
                  "source": [
                    {
                      "extension": "janus_rtc"
                    }
                  ]
                }
              ],
              "data": [
                {
                  "name": "asr_result",
                  "source": [
                    {
                      "extension": "stt"
                    }
                  ]
                }
              ]
            },
            {
              "extension": "janus_rtc",
              "audio_frame": [
                {
                  "name": "pcm_frame",
                  "dest": [
                    {
                      "extension": "streamid_adapter"
                    }
                  ]
                },
                {
                  "name": "pcm_frame",
                  "source": [
                    {
                      "extension": "tts"
                    }
                  ]
                }
              ],
              "data": [
                {
                  "name": "data",
                  "dest": [
                    {
                      "extension": "message_collector"
                    }
                  ],
                  "source": [
                    {
                      "extension": "main_control"
                    }
                  ]
                }
              ]
            }
          ]
        }
      }
    ]
  }
}
```

#### 3.2 环境变量配置

```bash
# Janus 配置
export JANUS_SERVER=http://192.168.1.100:8088
export JANUS_ROOM=agent_room
export JANUS_USER_ID=agent
export JANUS_ADMIN_SECRET=janusrocks

# 其他配置保持不变
export AGORA_APP_ID=xxx  # 可移除
export AGORA_APP_CERTIFICATE=xxx  # 可移除
export ALIYUN_ASR_BIGMODEL_API_KEY=xxx
export OPENAI_API_KEY=xxx
export COSY_TTS_API_KEY=xxx
```

---

### 阶段 4：前端适配（第 13-14 天）

#### 4.1 WebRTC 客户端

使用 Janus 的 JavaScript 库：

```javascript
// 使用 janus.js 库
import Janus from 'janus-gateway';

class JanusClient {
  constructor(serverUrl, room) {
    this.janus = null;
    this.room = room;
    this.serverUrl = serverUrl;
    this.localStream = null;
    this.remoteStream = null;
  }

  async connect() {
    this.janus = new Janus({
      server: this.serverUrl,
      success: (janus) => {
        this.attachVideoRoomPlugin();
      },
      error: (error) => {
        console.error('Janus connection error:', error);
      }
    });
  }

  attachVideoRoomPlugin() {
    this.janus.attach({
      plugin: "janus.plugin.videoroom",
      opaqueId: "videoroomtest",
      success: (pluginHandle) => {
        this.videoRoom = pluginHandle;
        this.joinRoom();
      }
    });
  }

  joinRoom() {
    this.videoRoom.send({
      message: {
        request: "join",
        room: this.room,
        display: "user"
      }
    });

    // 发布本地音频流
    if (this.localStream) {
      this.videoRoom.send({
        message: {
          request: "configure",
          audio: true
        },
        jsep: {
          type: 'audio',
          sdp: this.localStream.localDescription.sdp
        }
      });
    }
  }

  onRemoteStream(stream) {
    this.remoteStream = stream;
    // 播放音频
    const audio = new Audio();
    audio.srcObject = stream;
    audio.play();
  }

  async startLocalAudio() {
    this.localStream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false
    });
  }
}

// 使用示例
const client = new JanusClient(
  'http://192.168.1.100:8088/janus',
  'agent_room'
);

await client.connect();
await client.startLocalAudio();
```

---

## 代码实现

### main.go - 入口文件

```go
package main

import (
    "context"
    "log/slog"
    "os"

    ten "ten_framework/ten_runtime"
    janus "github.com/meetecho/janus-gateway/janus"
)

type JanusRTCExtension struct {
    ten.BaseExtension

    tenEnv      ten.TenEnv
    config      *Config
    janusClient *janus.Client
    room       *janus.VideoRoomPlugin
    audioSub    *janus.WebRTCUpstream
}

type Config struct {
    JanusServer   string `json:"janus_server"`
    Room          string `json:"room"`
    UserID        string `json:"user_id"`
    SubscribeAudio bool   `json:"subscribe_audio"`
    PublishAudio   bool   `json:"publish_audio"`
    PublishData   bool   `json:"publish_data"`
}

func main() {
    app := ten.NewDefaultApp(&JanusRTCExtension{})
    app.Run(true)
}

func (p *JanusRTCExtension) OnConfigure(tenEnv ten.TenEnv) {
    // 读取配置
    config := &Config{}
    if err := tenEnv.InitPropertyFromJSON(config); err != nil {
        slog.Error("Failed to load config", "err", err)
        return
    }
    p.config = config
    p.tenEnv = tenEnv

    slog.Info("JanusRTC configured",
        "server", config.JanusServer,
        "room", config.Room,
        "user_id", config.UserID)
}

func (p *JanusRTCExtension) OnStart(tenEnv ten.TenEnv) {
    // 连接到 Janus
    if err := p.connectToJanus(); err != nil {
        slog.Error("Failed to connect to Janus", "err", err)
        return
    }

    // 加入房间
    if err := p.joinRoom(); err != nil {
        slog.Error("Failed to join room", "err", err)
        return
    }

    tenEnv.OnStartDone()
}

func (p *JanusRTCExtension) connectToJanus() error {
    p.janusClient = janus.New(&janus.Config{
        Server:      p.config.JanusServer,
        Token:       "",
        APIKey:      "",
        API:         janus.DefaultAPI(),
        // WebSocket 传输
        Transports:   "websocket",
    })

    return p.janusClient.Connect(&janus.ClientCallbacks{
        Connected: func() {
            slog.Info("Connected to Janus")
        },
        Disconnected: func() {
            slog.Warn("Disconnected from Janus, reconnecting...")
            p.reconnect()
        },
    })
}

func (p *JanusRTCExtension) joinRoom() error {
    // 附加 VideoRoom 插件
    handle := p.janusClient.AttachPlugin("janus.plugin.videoroom", &janus.PluginCallbacks{
        Attached: func(handle *janus.PluginHandle) {
            p.room = handle.(*janus.VideoRoomPlugin)
            slog.Info("VideoRoom plugin attached")

            // 加入房间
            p.room.Join(&janus.JoinOptions{
                Room:   p.config.Room,
                ID:      p.config.UserID,
                Display: "AI Agent",
            })
        },
        DataMessage: func(handle *janus.PluginHandle, msg map[string]interface{}) {
            p.handleJanusData(msg)
        },
        Detached: func() {
            slog.Warn("VideoRoom plugin detached")
        },
    })

    return nil
}

func (p *JanusRTCExtension) OnData(tenEnv ten.TenEnv, data ten.Data) {
    dataType := data.GetName()
    content := data.GetPropertyByName("data").Value

    switch dataType {
    case "pcm_frame":
        // 收到 TTS 音频数据
        p.publishAudio(content.([]byte))
    case "flush":
        // 收到清空缓冲区命令
        p.flushAudioBuffer()
    }
}

func (p *JanusRTCExtension) publishAudio(audioData []byte) {
    if !p.config.PublishAudio {
        return
    }

    // 通过 Janus 发布音频
    p.room.Send(&janus.SendOptions{
        Data: audioData,
    })
}

func (p *JanusRTCExtension) handleJanusData(msg map[string]interface{}) {
    msgType, ok := msg["videoroom"].(string)
    if !ok {
        return
    }

    switch msgType {
    case "event":
        event, _ := msg["plugindata"].(map[string]interface{})
        eventType, _ := event["event"].(string)

        switch eventType {
        case "joined":
            // Agent 加入成功
            slog.Info("Joined room successfully")

        case "joined":
            // 用户加入房间
            users, _ := event["participants"].([]interface{})
            for _, user := range users {
                p.tenEnv.SendCmd("on_user_joined", user)
            }

        case "leaving":
            // 用户离开房间
            userID, _ := event["leaving"].(string)
            p.tenEnv.SendCmd("on_user_left", map[string]interface{}{
                "user_id": userID,
            })
        }
    }

    case "audio":
        // 收到远程用户音频
        audioData, _ := msg["data"].([]byte)
        p.tenEnv.SendData("pcm_frame", audioData, nil)
    }
}

func (p *JanusRTCExtension) flushAudioBuffer() {
    // 清空 Janus 的音频缓冲区
    p.room.Send(&janus.SendOptions{
        Message: map[string]interface{}{
            "request": "configure",
            "audio":    true,
        },
    })
}

func (p *JanusRTCExtension) reconnect() {
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()

    for {
        select {
        case <-ctx.Done():
            return
        default:
            if err := p.connectToJanus(); err == nil {
                if err := p.joinRoom(); err == nil {
                    slog.Info("Reconnected to Janus")
                    return
                }
            }
        }
        time.Sleep(1 * time.Second)
    }
}

func (p *JanusRTCExtension) OnStop(tenEnv ten.TenEnv) {
    // 清理资源
    if p.room != nil {
        p.room.Leave()
    }
    if p.janusClient != nil {
        p.janusClient.Disconnect()
    }
}
```

---

## 配置说明

### manifest.json

```json
{
  "type": "extension",
  "name": "janus_rtc",
  "version": "0.1.0",
  "api_version": "0.1.0",
  "dependencies": [
    {
      "type": "system",
      "name": "ten_runtime_go",
      "version": "0.11"
    },
    {
      "type": "addon",
      "name": "janus_client",
      "version": "1.0.0"
    }
  ],
  "supported_ten_versions": {
    "min": "0.11",
    "max": "0.11"
  }
}
```

### property.json

```json
{
  "ten": {
    "app_id": "",
    "log": {
      "handlers": [
        {
          "matchers": [
            {
              "level": "info"
            }
          ],
          "formatter": {
            "type": "plain",
            "colored": true
          },
          "emitter": {
            "type": "console",
            "config": {
              "stream": "stdout"
            }
          }
        }
      ]
    }
  }
}
```

---

## 部署指南

### Docker 部署（推荐）

#### 1. Janus 服务器部署

**Docker Compose**：

```yaml
version: '3.8'

services:
  janus:
    image: meetecho/janus-gateway:latest
    container_name: janus-gateway
    ports:
      - "8088:8088"      # HTTP/WebSocket
      - "8188:8188"      # Admin API
      - "10000-10100:10000-10100/udp"  # RTP 端口
    volumes:
      - ./janus/data:/opt/janus/share/janus/cfg
      - ./janus/recordings:/opt/janus/share/janus/recordings
    environment:
      - JANUS_SERVER=http://0.0.0.0:8088
      - JANUS_ADMIN_SECRET=${JANUS_ADMIN_SECRET:-janusrocks}
      - RTP_PORT_RANGE=10000-10100
    restart: unless-stopped
    networks:
      - ai_agents_network

networks:
  ai_agents_network:
    driver: bridge
```

**启动命令**：
```bash
docker compose -f janus-docker-compose.yml up -d
```

#### 2. TEN Agent 部署

```bash
# 1. 构建扩展
cd ai_agents/agents/ten_packages/extension/janus_rtc/src
go build -o ../bin/janus_rtc.so -buildmode=cshared

# 2. 安装依赖
cd /path/to/voice-assistant/tenapp
tman install

# 3. 启动 Agent
./scripts/start.sh
```

---

## 测试计划

### 测试环境

- ✅ 内网环境（完全隔离外网）
- ✅ 2 个客户端（模拟用户）
- ✅ 日志和监控

### 测试用例

| 用例 | 描述 | 预期结果 | 优先级 |
|------|------|----------|--------|
| **TC-01** | Janus 服务器启动 | 服务正常运行 | P0 |
| **TC-02** | Agent 连接 Janus | 成功加入房间 | P0 |
| **TC-03** | 用户连接房间 | 收到 on_user_joined | P0 |
| **TC-04** | 用户说话 | Agent 收到音频流 | P0 |
| **TC-05** | Agent 回复 | 用户收到音频流 | P0 |
| **TC-06** | 用户离开 | 收到 on_user_left | P1 |
| **TC-07** | 断连重连 | 自动恢复连接 | P1 |
| **TC-08** | 多用户并发 | 正确处理多个用户 | P1 |
| **TC-09** | 音频质量 | 无明显延迟/失真 | P2 |
| **TC-10** | 长时间稳定性 | 24 小时无崩溃 | P1 |

### 测试方法

#### TC-01: Janus 服务器启动

```bash
# 1. 启动 Janus
docker compose up -d

# 2. 检查健康状态
curl http://localhost:8088/janus/info

# 3. 查看日志
docker logs janus-gateway

# 预期：返回 JSON 格式的 Janus 信息
```

#### TC-03: 用户加入测试

```javascript
// 前端测试代码
const client = new JanusClient('ws://192.168.1.100:8088', 'agent_room');
await client.connect();

// Agent 端应该收到 on_user_joined 命令
```

#### TC-04-05: 语音通话测试

```bash
# 1. 启动 Agent
cd /path/to/voice-assistant
./scripts/start.sh

# 2. 前端连接并说话
# 测试音频流是否正常

# 3. 查看日志
tail -f /var/log/agent.log | grep -E "pcm_frame|audio"

# 预期：
# - 用户音频 → pcm_frame → VAD/STT
# - TTS 音频 → pcm_frame → 用户听到
```

#### TC-07: 断连重连测试

```bash
# 1. 启动 Agent 后停止 Janus
docker compose stop janus

# 2. 等待 10 秒
sleep 10

# 3. 重启 Janus
docker compose start janus

# 4. 查看日志
tail -f /var/log/agent.log | grep -E "Disconnected|Reconnected"

# 预期：Agent 自动重连成功
```

---

## 风险和缓解

| 风险 | 等级 | 缓解措施 |
|------|--------|----------|
| **WebSocket 连接不稳定** | 中 | 实现自动重连、心跳检测 |
| **音频延迟** | 低 | 优化网络配置、使用本地网络 |
| **多用户并发** | 中 | 充分测试、限制最大并发数 |
| **配置复杂度** | 低 | 提供默认配置、详细文档 |
| **资源占用** | 低 | 监控内存/CPU、合理配置 |

---

## 时间估算

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| 阶段 1 | 环境准备 | 1-3 天 |
| 阶段 2 | janus_rtc 开发 | 10-12 天 |
| 阶段 3 | 配置集成 | 2 天 |
| 阶段 4 | 前端适配 | 2-3 天 |
| 测试和优化 | 3-5 天 |
| **总计** | | **20-25 天** |

---

## 参考资料

### Janus 官方资源

- **官网**：https://janus.conf.meetecho.com/
- **文档**：https://janus.conf.meetecho.com/docs/
- **GitHub**：https://github.com/meetecho/janus-gateway
- **API 文档**：https://janus.conf.meetecho.com/docs/rest.html

### TEN Framework

- **文档**：https://theten.ai/docs
- **扩展开发**：https://theten.ai/docs/extension-development

### 示例代码

- **Janus 示例**：https://github.com/meetecho/janus-gateway/tree/main/html
- **WebRTC 集成**：https://webrtc.org/

---

## 附录

### A. 配置检查清单

- [ ] Janus 服务器部署完成
- [ ] 网络端口开放（8088, 8188）
- [ ] janus_rtc 扩展编译完成
- [ ] property.json 更新完成
- [ ] 环境变量配置完成
- [ ] API Server 更新（如需）
- [ ] 前端适配完成
- [ ] 测试用例全部通过
- [ ] 文档编写完成

### B. 迁移检查清单

| 功能 | Agora RTC | Janus RTC | 状态 |
|------|-----------|------------|------|
| 音频输入 | ✓ | ✓ | 兼容 |
| 音频输出 | ✓ | ✓ | 兼容 |
| 用户事件 | ✓ | ✓ | 兼容 |
| flush 命令 | ✓ | ✓ | 兼容 |
| 数据消息 | ✓ | ✓ | 兼容 |
| 流 ID 管理 | ✓ | N | 需要适配 |
| Token 认证 | ✓ | N | 不需要 |

### C. 命令对照表

| Agora RTC | Janus RTC | 说明 |
|-----------|------------|------|
| `on_user_joined` | `on_user_joined` | 用户加入事件 |
| `on_user_left` | `on_user_left` | 用户离开事件 |
| `flush` | `flush` | 清空音频缓冲 |
| `pcm_frame` | `pcm_frame` | PCM 音频帧 |
| `data` | `data` | 数据消息 |
