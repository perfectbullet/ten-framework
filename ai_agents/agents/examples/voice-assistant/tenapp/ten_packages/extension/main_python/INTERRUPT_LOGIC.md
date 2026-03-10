# 语音助手打断逻辑说明文档

## 概述

本文档详细说明了语音助手中打断机制的实现逻辑，包括打断的触发方式、处理流程以及相关的代码实现。

---

## 一、打断触发的四种方式

### 1. 打断短语检测

**触发位置：** `_on_asr_result` 方法（第151-157行）

**触发条件：**
- 收到最终的ASR结果（`event.final == True`）
- 文本内容包含打断短语

**打断短语列表：**
```python
self._interrupt_phrases = {
    "打断一下", "停一下", "别说了",
    "stop", "wait", "hold on",
}
```

**支持的打断模式：**
- 直接匹配：文本包含以上短语（不区分大小写）
- 重复字符：如"停停停"、"等等等"、"别别别"（重复3次及以上）
- 英文重复：如"stopstop"（重复2次及以上）

**特点：**
- 不将打断短语发送给LLM
- 仅触发打断动作
- 仍然会将文本记录到转录中

**代码示例：**
```python
if event.final and self._is_interrupt_phrase(event.text):
    self.ten_env.log_info(f"[MainControlExtension] Interrupt phrase detected...")
    await self._interrupt()
    await self._send_transcript("user", event.text, event.final, stream_id)
    return  # 不发送给 LLM
```

---

### 2. 长文本ASR结果

**触发位置：** `_on_asr_result` 方法（第175-180行）

**触发条件：**
- 收到最终的ASR结果（`event.final == True`）
- 文本长度大于8个字符（`len(event.text) > 8`）

**特点：**
- 打断当前正在进行的对话
- 将文本发送给LLM处理
- 增加turn_id计数

**代码示例：**
```python
if event.final and len(event.text) > 8:
    self.ten_env.log_info(f"[MainControlExtension] Calling _interrupt()...")
    await self._interrupt()
    self.ten_env.log_info("[MainControlExtension] _interrupt() completed")

if event.final:
    self.turn_id += 1
    llm_text = corrected_text if corrected_text else event.text
    await self.agent.queue_llm_input(llm_text)
```

---

### 3. 直接命令

**触发位置：** `on_cmd` 方法（第224-228行）

**触发条件：**
- 收到名称为"interrupt"的命令（Cmd）

**特点：**
- 直接执行打断动作
- 适用于外部系统通过命令方式触发打断

**代码示例：**
```python
if cmd_name == "interrupt":
    ten_env.log_info("[MainControlExtension] Received interrupt command")
    await self._interrupt()
    return
```

---

### 4. property.json 文件检查

**触发位置：** `_periodic_check_interrupt` 后台任务（第403-412行）

**触发条件：**
- 定期检查（每1秒）
- property.json 文件中 `ten.interrupt.action == "flush"`
- 时间戳比上次处理的新（避免重复处理）

**检查流程：**
1. 通过父进程PID获取命令行参数
2. 从命令行中提取 `--property` 参数路径
3. 读取 property.json 文件
4. 检查 `ten.interrupt.action` 和 `ten.interrupt.timestamp`
5. 如果满足条件则触发打断
6. 清除 interrupt 标记

**特点：**
- 支持外部系统通过修改配置文件触发打断
- 使用时间戳避免重复处理
- 处理完成后清除标记

**代码示例：**
```python
async def _periodic_check_interrupt(self):
    """定期检查 property.json 的后台任务"""
    while not self.stopped:
        await self._check_interrupt_file()
        await asyncio.sleep(1)  # 每 1 秒检查一次
```

---

## 二、`_interrupt` 方法详解

**方法位置：** 第307-318行

**核心功能：** 中断正在进行的大语言模型（LLM）和语音合成（TTS）生成过程

### 子方法1：刷新 LLM

```python
await self.agent.flush_llm()
```

**功能：**
- 停止当前正在进行的LLM生成
- 清空LLM的待处理队列
- 防止产生不相关的响应

---

### 子方法2：刷新 TTS

