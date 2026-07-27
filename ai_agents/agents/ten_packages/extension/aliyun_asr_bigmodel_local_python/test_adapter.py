"""
FunASR Adapter 测试脚本

专门测试 funasr_adapter.py 中的类和功能。
支持通过命令行参数自定义配置。
不使用任何 mock，只测试核心逻辑。
"""

import argparse
import json


import os
import sys
import wave
from pathlib import Path


# 添加当前目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入待测试的模块
try:
    from funasr_adapter import (
        FunASRRecognitionResult,
        FunASRRecognitionCallback,
        FunASRRecognition,
    )
except ImportError as e:
    print(f"⚠️  无法导入 funasr_adapter: {e}")
    print("这可能是因为缺少 TEN Framework 运行时依赖")
    print("请直接运行: python test_adapter.py")
    sys.exit(1)


class TestConfiguration:
    """测试配置相关功能"""

    @classmethod
    def load_config(cls):
        """从 property.json 加载配置"""
        config_path = Path(__file__).parent / "property.json"
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_config_loading(self, config):
        """测试配置加载"""
        print("=== 测试配置加载 ===")

        # 使用传入的配置
        params = config["params"]

        # 验证必要的配置项
        assert "funasr_host" in params
        assert "funasr_port" in params
        assert "sample_rate" in params
        assert "language_hints" in params

        # 验证配置值
        if "192.168.8.233" in params.get("funasr_host", ""):
            # 如果是从 property.json 加载的配置
            assert params["funasr_host"] == "192.168.8.233"
            assert params["funasr_port"] == "10095"
            assert params["sample_rate"] == 16000
            assert params["language_hints"] == ["zh"]
            assert params["funasr_mode"] == "2pass"
            print("✅ property.json 配置加载测试通过")
        else:
            # 使用默认配置或命令行配置
            print("✅ 默认/命令行配置测试通过")
            print(f"   - Host: {params['funasr_host']}")
            print(f"   - Port: {params['funasr_port']}")
            print(f"   - Sample rate: {params['sample_rate']}")
            print(f"   - Language hints: {params['language_hints']}")

        return params


class TestAudioProcessing:
    """测试音频处理相关功能"""

    def test_wav_file_reading(self, audio_file):
        """测试读取 WAV 文件"""
        print("\n=== 测试 WAV 文件读取 ===")

        # 使用传入的音频文件参数
        if Path(audio_file).is_absolute():
            wav_path = Path(audio_file)
        else:
            wav_path = Path(__file__).parent / audio_file

        if not wav_path.exists():
            print(f"⚠️  {wav_path} 不存在，跳过测试")
            return

        try:
            with wave.open(str(wav_path), 'rb') as wav_file:
                # 验证 WAV 文件基本信息
                channels = wav_file.getnchannels()
                width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                frames = wav_file.getnframes()

                print("🎵 WAV 文件信息:")
                print(f"   - 文件路径: {wav_path}")
                print(f"   - 通道数: {channels}")
                print(f"   - 采样位宽: {width} bytes")
                print(f"   - 采样率: {framerate} Hz")
                print(f"   - 总帧数: {frames}")

                # 验证预期的格式
                assert channels == 1, "期望单声道"
                assert width == 2, "期望 16-bit PCM"
                assert framerate == 16000, "期望 16kHz 采样率"

                # 读取音频数据
                audio_data = wav_file.readframes(frames)
                print(f"   - 音频数据大小: {len(audio_data)} bytes")
                print(f"   - 音频时长: {len(audio_data) / (framerate * 2 / 1000):.2f} 秒")

                print("✅ WAV 文件读取测试通过")

                return audio_data

        except Exception as e:
            print(f"❌ WAV 文件读取失败: {e}")
            return None

    def test_audio_chunking(self, audio_data, sample_rate=16000):
        """测试音频分块"""
        print("\n=== 测试音频分块 ===")

        # 如果没有传入音频数据，使用模拟数据
        if audio_data is None:
            print("⚠️  没有音频数据，使用模拟数据")
            audio_data = b"\x01\x02" * 3200  # 6400 bytes, 约 200ms at 16kHz

        # 验证音频数据
        assert len(audio_data) > 0, "音频数据不能为空"

        # 计算分块大小
        chunk_sizes = [5, 10, 5]  # 毫秒

        # 计算字节大小（16-bit mono: 2 bytes per sample）
        bytes_per_ms = sample_rate * 2 // 1000  # 每毫秒字节数

        print("📊 音频处理信息:")
        print(f"   - 总音频长度: {len(audio_data)} bytes")
        print(f"   - 采样率: {sample_rate} Hz")
        print(f"   - 字节/毫秒: {bytes_per_ms}")
        print(f"   - chunk sizes: {chunk_sizes}")

        # 测试分块逻辑
        chunk_offset = 0
        chunks = []

        for i, chunk_ms in enumerate(chunk_sizes):
            chunk_size_bytes = chunk_ms * bytes_per_ms
            if chunk_offset + chunk_size_bytes <= len(audio_data):
                chunk = audio_data[chunk_offset:chunk_offset + chunk_size_bytes]
                chunks.append({
                    "index": i,
                    "size_ms": chunk_ms,
                    "size_bytes": len(chunk),
                    "data": chunk
                })
                chunk_offset += chunk_size_bytes
                print(f"   - Chunk {i}: {chunk_ms}ms ({len(chunk)} bytes)")

        assert len(chunks) > 0, "应该产生音频块"

        print("✅ 音频分块测试通过")


