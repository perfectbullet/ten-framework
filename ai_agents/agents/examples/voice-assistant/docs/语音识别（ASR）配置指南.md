# 语音识别（ASR）配置指南

## 问题背景

在使用 Aliyun ASR BigModel 进行语音识别时，可能会遇到以下问题：
- 语音识别结果频繁分段（识别不连贯）
- LLM 和 TTS 模块频繁中断和重新启动
- 语音助手无法正常回复用户

## 根本原因分析

ASR 模块会在识别过程中产生多个中间结果。当前的默认配置会对每个中间结果都触发完整的 LLM-TTS 流程，导致：

1. **频繁中断**：新的 ASR 结果到达时，会立即取消当前的 LLM 请求
2. **重复处理**：同一句话被分成多段识别，每段都单独处理
3. **用户体验差**：语音助手频繁停顿和重新思考

## 解决方案

通过优化 ASR 配置参数，延长静音检测的等待时间，使系统能够等待用户完整说完一句话后再进行处理。

### 关键参数说明

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `max_sentence_silence` | 800ms | 500ms | 静音超时时间，用户停顿超过此时间则认为句子结束 |
| `funasr_mode` | offline | offline | FunASR 运行模式，offline 可获得更准确的识别结果 |
| `funasr_chunk_interval` | 10ms | 10ms | 音频块处理间隔 |
| `funasr_chunk_size` | 5,10,5 | 5,10,5 | 音频块大小配置 |

## 配置修改

### 修改 property.json

````json
// filepath: [property.json](http://_vscodecontentref_/0)
{
  "ten": {
    "predefined_graphs": [
      {
        "name": "voice_assistant",
        "auto_start": true,
        "graph": {
          "nodes": [
            // ...其他节点配置...
            {
              "type": "extension",
              "name": "stt",
              "addon": "aliyun_asr_bigmodel_local_python",
              "extension_group": "stt",
              "property": {
                "params": {
                  "api_key": "${env:ALIYUN_ASR_BIGMODEL_API_KEY|no_api_key}",
                  "asr_backend": "funasr",
                  "funasr_host": "192.168.8.230",
                  "funasr_port": "30095",
                  "funasr_is_ssl": true,
                  "funasr_chunk_size": "5,10,5",
                  "funasr_chunk_interval": 10,
                  "funasr_mode": "offline",
                  "funasr_hotwords": "",
                  "funasr_itn": true,
                  "max_sentence_silence": 500,
                  "language_hints": [
                    "zh"
                  ],
                  "sample_rate": 16000
                }
              }
            }
            // ...其他节点配置...
          ]
        }
      }
    ]
  }
}