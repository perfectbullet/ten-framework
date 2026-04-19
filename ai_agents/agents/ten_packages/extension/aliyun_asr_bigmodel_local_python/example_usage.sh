#!/bin/bash
# FunASR Adapter 测试脚本使用示例

echo "FunASR Adapter 测试脚本使用示例"
echo "================================="

# 示例1: 使用 property.json 配置（默认）
echo -e "\n1️⃣ 使用默认配置（property.json）:"
echo "python test_adapter.py"
python test_adapter.py > /dev/null 2>&1 && echo "✅ 运行成功" || echo "❌ 运行失败"

# 示例2: 使用自定义配置
echo -e "\n2️⃣ 使用自定义配置:"
echo "python test_adapter.py --host 127.0.0.1 --port 10095 --audio-file zj-1.wav --verbose"
python test_adapter.py --host 127.0.0.1 --port 10095 --audio-file zj-1.wav --verbose > /dev/null 2>&1 && echo "✅ 运行成功" || echo "❌ 运行失败"

# 示例3: 使用默认配置（不依赖 property.json）
echo -e "\n3️⃣ 使用默认配置（不依赖 property.json）:"
echo "python test_adapter.py --no-config --host 127.0.0.1 --port 10095"
python test_adapter.py --no-config --host 127.0.0.1 --port 10095 > /dev/null 2>&1 && echo "✅ 运行成功" || echo "❌ 运行失败"

# 示例4: 使用 SSL 连接
echo -e "\n4️⃣ 使用 SSL 连接:"
echo "python test_adapter.py --host 127.0.0.1 --port 10095 --is-ssl"
python test_adapter.py --host 127.0.0.1 --port 10095 --is-ssl > /dev/null 2>&1 && echo "✅ 运行成功" || echo "❌ 运行失败"

# 示例5: 使用不同的音频文件
echo -e "\n5️⃣ 使用不同的音频文件:"
echo "python test_adapter.py --audio-file my_audio.wav"
python test_adapter.py --audio-file zj-1.wav > /dev/null 2>&1 && echo "✅ 运行成功" || echo "❌ 运行失败"

# 示例6: 查看帮助
echo -e "\n6️⃣ 查看帮助:"
echo "python test_adapter.py --help"
python test_adapter.py --help | head -10

echo -e "\n🎉 所有示例展示完毕！"