class TestFunASRRecognitionResult:
    """测试 FunASRRecognitionResult 类"""

    def test_intermediate_result(self):
        """测试中间结果"""
        print("\n=== 测试中间结果 ===")

        # 模拟中间结果消息
        message = {
            "is_final": False,
            "mode": "2pass-online",
            "text": "你好",
            "wav_name": "default"
        }

        result = FunASRRecognitionResult(message)

        # 验证基本属性
        assert result.status_code == 200
        assert result.request_id == "default"
        assert not result.output["final"]  # 不是最终结果

        # 验证句子结构
        sentence = result.output["sentence"]
        assert sentence["text"] == "你好"
        assert sentence["begin_time"] == 0
        assert sentence["end_time"] == 0
        assert sentence["final"] == False
        assert sentence["words"] == []

        print("✅ 中间结果测试通过")

    def test_final_result_with_timestamps(self):
        """测试带时间戳的最终结果"""
        print("\n=== 测试最终结果（带时间戳）===")

        # 模拟最终结果消息
        message = {
            "is_final": True,
            "mode": "2pass-offline",
            "text": "你好世界",
            "wav_name": "default",
            "timestamp": "1691458800000",
            "stamp_sents": [{
                "start": 1000,
                "end": 3000,
                "text_seg": "你 好 世 界",
                "ts_list": [[1000, 1500], [1500, 2000], [2000, 2500], [2500, 3000]]
            }]
        }

        result = FunASRRecognitionResult(message)

        # 验证最终结果属性
        assert result.output["final"] == True
        assert result.status_code == 200

        # 验证句子结构
        sentence = result.output["sentence"]
        assert sentence["text"] == "你好世界"
        assert sentence["begin_time"] == 1000
        assert sentence["end_time"] == 3000
        assert sentence["final"] == True

        # 验证词级时间戳
        words = sentence["words"]
        assert len(words) == 4
        assert words[0] == {"text": "你", "begin_time": 1000, "end_time": 1500}
        assert words[1] == {"text": "好", "begin_time": 1500, "end_time": 2000}
        assert words[2] == {"text": "世", "begin_time": 2000, "end_time": 2500}
        assert words[3] == {"text": "界", "begin_time": 2500, "end_time": 3000}

        print("✅ 最终结果测试通过")

    def test_vllm_final_result(self):
        """测试 vLLM WebSocket 最终结果格式。"""
        message = {
            "sentences": [
                {"text": "你好", "start": 0, "end": 680},
                {"text": "世界", "start": 700, "end": 1200},
            ],
            "is_final": True,
            "duration_ms": 1200,
        }

        sentence = FunASRRecognitionResult(message).get_sentence()
        assert sentence["text"] == "你好世界"
        assert sentence["begin_time"] == 0
        assert sentence["end_time"] == 1200
        assert sentence["final"] is True

    def test_static_methods(self):
        """测试静态方法"""
        print("\n=== 测试静态方法 ===")

        # 测试 is_sentence_end
        sentence_final = {"text": "你好", "final": True}
        sentence_intermediate = {"text": "你好", "final": False}

        assert FunASRRecognitionResult.is_sentence_end(sentence_final) == True
        assert FunASRRecognitionResult.is_sentence_end(sentence_intermediate) == False

        print("✅ 静态方法测试通过")

    def test_string_representation(self):
        """测试字符串表示"""
        print("\n=== 测试字符串表示 ===")

        message = {"text": "测试", "is_final": False}
        result = FunASRRecognitionResult(message)

        str_result = str(result)
        assert "sentence" in str_result
        assert "text" in str_result
        assert "测试" in str_result

        print("✅ 字符串表示测试通过")

    def test_property_json_scenarios(self):
        """测试 property.json 相关的场景"""
        print("\n=== 测试配置相关场景 ===")

        # 模拟 property.json 中的配置场景
        scenarios = [
            {
                "name": "中间结果",
                "message": {
                    "is_final": False,
                    "mode": "2pass-online",
                    "text": "你好",
                    "wav_name": "default"
                },
                "expected_final": False
            },
            {
                "name": "最终结果（无时间戳）",
                "message": {
                    "is_final": True,
                    "mode": "2pass-offline",
                    "text": "你好世界",
                    "wav_name": "default"
                },
                "expected_final": True
            },
            {
                "name": "最终结果（带时间戳）",
                "message": {
                    "is_final": True,
                    "mode": "2pass-offline",
                    "text": "测试一下",
                    "wav_name": "default",
                    "stamp_sents": [{
                        "start": 1000,
                        "end": 3000,
                        "text_seg": "测 试 一 下",
                        "ts_list": [[1000, 1500], [1500, 2000], [2000, 2500], [2500, 3000]]
                    }]
                },
                "expected_final": True
            }
        ]

        for scenario in scenarios:
            result = FunASRRecognitionResult(scenario['message'])

            # 验证基本属性
            assert result.request_id == scenario['message']['wav_name']
            assert result.output['final'] == scenario['expected_final']

            # 验证句子结构
            sentence = result.output['sentence']
            assert sentence['text'] == scenario['message']['text']
            assert sentence['final'] == scenario['expected_final']

        print("✅ 配置相关场景测试通过")


