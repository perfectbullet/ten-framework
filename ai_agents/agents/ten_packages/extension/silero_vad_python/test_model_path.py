#!/usr/bin/env python3
"""
测试脚本：验证 funasr_model.py 的模型路径配置
"""
import os
import sys

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from funasr_model import FunASRWrapper, get_asr_wrapper, DEFAULT_MODEL_DIR

def test_default_path():
    """测试默认路径是否正确"""
    print("=" * 60)
    print("测试 1: 验证默认模型路径")
    print("=" * 60)

    print(f"默认模型目录: {DEFAULT_MODEL_DIR}")
    print(f"目录是否存在: {os.path.exists(DEFAULT_MODEL_DIR)}")

    if os.path.exists(DEFAULT_MODEL_DIR):
        print("✅ 默认路径正确")
    else:
        print("❌ 默认路径错误")
        return False

    # 检查必要文件
    required_files = ['config.yaml', 'tokens.json', 'model_quant.onnx']
    print("\n检查模型文件:")
    for file in required_files:
        file_path = os.path.join(DEFAULT_MODEL_DIR, file)
        exists = os.path.exists(file_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {file}")

    return True


def test_wrapper_initialization():
    """测试 FunASRWrapper 初始化"""
    print("\n" + "=" * 60)
    print("测试 2: 验证 FunASRWrapper 初始化")
    print("=" * 60)

    try:
        # 测试使用默认路径
        print("初始化 FunASRWrapper (使用默认路径)...")
        wrapper = FunASRWrapper()

        print(f"模型目录: {wrapper.model_dir}")
        print(f"使用量化: {wrapper.quantize}")
        print(f"批处理大小: {wrapper.batch_size}")
        print("✅ 初始化成功")
        return True

    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return False


def test_model_loading():
    """测试模型加载"""
    print("\n" + "=" * 60)
    print("测试 3: 加载 FunASR 模型")
    print("=" * 60)

    try:
        print("加载模型...")
        wrapper = FunASRWrapper()
        load_time = wrapper.load()

        print(f"模型加载时间: {load_time:.2f}秒")
        print(f"模型已加载: {wrapper.model is not None}")
        print("✅ 模型加载成功")
        return True

    except FileNotFoundError as e:
        print(f"❌ 模型目录未找到: {e}")
        return False
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return False


def test_singleton_pattern():
    """测试单例模式"""
    print("\n" + "=" * 60)
    print("测试 4: 验证单例模式")
    print("=" * 60)

    try:
        print("第一次调用 get_asr_wrapper()...")
        wrapper1 = get_asr_wrapper()
        print(f"Wrapper 1 ID: {id(wrapper1)}")

        print("第二次调用 get_asr_wrapper()...")
        wrapper2 = get_asr_wrapper()
        print(f"Wrapper 2 ID: {id(wrapper2)}")

        if wrapper1 is wrapper2:
            print("✅ 单例模式正常工作")
            return True
        else:
            print("❌ 单例模式异常")
            return False

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def test_custom_path():
    """测试自定义路径"""
    print("\n" + "=" * 60)
    print("测试 5: 验证自定义路径")
    print("=" * 60)

    try:
        # 测试显式传入相对路径
        custom_path = "speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx"
        print(f"使用自定义相对路径: {custom_path}")

        wrapper = FunASRWrapper(model_dir=custom_path)
        print(f"解析后的绝对路径: {wrapper.model_dir}")

        # 验证路径是否正确
        expected_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            custom_path
        )

        if wrapper.model_dir == expected_path:
            print("✅ 自定义路径解析正确")
        else:
            print(f"❌ 路径不匹配")
            print(f"  期望: {expected_path}")
            print(f"  实际: {wrapper.model_dir}")
            return False

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("FunASR 模型路径测试")
    print("=" * 60)

    tests = [
        test_default_path,
        test_wrapper_initialization,
        test_model_loading,
        test_singleton_pattern,
        test_custom_path,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            results.append(False)

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"通过: {passed}/{total}")

    if passed == total:
        print("✅ 所有测试通过")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
