# Cosy TTS Python 扩展

一款适用于 TEN 框架的文本转语音扩展，通过 dashscope 工具包与 Cosy TTS 服务实现集成。

## 概述
本扩展借助官方 dashscope Python 软件开发工具包（SDK），调用 Cosy TTS 服务实现高质量的文本转语音合成。它遵循与 TEN 框架中其他 TTS 扩展相同的架构与设计模式，保障了功能的一致性与可维护性。

## 配置
需配置以下环境变量：
- `COSY_TTS_API_KEY`：你的 Cosy 应用程序编程接口密钥（API Key）

## 属性

### 顶层属性
- `dump`：启用音频转储功能以用于调试（类型：布尔值）
- `dump_path`：音频转储文件的存储路径（类型：字符串）

### 文本转语音（TTS）参数（嵌套在 `params` 配置项下）

### 可选参数
- `api_key`：用于身份验证的 Cosy TTS 应用程序编程接口密钥（即 dashscope 应用程序编程接口密钥）
- `model`：选用的文本转语音模型（默认值："cosyvoice-v1"）
- `sample_rate`：音频采样率，单位为赫兹（Hz）（默认值：16000）
- `voice`：合成语音所使用的音色名称（默认值："longxiaochun"）

---