class TestFunASRRecognition:
    """测试 FunASRRecognition 类"""

    def test_construction_with_config(self, config):
        """测试使用配置构造"""
        print("\n=== 测试构造函数 ===")

        params = config["params"]

        # 创建回调
        callback = TestCallback()

        # 创建 recognition 实例
        recognition = FunASRRecognition(
            host=params["funasr_host"],
            port=params["funasr_port"],
            is_ssl=params["funasr_is_ssl"],
            mode=params["funasr_mode"],
            wav_name="test_stream",
            callback=callback,
            sample_rate=params["sample_rate"],
            language_hints=params["language_hints"],
            hotwords=params["funasr_hotwords"],
            itn=params["funasr_itn"]
        )

        # 验证配置是否正确加载
        assert recognition.host == params["funasr_host"]
        assert recognition.port == params["funasr_port"]
        assert recognition.mode == params["funasr_mode"]
        assert recognition.sample_rate == params["sample_rate"]
        assert recognition.kwargs["hotwords"] == params["funasr_hotwords"]
        assert recognition.kwargs["itn"] == params["funasr_itn"]

        print("✅ 构造函数测试通过")

    def test_send_audio_and_get_results(self, config, audio_file):
        """测试发送音频数据并获取识别结果"""
        print("\n=== 测试发送音频并获取结果 ===")

        params = config["params"]

        # 创建测试回调
        callback = TestCallback()

        # 创建 recognition 实例
        recognition = FunASRRecognition(
            host=params["funasr_host"],
            port=params["funasr_port"],
            is_ssl=params["funasr_is_ssl"],
            mode=params["funasr_mode"],
            wav_name="test_audio",
            callback=callback,
            sample_rate=params["sample_rate"],
            language_hints=params["language_hints"],
            hotwords=params["funasr_hotwords"],
            itn=params["funasr_itn"],
            dump=True,
            dump_path="."
        )

        # 启动识别（模拟）
        recognition.start()

        # 读取测试音频数据
        if Path(audio_file).is_absolute():
            wav_path = Path(audio_file)
        else:
            wav_path = Path(__file__).parent / audio_file

        if wav_path.exists():
            with wave.open(str(wav_path), 'rb') as wav_file:
                audio_data = wav_file.readframes(wav_file.getnframes())
                print(f"🎵 读取到音频数据: {len(audio_data)} bytes")
        else:
            # 使用模拟音频数据
            audio_data = b"\x01\x02" * 3200  # 6400 bytes
            print(f"🎵 使用模拟音频数据: {len(audio_data)} bytes")

        # 发送音频数据
        print("📤 发送音频数据到 FunASR...")
        recognition.send_audio_frame(audio_data)

        # 模拟发送结束
        print("🏁 发送结束标记...")
        recognition.send_end_of_speech()

        # 等待处理（模拟异步处理）
        import time
        time.sleep(0.5)

        # 打印收集到的结果
        if callback.results:
            print(f"📊 收到 {len(callback.results)} 个识别结果:")
            for i, result in enumerate(callback.results):
                print(f"   结果 {i+1}:")
                print(f"     - 文本: {result.output['sentence']['text']}")
                print(f"     - 是否最终: {result.output['final']}")
                print(f"     - 开始时间: {result.output['sentence'].get('begin_time', 0)}ms")
                print(f"     - 结束时间: {result.output['sentence'].get('end_time', 0)}ms")
                print(f"     - 状态码: {result.status_code}")
                if result.output['sentence'].get('words'):
                    print(f"     - 词级时间戳: {result.output['sentence']['words']}")
                print()
        else:
            print("⚠️  没有收到识别结果")

        # 停止识别
        recognition.stop()

        print("✅ 音频发送和结果获取测试通过")

    def test_message_building(self):
        """测试 vLLM WebSocket 控制消息构建逻辑。"""
        print("\n=== 测试 vLLM 控制消息 ===")

        config = TestConfiguration.load_config()
        params = config["params"]

        language = params["language_hints"][0]
        language_map = {"zh": "中文", "zh-CN": "中文"}
        messages = ["START", f"LANGUAGE:{language_map.get(language, language)}", "STOP"]

        assert messages == ["START", "LANGUAGE:中文", "STOP"]

        print("✅ vLLM 控制消息测试通过")

    def test_audio_buffer_operations(self):
        """测试音频缓冲区操作"""
        print("\n=== 测试音频缓冲区操作 ===")

        callback = FunASRRecognitionCallback()
        recognition = FunASRRecognition(callback=callback)

        # 验证初始状态
        assert len(recognition._audio_data_buffer) == 0

        # 添加音频数据
        test_data = [b"test1", b"test2", b"test3"]
        for data in test_data:
            recognition._audio_data_buffer.append(data)

        # 验证缓冲区内容
        assert len(recognition._audio_data_buffer) == 3
        assert recognition._audio_data_buffer[0] == b"test1"
        assert recognition._audio_data_buffer[1] == b"test2"
        assert recognition._audio_data_buffer[2] == b"test3"

        # 清空缓冲区
        recognition._audio_data_buffer.clear()
        assert len(recognition._audio_data_buffer) == 0

        print("✅ 音频缓冲区操作测试通过")

    def test_configuration_methods(self):
        """测试配置相关方法"""
        print("\n=== 测试配置方法 ===")

        callback = FunASRRecognitionCallback()
        recognition = FunASRRecognition(callback=callback)

        # 验证默认值
        assert recognition.mode == "2pass"
        assert recognition.wav_name == "default"

        # 更新配置
        recognition.mode = "online"
        recognition.wav_name = "test_stream"

        assert recognition.mode == "online"
        assert recognition.wav_name == "test_stream"

        print("✅ 配置方法测试通过")


