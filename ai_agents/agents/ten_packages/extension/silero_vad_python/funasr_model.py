#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""
FunASR ASR Model Wrapper for Speech Interruption Detection.
Provides speech-to-text recognition with timing logs.
"""
import io
import time
import json
import os
from typing import List, Dict, Any, Optional
import numpy as np

# 模型导入（延迟导入，按需加载）
PARAFORMER_MODEL = None
TARGET_SAMPLE_RATE = 16000

# 获取脚本所在目录
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认模型目录：脚本同级目录下的 speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx
DEFAULT_MODEL_DIR = os.path.join(_SCRIPT_DIR, "speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx")


class FunASRWrapper:
    """FunASR Paraformer model wrapper for speech recognition."""

    def __init__(self, model_dir: str = None,
                 quantize: bool = True,
                 batch_size: int = 1):
        """
        Initialize FunASR model.

        Args:
            model_dir: FunASR model directory path (default: script_dir/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx)
            quantize: Whether to use quantized model
            batch_size: Batch size for inference
        """
        # 如果未指定模型目录，使用默认路径（脚本同级目录）
        if model_dir is None:
            model_dir = DEFAULT_MODEL_DIR
        # 如果是相对路径，转换为基于脚本目录的绝对路径
        elif not os.path.isabs(model_dir):
            model_dir = os.path.join(_SCRIPT_DIR, model_dir)

        self.model_dir = model_dir
        self.quantize = quantize
        self.batch_size = batch_size
        self.model = None
        self._load_time = 0.0

    def load(self) -> float:
        """
        Load FunASR model.

        Returns:
            float: Model loading time in seconds
        """
        global PARAFORMER_MODEL

        start_time = time.time()

        # 验证模型目录是否存在
        if not os.path.exists(self.model_dir):
            raise FileNotFoundError(
                f"FunASR model directory not found: {self.model_dir}\n"
                f"Please ensure the model directory exists in the same location as this script."
            )

        # 验证模型目录是否包含必要的文件
        required_files = ['config.yaml', 'tokens.json']
        missing_files = [f for f in required_files
                        if not os.path.exists(os.path.join(self.model_dir, f))]
        if missing_files:
            print(f"[FunASR] Warning: Missing expected files in model directory: {missing_files}")

        try:
            from funasr_onnx import Paraformer
        except ImportError:
            raise ImportError(
                "funasr-onnx is not installed. "
                "Install with: pip install funasr-onnx"
            )

        if PARAFORMER_MODEL is None:
            PARAFORMER_MODEL = Paraformer(
                self.model_dir,
                batch_size=self.batch_size,
                quantize=self.quantize
            )

        self.model = PARAFORMER_MODEL
        self._load_time = time.time() - start_time

        return self._load_time

    def _load_bytes_to_numpy(self, audio_bytes: bytes, target_sr: int = TARGET_SAMPLE_RATE):
        """
        将音频字节数据转换为 numpy 数组，自动重采样到目标采样率。

        Args:
            audio_bytes: 音频字节数据（支持 WAV, MP3 等多种格式）
            target_sr: 目标采样率，默认 16000Hz

        Returns:
            numpy.ndarray: 重采样后的音频数据（float32，归一化到 [-1, 1]）
        """
        import librosa

        try:
            # 使用 BytesIO 将 bytes 转换为文件类对象
            audio_buffer = io.BytesIO(audio_bytes)

            # 使用 librosa 加载音频，自动重采样到目标采样率
            waveform, sr = librosa.load(audio_buffer, sr=target_sr)

            return waveform

        except Exception as e:
            raise ValueError(f"Failed to load audio data: {e}")

    def recognize(self, audio_input: Any, sample_rate: int = TARGET_SAMPLE_RATE) -> List[Dict[str, Any]]:
        """
        Recognize speech from audio input.

        Args:
            audio_input: Audio data (bytes, numpy array, or file path)
            sample_rate: Sample rate for numpy array input

        Returns:
            List of recognition results, each containing:
                - preds: Recognized text (with spaces between characters)
                - timestamp: List of [start_ms, end_ms] for each word/character
                - raw_tokens: List of original tokens
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        start_time = time.time()
        audio_size = 0

        # 处理不同类型的输入
        if isinstance(audio_input, str):
            # 文件路径
            audio_array = self._load_bytes_to_numpy_from_file(audio_input)
            audio_size = len(audio_array)
        elif isinstance(audio_input, bytes):
            # PCM 字节数据 - 需要转换为 WAV 格式或直接处理
            audio_array = self._convert_pcm_to_numpy(audio_input, sample_rate)
            audio_size = len(audio_input)
        elif hasattr(audio_input, '__array__'):
            # numpy array
            audio_array = audio_input
            audio_size = audio_array.nbytes
        else:
            raise ValueError(f"Unsupported audio input type: {type(audio_input)}")

        # 调用模型进行识别
        inference_start = time.time()
        result = self.model(audio_array)
        inference_time = time.time() - inference_start

        total_time = time.time() - start_time

        # 记录详细日志
        self._log_recognition_result(result, audio_size, total_time, inference_time)

        return result

    def _convert_pcm_to_numpy(self, pcm_bytes: bytes, sample_rate: int):
        """
        将 PCM16 字节数据直接转换为 numpy 数组（快速路径，无需 librosa）。

        Args:
            pcm_bytes: PCM16 格式的字节数据
            sample_rate: 采样率

        Returns:
            numpy.ndarray: 音频数据（float32，归一化到 [-1, 1]）
        """


        # 如果采样率已经是目标采样率，直接转换
        if sample_rate == TARGET_SAMPLE_RATE:
            audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
            return audio_int16.astype(np.float32) / 32768.0
        else:
            # 需要重采样，使用 librosa
            return self._load_bytes_to_numpy(pcm_bytes, TARGET_SAMPLE_RATE)

    def _load_bytes_to_numpy_from_file(self, file_path: str):
        """从文件加载音频为 numpy 数组."""
        with open(file_path, "rb") as f:
            audio_bytes = f.read()
        return self._load_bytes_to_numpy(audio_bytes)

    def _log_recognition_result(self, result: List[Dict], audio_size: int,
                               total_time: float, inference_time: float):
        """
        记录识别结果的详细日志。

        Args:
            result: ASR 识别结果
            audio_size: 音频数据大小（字节或样本数）
            total_time: 总耗时（秒）
            inference_time: 模型推理耗时（秒）
        """
        if not result or not result[0]:
            print(f"[FunASR] Recognition completed: no text detected, "
                  f"audio_size={audio_size}, total_time={total_time:.3f}s")
            return

        text = result[0].get('preds', '')
        text_compact = text.replace(' ', '')  # 移除空格显示更紧凑

        print(f"[FunASR] Recognition completed:")
        print(f"  Text: {text_compact}")
        print(f"  Audio size: {audio_size} units")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Inference time: {inference_time:.3f}s")

        # 记录原始时间戳信息（如果需要详细分析）
        if 'timestamp' in result[0]:
            timestamps = result[0]['timestamp']
            if timestamps:
                duration_ms = timestamps[-1][1] - timestamps[0][0]
                print(f"  Speech duration: {duration_ms}ms")

    def extract_text(self, result: List[Dict]) -> str:
        """
        从识别结果中提取纯文本（移除空格）。

        Args:
            result: ASR 识别结果

        Returns:
            str: 识别的文本（无空格）
        """
        if not result or not result[0]:
            return ""

        preds = result[0].get('preds', '')
        return preds.replace(' ', '')

    def extract_text_with_spaces(self, result: List[Dict]) -> str:
        """
        从识别结果中提取文本（保留空格分隔）。

        Args:
            result: ASR 识别结果

        Returns:
            str: 识别的文本
        """
        if not result or not result[0]:
            return ""

        return result[0].get('preds', '')


