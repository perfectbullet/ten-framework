# Silero VAD 配置指南

## 核心参数说明

| 参数 | 当前值 | 说明 |
|------|--------|------|
| `threshold` | 0.5 | **VAD 阈值**（0-1）- 判断是否为语音的置信度阈值 |
| `sampling_rate` | 16000 | 采样率（Hz）- 固定为 16000Hz |
| `min_speech_duration_ms` | 500 | 最小语音持续时间 - 小于此值会被丢弃 |
| `min_silence_duration_ms` | 200 | 最小静音持续时间 - 连续静音多久判定为语音结束 |
| `speech_pad_ms` | 30 | 语音填充 - 防止截断语音边缘 |
| `chunk_size` | 512 | 音频块大小 |

## 辅助参数

| 参数 | 说明 |
|------|------|
| `use_onnx` | 使用 ONNX 推理引擎 |
| `enable_asr` | 是否集成 ASR 语音识别 |
| `interruption_threshold` | 打断检测级别 |

---

## 📢 噪声环境推荐配置

根据 Silero VAD 的最佳实践，针对**噪声环境**建议调整以下参数：

```json
{
  "threshold": 0.6,              // ↑ 从 0.5 提高到 0.6
  "min_speech_duration_ms": 800, // ↑ 从 500 提高到 800
  "min_silence_duration_ms": 400,// ↑ 从 200 提高到 400
  "speech_pad_ms": 50             // ↑ 从 30 提高到 50
}
```

### 调整策略说明

| 参数 | 噪声环境调整 | 原因 |
|------|-------------|------|
| **threshold** | `0.5 → 0.6` | 提高阈值，避免将背景噪声误判为语音 |
| **min_speech_duration_ms** | `500ms → 800ms` | 过滤短暂的噪声爆发，只保留持续语音 |
| **min_silence_duration_ms** | `200ms → 400ms` | 避免因短暂静音误判为语音结束 |
| **speech_pad_ms** | `30ms → 50ms` | 增加填充，保护语音边缘不被截断 |

---

## 🎯 分级配置建议

根据噪声强度，可以选择不同级别的配置：

### 轻度噪声（办公室/街道）
```json
"threshold": 0.55,
"min_speech_duration_ms": 600,
"min_silence_duration_ms": 300
```

### 中度噪声（咖啡厅/商场）
```json
"threshold": 0.6,
"min_speech_duration_ms": 800,
"min_silence_duration_ms": 400
```

### 重度噪声（工厂/交通工具）
```json
"threshold": 0.7,
"min_speech_duration_ms": 1000,
"min_silence_duration_ms": 600
```

---

## ⚠️ 注意事项

1. **阈值过高的问题**：`threshold` > 0.7 可能导致轻微声音被漏检
2. **响应延迟**：增加 `min_speech_duration_ms` 会延迟检测开始
3. **实时性权衡**：更保守的配置 = 更高准确性 + 更低实时性

---

## 🔧 快速配置模板

### 默认配置（安静环境）
```json
{
  "use_onnx": true,
  "sampling_rate": 16000,
  "threshold": 0.5,
  "min_speech_duration_ms": 500,
  "min_silence_duration_ms": 200,
  "speech_pad_ms": 30,
  "chunk_size": 512
}
```

### 噪声环境配置
```json
{
  "use_onnx": true,
  "sampling_rate": 16000,
  "threshold": 0.6,
  "min_speech_duration_ms": 800,
  "min_silence_duration_ms": 400,
  "speech_pad_ms": 50,
  "chunk_size": 512
}
```