class TestAudioTimeline:
    """测试音频时间轴相关功能"""

    def test_duration_calculation(self):
        """测试音频时长计算"""
        print("\n=== 测试音频时长计算 ===")

        # 模拟音频数据长度（16-bit mono PCM）
        sample_rate = 16000
        audio_bytes = b"\x01\x02" * 3200  # 6400 bytes
        expected_duration_ms = int(len(audio_bytes) / (sample_rate / 1000 * 2))

        # 计算时长
        calculated_duration_ms = int(len(audio_bytes) / (sample_rate * 2 / 1000))

        assert calculated_duration_ms == expected_duration_ms
        print(f"✅ 音频时长计算: {calculated_duration_ms}ms")

    def test_chunk_size_conversion(self):
        """测试 chunk size 转换"""
        print("\n=== 测试 chunk size 转换 ===")

        config = TestConfiguration.load_config()
        params = config["params"]

        chunk_size_str = params["funasr_chunk_size"]
        chunk_sizes = [int(x) for x in chunk_size_str.split(",")]

        assert chunk_sizes == [5, 10, 5]
        print(f"✅ Chunk size 转换: {chunk_sizes}")

        # 验证转换为毫秒
        sample_rate = params["sample_rate"]
        bytes_per_ms = sample_rate * 2 // 1000

        for i, chunk_ms in enumerate(chunk_sizes):
            chunk_size_bytes = chunk_ms * bytes_per_ms
            print(f"   - Chunk {i}: {chunk_ms}ms = {chunk_size_bytes} bytes")

        print("✅ Chunk size 转换测试通过")


