# FunASR Adapter 测试说明

## 概述

为 `funasr_adapter.py` 创建的纯功能测试套件，无需依赖 TEN Framework 运行时或外部 FunASR 服务器。

## 测试文件

### `test_adapter.py`
主要的测试文件，包含所有测试用例：
- `TestConfiguration` - 配置加载和验证测试
- `TestAudioProcessing` - 音频文件处理测试
- `TestFunASRRecognitionResult` - 识别结果解析测试
- `TestFunASRRecognition` - Recognition 类核心功能测试
- `TestAudioTimeline` - 音频时间轴计算测试
- `TestErrorHandling` - 错误处理测试


## 运行方式

### 1. 基本用法

#### 使用 property.json 配置（默认）
```bash
# 运行所有测试（使用 property.json 配置）
python test_adapter.py

# 详细输出模式
python test_adapter.py --verbose
```

#### 使用自定义配置
```bash
# 指定服务器地址和端口
python test_adapter.py --host 127.0.0.1 --port 10095

# 指定音频文件
python test_adapter.py --audio-file my_audio.wav

# 使用 SSL 连接
python test_adapter.py --host 127.0.0.1 --port 10095 --is-ssl
```

#### 使用默认配置（不依赖 property.json）
```bash
# 不使用 property.json，使用内置默认配置
python test_adapter.py --no-config --host 127.0.0.1 --port 10095
```

### 2. 完整测试套件
```bash
# 运行所有测试
python test_adapter.py

# 或使用运行器
python run_tests.py
```

## 命令行参数

```bash
python test_adapter.py [选项]

选项：
  -h, --help            显示帮助信息
  --host HOST           FunASR 服务器地址 (默认: property.json)
  --port PORT           FunASR 服务器端口 (默认: property.json)
  --is-ssl              是否使用 SSL 连接
  --audio-file AUDIO_FILE 测试音频文件路径
  --test-name TEST_NAME   运行特定测试用例
  --verbose             详细输出模式
  --no-config           不使用 property.json，使用默认配置
```

### 常用参数组合

1. **默认配置**：
   ```bash
   python test_adapter.py
   ```

2. **自定义服务器配置**：
   ```bash
   python test_adapter.py --host 192.168.1.100 --port 10095
   ```

3. **自定义音频文件**：
   ```bash
   python test_adapter.py --audio-file custom_audio.wav
   ```

4. **不使用 property.json**：
   ```bash
   python test_adapter.py --no-config --host 127.0.0.1 --port 10095
   ```

5. **SSL 连接**：
   ```bash
   python test_adapter.py --host 127.0.0.1 --port 10095 --is-ssl
   ```

6. **详细输出**：
   ```bash
   python test_adapter.py --verbose
   ```



## 测试覆盖

### 配置管理
- 从 `property.json` 加载配置
- 验证必要的配置项
- 配置值验证

### 音频处理
- WAV 文件读取（支持 zj-1.wav）
- 音频分块逻辑
- 时长计算

### 识别结果处理
- 中间结果解析
- 最终结果解析（带时间戳）
- 静态方法测试
- 字符串表示测试

### Recognition 类
- 构造函数配置
- 消息构建逻辑
- 音频缓冲区操作
- 配置方法

### 时间轴计算
- 音频时长计算
- Chunk size 转换

### 错误处理
- 无效消息处理
- 时间戳提取
- 边界情况测试

## 测试数据

### property.json
包含 FunASR 服务器连接参数：
```json
{
  "params": {
    "funasr_host": "192.168.8.233",
    "funasr_port": "10095",
    "sample_rate": 16000,
    "language_hints": ["zh"],
    "funasr_mode": "2pass"
  }
}
```

### zj-1.wav
测试音频文件：
- 格式：16-bit mono PCM
- 采样率：16 kHz
- 时长：约 4.2 秒
- 大小：133,632 bytes

## 特点

1. **无外部依赖**：不需要 TEN Framework 运行时或真实的 FunASR 服务器
2. **纯功能测试**：只测试核心逻辑，不涉及网络通信
3. **完整覆盖**：测试所有主要功能和边界情况
4. **易于使用**：提供多种运行方式，支持单独测试

## 故障排除

### ImportError
如果遇到 `ModuleNotFoundError: No module named 'ten_runtime'` 错误：
- 这是正常的，因为测试直接运行在环境中
- 使用 `python test_adapter.py`直接运行
- 不要使用 `pytest` 命令运行，因为它会尝试导入模块

### 缺少测试数据
如果提示缺少 `zj-1.wav`：
- 测试会跳过相关测试并继续
- 可以从其他地方复制测试音频文件到当前目录

## 注意事项

1. 此测试套件专门用于 `funasr_adapter.py` 的单元测试
2. 不覆盖 TEN Framework 集成测试
3. 所有测试都是确定性的，结果每次都应该相同
4. 测试使用了来自 `property.json` 的实际配置值