```python
await _send_data(
    self.ten_env,
    "tts_flush",
    "tts",
    {"flush_id": str(uuid.uuid4())}
)
```

**功能：**
- 向TTS扩展发送刷新指令
- 停止当前正在进行的语音合成
- 使用唯一的flush_id标识此次刷新操作
- 清空TTS的待处理队列

---

### 子方法3：刷新 RTC

```python
await _send_cmd(self.ten_env, "flush", "agora_rtc")
```

**功能：**
- 向Agora RTC扩展发送刷新指令
- 停止当前正在播放的音频
- 清空音频播放队列
- 为新的对话做好准备

---

## 三、打断机制的三级流程

```
用户语音输入
    ↓
┌─────────────────────────────────────┐
│ Level 1: ASR 识别阶段               │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 检测打断短语                    │ │
│ │ ("打断一下", "stop", "stopstop") │ │
│ └────────────┬────────────────────┘ │
│              ↓ 是打断短语           │
│         ┌────────────────┐         │
│         │ 触发 _interrupt│         │
│         └────────────────┘         │
└─────────────┬───────────────────────┘
              ↓ 最终结果且长度>8
         ┌────────────────┐
         │ 触发 _interrupt│
         └────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Level 2: 打断执行阶段                │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 1. flush_llm()                 │ │
│ │    停止LLM生成                 │ │
│ └────────────┬────────────────────┘ │
│              ↓                       │
│ ┌─────────────────────────────────┐ │
│ │ 2. send_data(tts_flush)         │ │
│ │    停止TTS合成                 │ │
│ └────────────┬────────────────────┘ │
│              ↓                       │
│ ┌─────────────────────────────────┐ │
│ │ 3. send_cmd(flush, agora_rtc)   │ │
│ │    停止音频播放                 │ │
│ └─────────────────────────────────┘ │
└─────────────┬───────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ Level 3: 清理与重新准备             │
│                                     │
│ • 清空各扩展的待处理队列            │
│ • 生成新的turn_id                   │
│ • 准备接收新的用户输入              │
│ • 清除interrupt标记（方式4）        │
└─────────────────────────────────────┘
```

---

## 四、其他打断方式

### 后台任务启动

**位置：** `on_start` 方法（第211-212行）

```python
asyncio.create_task(self._periodic_check_interrupt())
```

在扩展启动时创建后台任务，定期检查property.json中的interrupt标记。

---

## 五、关键变量说明

| 变量名 | 类型 | 说明 |
|--------|------|------|
| `_interrupt_phrases` | set | 打断短语集合，用于快速检测 |
| `_last_interrupt_timestamp` | int | 上次处理interrupt的时间戳，避免重复处理 |
| `turn_id` | int | 当前对话轮次ID，打断后递增 |
| `sentence_buffer` | SentenceBuffer | 句子缓冲区，用于LLM输出处理 |

---

## 六、日志输出格式

所有打断相关的操作都会在日志中输出，格式如下：

- 打断短语检测：`[MainControlExtension] Interrupt phrase detected: '{text}', calling _interrupt()`
- 长文本触发：`[MainControlExtension] Calling _interrupt() due to ASR result (final={final}, text_len={len})`
- 命令触发：`[MainControlExtension] Received interrupt command`
- 文件检测：`[MainControlExtension] Detected interrupt from property.json, timestamp={timestamp}`
- 打断完成：`[MainControlExtension] Interrupt signal sent............................`

---

## 七、调试建议

1. **查看打断触发：** 搜索日志中的 "Interrupt" 关键词
2. **查看打断执行：** 查找 "Interrupt signal sent" 标记
3. **查看文件检查：** 搜索 "Detected interrupt from property.json"
4. **验证打断效果：** 观察日志中turn_id的变化和LLM/TTS的重新开始

---

## 八、注意事项

1. **打断短语选择：** 避免使用容易误触发的短语（如单独的"好的"、"等一下"）
2. **时间戳机制：** 方式4使用时间戳确保同一个interrupt标记只处理一次
3. **后台任务：** `_periodic_check_interrupt` 在扩展停止时自动结束
4. **文本发送：** 打断短语不发送给LLM，但仍会记录到转录中

---

*文档生成时间：2026-03-10*
*源文件：extension.py*