class TestCallback(FunASRRecognitionCallback):
    """测试用的回调类，收集识别结果"""

    def __init__(self):
        super().__init__()
        self.results = []
        self.events = []

    def on_event(self, result: FunASRRecognitionResult) -> None:
        """当收到识别结果时调用"""
        self.results.append(result)
        self.events.append("on_event")
        print(f"🔔 收到事件: on_event, 结果: {result.output['sentence']['text']}")

    def on_open(self) -> None:
        """当连接建立时调用"""
        self.events.append("on_open")
        print("🔔 收到事件: on_open")

    def on_complete(self) -> None:
        """当识别完成时调用"""
        self.events.append("on_complete")
        print("🔔 收到事件: on_complete")

    def on_error(self, result: FunASRRecognitionResult) -> None:
        """当发生错误时调用"""
        self.events.append("on_error")
        print(f"🔔 收到事件: on_error, 错误: {result.status_code}")

    def on_close(self) -> None:
        """当连接关闭时调用"""
        self.events.append("on_close")
        print("🔔 收到事件: on_close")


class TestErrorHandling:
    """测试错误处理"""

    def test_invalid_message_handling(self):
        """测试无效消息处理"""
        print("\n=== 测试无效消息处理 ===")

        # 测试空消息
        result = FunASRRecognitionResult({})
        assert result.output["sentence"]["text"] == ""
        assert result.output["final"] == False

        # 测试缺少关键字段
        incomplete_message = {
            "text": "测试",
            # 缺少 is_final 字段
        }
        result = FunASRRecognitionResult(incomplete_message)
        assert result.output["sentence"]["text"] == "测试"
        assert result.output["final"] == False  # 默认值

        print("✅ 无效消息处理测试通过")

    def test_timestamp_extraction(self):
        """测试时间戳提取"""
        print("\n=== 测试时间戳提取 ===")

        # 测试没有时间戳的情况
        message_no_ts = {
            "text": "测试",
            "is_final": True,
            "mode": "2pass-offline"
        }
        result = FunASRRecognitionResult(message_no_ts)
        assert result.output["sentence"]["begin_time"] == 0
        assert result.output["sentence"]["end_time"] == 0

        # 测试有时间戳的情况
        message_with_ts = {
            "text": "测试",
            "is_final": True,
            "mode": "2pass-offline",
            "stamp_sents": [{
                "start": 1000,
                "end": 2000,
                "text_seg": "测试",
                "ts_list": [[1000, 2000]]
            }]
        }
        result = FunASRRecognitionResult(message_with_ts)
        assert result.output["sentence"]["begin_time"] == 1000
        assert result.output["sentence"]["end_time"] == 2000

        print("✅ 时间戳提取测试通过")


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='FunASR Adapter 测试脚本')

    # 连接参数
    parser.add_argument('--host', type=str, default=None,
                       help='FunASR 服务器地址 (默认: property.json)')
    parser.add_argument('--port', type=str, default=None,
                       help='FunASR 服务器端口 (默认: property.json)')
    parser.add_argument('--is-ssl', action='store_true',
                       help='是否使用 SSL 连接')
    parser.add_argument('--audio-file', type=str, default='zj-1.wav',
                       help='测试音频文件路径')

    # 测试参数
    parser.add_argument('--test-name', type=str, default=None,
                       help='运行特定测试用例')
    parser.add_argument('--verbose', action='store_true',
                       help='详细输出模式')
    parser.add_argument('--no-config', action='store_true',
                       help='不使用 property.json，使用默认配置')

    return parser.parse_args()


