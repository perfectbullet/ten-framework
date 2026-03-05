# 延迟分析报告

**日志文件**: `ai_agents/info.log`
**分析日期**: 2026-03-02
**会话 ID**: employee_28_63233052_59

---

## 一、完整端到端延迟（从语音结束到首音播放）

| Turn | 问题 | VAD→ASR | ASR→LLM | LLM→TTS | TTS→TTFB | **端到端** |
|------|------|----------|----------|-----------|----------|
| 1 | 完全平方公式 | 826ms | 2138ms | 817ms | 138ms | **3.92秒** |
| 2 | 我拉一个视频 | 698ms | 1332ms | 1050ms | 137ms | **3.02秒** |
| 3 | 扇形的面积公式 | 798ms | 1261ms | 1095ms | 130ms | **3.28秒** |

**平均端到端延迟**: ~3.4 秒

---

## 二、主要延迟瓶颈分析

### 1. ASR → LLM 延迟（1.2-2.1秒）- **最大瓶颈**

```
Turn 1 延迟构成 (2138ms):
├─ Ollama 验证 (检查文本是否有意义):     118ms (6%)
├─ 中断流程 (取消上一轮 TTS):         ~2000ms (93%) ⚠️
│   ├─ WebSocket 连接关闭等待:             ~2000ms
│   └─ TTS synthesizer 清理:               7ms
├─ 上下文排队:                             3ms (<1%)
└─ LLM API 调用:                          9ms (<1%)

Turn 2 延迟构成 (1332ms):
├─ Ollama 验证:                            ~700ms
├─ 中断流程:                                 ~600ms
├─ 上下文排队:                               3ms
└─ LLM API 调用:                            9ms

Turn 3 延迟构成 (1261ms):
├─ Ollama 验证:                            ~600ms
├─ 中断流程:                                 ~600ms
├─ 上下文排队:                               3ms
└─ LLM API 调用:                            9ms
```

**关键发现**: Turn 1 额外的 800ms 延迟是因为 WebSocket 连接关闭等待了 2 秒。
Turn 2 和 Turn 3 没有需要关闭的 WebSocket 连接，所以更快。

### 2. LLM → TTS 延迟（0.8-1.1秒）

| Turn | LLM→TTS | 原因 |
|------|----------|------|
| 1 | 817ms | DeepSeek API 响应时间 |
| 2 | 1050ms | DeepSeek API 响应时间 |
| 3 | 1095ms | DeepSeek API 响应时间 |

### 3. TTS 同轮内 TTFB 波动

```
Turn 1 tts-request-1:
├─ 片段1: 好的，我正在梳理您的问题要点…      TTFB=137ms
├─ 片段2: 完全平方公式的标准形式是：           TTFB=14ms
├─ 片段3: (a 加减 b) 的平方 等于...           TTFB=14ms
└─ 片段4: ...                               TTFB=1186ms ⚠️
```

**波动原因**:
- 前几个片段 TTFB 很低 (14-137ms)，因为复用了已有的 synthesizer
- 最后一个片段 TTFB 很高 (1186ms)，可能需要重新连接 WebSocket

### 4. 各阶段详细时间戳 (Turn 1)

```
09:51:21.195  VAD Speech end detected
09:51:22.021  ASR result event (FunASR)         +826ms
09:51:22.021  send_asr_result                      +0.2ms
09:51:22.021  _on_asr_result (main_control)      +0.3ms
09:51:22.140  Ollama validation completed           +118ms
09:51:22.140  Calling _interrupt()                 +0ms
09:51:22.140  RTC flushed audio buffer
09:51:22.140  tts_flush received
09:51:22.140  Cancelling TTS request
09:51:24.140  WebSocket connection closed       +2000ms ⚠️
09:51:24.140  TTS synthesizer cleaned
09:51:24.147  _interrupt() completed
09:51:24.147  Sent transcript (user)
09:51:24.150  _queue_context (发送到 LLM)
09:51:24.159  get_chat_completions (LLM请求)   +2138ms
09:51:24.977  LLM first response               +817ms
09:51:24.977  TTS start synthesis
09:51:25.115  TTS TTFB (首音)               +138ms
```

---

## 三、优化建议

| 瓶颈 | 延迟占比 | 优化建议 |
|--------|----------|----------|
| **中断流程 (WebSocket 关闭)** | ~93% (Turn 1) | 优化 WebSocket 关闭逻辑，添加超时机制，避免阻塞等待 |
| Ollama 验证 | ~6% | 考虑缓存常见短语，跳过验证；或优化验证逻辑 |
| LLM API 响应 | ~100% (LLM→TTS) | 使用更快的 LLM 模型或优化 prompt |
| TTS 波动 | N/A | 优化 WebSocket 连接复用机制，避免重复连接 |

---

## 四、日志相关问题

### 1. start_of_sentence/end_of_sentence 未处理警告

```
W on_cmd@agent.py:128 [main_control] Unhandled cmd: start_of_sentence
W on_cmd@agent.py:128 [main_control] Unhandled cmd: end_of_sentence
```

**原因**: VAD 扩展向 main_control 发送 `start_of_sentence` 和 `end_of_sentence` 命令，但 `agent.py` 的 `on_cmd` 方法没有对应的处理逻辑。

**影响**: 仅产生警告日志，不影响功能

**建议**: 在 `on_cmd` 方法中显式忽略这些命令，消除日志噪音。

### 2. Failed to send message 警告

```
W Failed to send message: Failed to find destination of a 'audio_frame' message 'pcm_frame' from graph.
W Failed to send message: Failed to find destination of a 'data' message 'tts_flush_end' from graph.
```

**原因**: 图配置中可能缺少目标扩展的连接配置。

---

## 五、关于时间不匹配问题

**日志时间**: 2026/03/03
**系统时间**: 2026-03-02

**原因分析**:
1. 日志可能是从 Docker 容器中收集的，容器时间和宿主机时间不同步
2. 日志文件可能从其他环境复制而来
3. 使用时区 `+00:00` (UTC)，与本地时区可能不同

**处理建议**: 使用日志中的相对时间差计算延迟，而非绝对时间。

---

**报告生成时间**: 2026-03-02
