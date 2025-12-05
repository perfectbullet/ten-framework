正在使用 "替换文件中的字符串"


```

```


正在使用 "替换文件中的字符串"


```

```


正在使用 "替换文件中的字符串"


```

```


正在使用 "替换文件中的字符串"


```

```


已完成(更新 .github/copilot-instructions.md/5) *5*

完成！我已经成功实现了 FunASR 本地化 ASR 方案，下面是实现总结：

## 🎯 实现总结

### 已完成的核心功能

1. **FunASR 适配器层** (funasr_adapter.py) ✅
   - `FunASRRecognitionResult` - 将 FunASR 消息格式转换为 Dashscope 兼容结构
   - `FunASRRecognitionCallback` - 提供统一的回调接口
   - `FunASRRecognition` - WebSocket 客户端，匹配 Dashscope 的 API
   - 支持词级时间戳提取（从 `stamp_sents[0]['ts_list']`）
   - 线程安全的回调处理（使用 `asyncio.run_coroutine_threadsafe`）

2. **配置系统升级** (config.py) ✅
   - 添加 `asr_backend` 字段（"dashscope" 或 "funasr"）
   - FunASR 专属配置：host、port、is_ssl、chunk_size、mode、hotwords 等
   - 保持向后兼容，默认使用 Dashscope

3. **双后端架构** (extension.py) ✅
   - `start_connection()` 根据配置动态选择后端
   - `_start_dashscope_connection()` - 云端 ASR 初始化
   - `_start_funasr_connection()` - 本地 ASR 初始化（包含 FunASRCallbackAdapter）
   - `vendor()` 方法根据后端返回不同的厂商名称

4. **配置文件** ✅
   - 更新 property.json 添加 `asr_backend` 字段
   - 创建 property_funasr.json FunASR 测试配置

5. **文档更新** ✅
   - 更新英文和中文版 copilot-instructions.md
   - 记录双后端架构、FunASR 消息格式适配、配置说明

### 关键特性

✨ **无缝切换** - 只需修改配置文件中的 `asr_backend` 即可在云端和本地 ASR 之间切换

✨ **统一接口** - 两个后端实现相同的接口，上层代码无需修改

✨ **词级时间戳** - FunASR 提供完整的词级时间戳，解决 Dashscope 的 `words[]` 为空的问题

✨ **线程安全** - 正确处理 WebSocket 线程与 asyncio 事件循环的交互

### 使用方式

**使用 Dashscope（云端）**：
```json
{
    "params": {
        "asr_backend": "dashscope",
        "api_key": "${env:ALIYUN_ASR_BIGMODEL_API_KEY|}"
    }
}
```

**使用 FunASR（本地）**：
```json
{
    "params": {
        "asr_backend": "funasr",
        "funasr_host": "127.0.0.1",
        "funasr_port": "10095",
        "funasr_mode": "2pass"
    }
}
```

### 下一步建议

1. **测试验证**：使用真实的 FunASR 服务器测试连接和识别功能
2. **错误处理**：可以增强 FunASR 连接失败时的错误提示
3. **重连机制**：现有的 `ReconnectManager` 应该已经支持 FunASR，但建议专门测试 WebSocket 断线重连场景
4. **性能调优**：根据实际使用情况调整 `chunk_size` 和 `chunk_interval` 参数

所有代码已经实现完成，可以开始测试了！🚀

已进行更改。