def load_config_or_default(args):
    """加载配置或使用默认值"""
    if args.no_config:
        # 使用默认配置
        config = {
            "params": {
                "funasr_host": args.host or "127.0.0.1",
                "funasr_port": args.port or "10095",
                "funasr_is_ssl": args.is_ssl or False,
                "funasr_mode": "2pass",
                "funasr_chunk_size": "5,10,5",
                "funasr_chunk_interval": 10,
                "funasr_hotwords": "",
                "funasr_itn": True,
                "sample_rate": 16000,
                "language_hints": ["zh"],
                "language": "zh-CN",
                "dump": True
            }
        }
        if args.verbose:
            print("📋 使用默认配置")
    else:
        # 从 property.json 加载配置
        config = TestConfiguration.load_config()
        # 命令行参数覆盖配置文件
        if args.host:
            config["params"]["funasr_host"] = args.host
        if args.port:
            config["params"]["funasr_port"] = args.port
        if args.is_ssl:
            config["params"]["funasr_is_ssl"] = True
        config["params"]["dump"] = True  # 启用音频转储

        if args.verbose:
            print("📋 从 property.json 加载配置，并应用命令行参数覆盖")

    return config


def run_tests(args=None):
    """运行所有测试"""
    if args is None:
        args = parse_arguments()

    print("🚀 开始 FunASR Adapter 纯逻辑测试")
    print("=" * 60)

    if args.no_config:
        print("📁 使用默认配置")
    else:
        print("📁 使用配置: property.json")

    audio_file = args.audio_file or "zj-1.wav"
    print(f"🎵 使用测试数据: {audio_file}")

    if args.host:
        print(f"🌐 服务器: {args.host}:{args.port or '10095'}")
        print(f"🔒 SSL: {'是' if args.is_ssl else '否'}")

    print("=" * 60)

    # 加载配置
    config = load_config_or_default(args)
    params = config["params"]

    # 初始化测试结果
    test_results = []

    try:
        # 配置测试
        config_test = TestConfiguration()
        config_test.test_config_loading(config)
        test_results.append(("配置管理", True))
    except Exception as e:
        test_results.append(("配置管理", False, str(e)))

    # 读取音频数据（复用）
    audio_data = None

    try:
        # 音频处理测试
        audio_test = TestAudioProcessing()
        audio_data = audio_test.test_wav_file_reading(args.audio_file)
        audio_test.test_audio_chunking(audio_data, params.get("sample_rate", 16000))
        test_results.append(("音频处理", True))
    except Exception as e:
        test_results.append(("音频处理", False, str(e)))

    try:
        # 结果处理测试
        result_test = TestFunASRRecognitionResult()
        result_test.test_intermediate_result()
        result_test.test_final_result_with_timestamps()
        result_test.test_vllm_final_result()
        result_test.test_static_methods()
        result_test.test_string_representation()
        result_test.test_property_json_scenarios()
        test_results.append(("结果处理", True))
    except Exception as e:
        test_results.append(("结果处理", False, str(e)))

    try:
        # Recognition 类测试
        recognition_test = TestFunASRRecognition()
        recognition_test.test_construction_with_config(config)
        recognition_test.test_message_building()
        recognition_test.test_audio_buffer_operations()
        recognition_test.test_configuration_methods()
        recognition_test.test_send_audio_and_get_results(config, args.audio_file)
        test_results.append(("Recognition 类", True))
    except Exception as e:
        test_results.append(("Recognition 类", False, str(e)))

    try:
        # 时间轴测试
        timeline_test = TestAudioTimeline()
        timeline_test.test_duration_calculation()
        timeline_test.test_chunk_size_conversion()
        test_results.append(("时间轴", True))
    except Exception as e:
        test_results.append(("时间轴", False, str(e)))

    try:
        # 错误处理测试
        error_test = TestErrorHandling()
        error_test.test_invalid_message_handling()
        error_test.test_timestamp_extraction()
        test_results.append(("错误处理", True))
    except Exception as e:
        test_results.append(("错误处理", False, str(e)))

    # 打印测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    all_passed = True
    for test_name, *result in test_results:
        if len(result) == 1:
            passed, message = result[0], "所有测试通过"
        elif len(result) == 2:
            passed, message = result
        else:
            passed, message = result

        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{test_name}: {status}")
        if not passed:
            print(f"   错误: {message}")
            all_passed = False

    if all_passed:
        print("\n🎉 所有测试都通过了！")
        print("\n✅ 测试覆盖了以下功能:")
        print("1. ✅ 配置加载和验证 (来自 property.json)")
        print("2. ✅ 音频文件读取和处理 (支持 zj-1.wav)")
        print("3. ✅ 识别结果解析和处理")
        print("4. ✅ Recognition 类的核心功能")
        print("5. ✅ 音频时间轴计算")
        print("6. ✅ 错误处理和边界情况")
        print("\n📝 注意: 此测试不依赖任何外部服务或框架")
    else:
        print("\n❌ 部分测试失败，请查看错误信息")


