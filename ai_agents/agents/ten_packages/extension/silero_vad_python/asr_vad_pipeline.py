from funasr_onnx import Paraformer, Fsmn_vad
import librosa
import io
import tempfile
import os
import soundfile

TARGET_SAMPLE_RATE = 16000  # 目标采样率 16000Hz

# VAD 模型：语音活动检测
vad_model_dir = "speech_fsmn_vad_zh-cn-16k-common-onnx"
vad_model = Fsmn_vad(vad_model_dir, batch_size=1)

# ASR 模型：语音识别
asr_model_dir = "speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx"
asr_model = Paraformer(asr_model_dir, batch_size=1, quantize=True)


def load_bytes_from_file(file_path):
    """
    从文件读取音频字节数据

    Args:
        file_path: 音频文件路径

    Returns:
        bytes: 音频字节数据
    """
    with open(file_path, "rb") as f:
        return f.read()


def asr_with_vad(audio_bytes, vad_model, asr_model, target_sr=TARGET_SAMPLE_RATE):
    """
    结合 VAD 和 ASR 进行语音识别和分段

    处理流程：
    1. 加载音频并自动重采样到目标采样率
    2. 使用 VAD 检测语音段落
    3. 对每个语音段落进行 ASR 识别
    4. 返回带时间戳的识别结果

    Args:
        audio_bytes: 音频字节数据（支持 WAV, MP3 等多种格式）
        vad_model: VAD 模型实例
        asr_model: ASR 模型实例
        target_sr: 目标采样率，默认 16000Hz

    Returns:
        List[Dict]: 识别结果列表，每个元素包含:
            - start_time: 开始时间（毫秒）
            - end_time: 结束时间（毫秒）
            - text: 识别文本
    """
    try:
        # 1. 加载音频，自动重采样到目标采样率
        audio_buffer = io.BytesIO(audio_bytes)
        waveform, sr = librosa.load(audio_buffer, sr=target_sr)

        # 2. 保存到临时文件（VAD 模型需要文件路径）
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            soundfile.write(tmp.name, waveform, target_sr)
            tmp_path = tmp.name

        # 3. VAD: 检测语音段落
        vad_segments = vad_model(tmp_path)

        # 4. 提取并识别每个段落
        results = []
        for start_ms, end_ms in vad_segments:
            # 将毫秒转换为样本点
            start_sample = int(start_ms * target_sr // 1000)
            end_sample = int(end_ms * target_sr // 1000)

            # 提取语音片段
            segment = waveform[start_sample:end_sample]

            # 跳过太短的片段（小于 100 个样本点）
            if len(segment) < 100:
                continue

            # ASR 识别
            try:
                segment_result = asr_model([segment])
                text = segment_result[0]['preds'] if segment_result else ''
            except Exception as e:
                print(f"Warning: ASR failed for segment [{start_ms}ms - {end_ms}ms]: {e}")
                text = ''

            results.append({
                'start_time': start_ms,
                'end_time': end_ms,
                'text': text
            })

        # 5. 清理临时文件
        os.unlink(tmp_path)

        return results

    except Exception as e:
        raise ValueError(f"ASR with VAD failed: {e}")


# 使用示例
if __name__ == "__main__":
    # 从文件读取音频
    audio_bytes = load_bytes_from_file('tests/hdj-zl.wav')

    # 使用 VAD + ASR 进行识别
    results = asr_with_vad(audio_bytes, vad_model, asr_model)

    # 打印识别结果
    print(f"检测到 {len(results)} 个语音段落\n")
    for i, result in enumerate(results, 1):
        print(f"段落 {i}: [{result['start_time']}ms - {result['end_time']}ms]")
        print(f"  文本: {result['text']}\n")