# 全局模型实例（单例模式）
_asr_wrapper: Optional[FunASRWrapper] = None


def get_asr_wrapper(model_dir: str = None,
                     quantize: bool = True,
                     batch_size: int = 1) -> FunASRWrapper:
    """
    获取全局 ASR wrapper 实例（单例模式）。

    Args:
        model_dir: FunASR 模型目录（默认：脚本同级目录下的 speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx）
        quantize: 是否使用量化模型
        batch_size: 批处理大小

    Returns:
        FunASRWrapper: ASR wrapper 实例
    """
    global _asr_wrapper

    if _asr_wrapper is None:
        _asr_wrapper = FunASRWrapper(model_dir, quantize, batch_size)
        load_time = _asr_wrapper.load()
        print(f"[FunASR] Model loaded successfully in {load_time:.2f}s")
        print(f"[FunASR] Model directory: {_asr_wrapper.model_dir}")

    return _asr_wrapper


# 便捷函数
def recognize_audio(audio_bytes: bytes, sample_rate: int = TARGET_SAMPLE_RATE) -> str:
    """
    便捷函数：识别音频字节并返回文本。

    Args:
        audio_bytes: PCM16 音频字节数据
        sample_rate: 采样率

    Returns:
        str: 识别的文本（无空格）
    """
    wrapper = get_asr_wrapper()
    result = wrapper.recognize(audio_bytes, sample_rate)
    return wrapper.extract_text(result)


# 使用示例（用于测试）
if __name__ == "__main__":
    # 测试识别
    def load_bytes_from_file(file_path):
        with open(file_path, "rb") as f:
            return f.read()

    audio_bytes = load_bytes_from_file('tests/hdj-zl.wav')
    text = recognize_audio(audio_bytes)
    print(f"Final text: {text}")