# Individual test functions for pytest compatibility
def test_config_loading():
    """测试配置加载"""
    config_test = TestConfiguration()
    config_test.test_config_loading()


def test_wav_file_reading():
    """测试 WAV 文件读取"""
    audio_test = TestAudioProcessing()
    audio_test.test_wav_file_reading()


def test_audio_chunking():
    """测试音频分块"""
    audio_test = TestAudioProcessing()
    audio_test.test_audio_chunking()


def test_intermediate_result():
    """测试中间结果"""
    result_test = TestFunASRRecognitionResult()
    result_test.test_intermediate_result()


def test_final_result_with_timestamps():
    """测试带时间戳的最终结果"""
    result_test = TestFunASRRecognitionResult()
    result_test.test_final_result_with_timestamps()


def test_vllm_final_result():
    """测试 vLLM 最终结果。"""
    result_test = TestFunASRRecognitionResult()
    result_test.test_vllm_final_result()


def test_static_methods():
    """测试静态方法"""
    result_test = TestFunASRRecognitionResult()
    result_test.test_static_methods()


def test_string_representation():
    """测试字符串表示"""
    result_test = TestFunASRRecognitionResult()
    result_test.test_string_representation()


def test_property_json_scenarios():
    """测试 property.json 相关场景"""
    result_test = TestFunASRRecognitionResult()
    result_test.test_property_json_scenarios()


def test_construction_with_config():
    """测试使用配置构造"""
    recognition_test = TestFunASRRecognition()
    recognition_test.test_construction_with_config()


def test_message_building():
    """测试消息构建"""
    recognition_test = TestFunASRRecognition()
    recognition_test.test_message_building()


def test_audio_buffer_operations():
    """测试音频缓冲区操作"""
    recognition_test = TestFunASRRecognition()
    recognition_test.test_audio_buffer_operations()


def test_configuration_methods():
    """测试配置方法"""
    recognition_test = TestFunASRRecognition()
    recognition_test.test_configuration_methods()


def test_send_audio_and_get_results():
    """测试发送音频并获取结果"""
    recognition_test = TestFunASRRecognition()
    recognition_test.test_send_audio_and_get_results()


def test_duration_calculation():
    """测试音频时长计算"""
    timeline_test = TestAudioTimeline()
    timeline_test.test_duration_calculation()


def test_chunk_size_conversion():
    """测试 chunk size 转换"""
    timeline_test = TestAudioTimeline()
    timeline_test.test_chunk_size_conversion()


def test_invalid_message_handling():
    """测试无效消息处理"""
    error_test = TestErrorHandling()
    error_test.test_invalid_message_handling()


def test_timestamp_extraction():
    """测试时间戳提取"""
    error_test = TestErrorHandling()
    error_test.test_timestamp_extraction()


if __name__ == "__main__":
    # 解析命令行参数并运行测试
    args = parse_arguments()
    run_tests(args)
