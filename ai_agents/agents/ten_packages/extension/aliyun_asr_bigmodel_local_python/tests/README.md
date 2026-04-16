# FunASR ASR 扩展测试说明

## 测试命令

### 快速测试（推荐）

```bash
cd /home/zj/ten-framework/ai_agents/agents/ten_packages/extension/aliyun_asr_bigmodel_local_python

# 运行所有测试
export PYTHONPATH=.ten/app:.ten/app/ten_packages/system/ten_runtime_python/lib:.ten/app/ten_packages/system/ten_runtime_python/interface:.ten/app/ten_packages/system/ten_ai_base/interface:$PYTHONPATH
pytest -s tests/ -p no:asyncio
```

### 使用 ten 环境 Python 3.10

```bash
export PYTHONPATH=.ten/app:.ten/app/ten_packages/system/ten_runtime_python/lib:.ten/app/ten_packages/system/ten_runtime_python/interface:.ten/app/ten_packages/system/ten_ai_base/interface:$PYTHONPATH
/home/zj/miniconda3/envs/ten/bin/python -m pytest -s tests/ -p no:asyncio
```

### 单独运行 ASR 识别测试

```bash
# 需要 FunASR 服务器 (192.168.8.233:10095) 运行
pytest -s tests/test_asr_result.py -p no:asyncio
```

## 测试说明

### test_asr_result.py
- **功能**: 测试完整的语音识别流程
- **依赖**: FunASR 服务器 (192.168.8.233:10095) 必须运行
- **音频文件**: 使用 `zj-1.wav` (扩展根目录)
- **输出**: 识别结果会打印到控制台

**示例输出**:
```
========== ASR Result ==========
Text: 现在测试一下没有加入任何白噪声
Final: True
Start: 880 ms
Duration: 4315 ms
Language: zh-CN
================================
```

### test_invalid_params.py
- **功能**: 测试无效参数处理
- **依赖**: 无外部服务依赖
- **状态**: 总是运行

## 期望结果

### FunASR 服务器运行时

```
========================= test session starts =========================
collected 2 items

tests/test_asr_result.py .     # 通过（显示识别结果）
tests/test_invalid_params.py .  # 通过

========================= 2 passed in 0.12s =========================
```

### FunASR 服务器未运行时

```
tests/test_asr_result.py FAILED  # 连接失败
tests/test_invalid_params.py .    # 通过
```

## 前置要求

1. **FunASR 服务器** 必须在 `192.168.8.233:10095` 运行
2. **Python 3.10** (推荐) 或 Python 3.13
3. 依赖已安装: `tman install --standalone`

## 注意事项

1. `-p no:asyncio`: 必须添加此参数以避免 pytest-asyncio 兼容性问题
2. 如果测试超时，检查 FunASR 服务器是否运行
3. 识别结果会实时打印到控制台
