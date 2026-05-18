import os
import wave

import numpy as np
from funasr import AutoModel

# 获取脚本所在目录
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL_DIR = os.path.join(
    _SCRIPT_DIR,
    "speech_fsmn_vad_zh-cn-16k-common-pytorch",
)

chunk_size = 200  # ms
sample_rate = 16000

model = AutoModel(
    model=DEFAULT_MODEL_DIR,
    device="cpu",
    log_level="warning",
    disable_update=True,
    disable_pbar=True,
    lookback_time_start_point=400,  # 构建时设才生效
    lookahead_time_end_point=200,  # 构建时设才生效
    do_extend=1,  # 构建时设才生效
    max_end_silence_time=1000,  # 两个地方都行
)

print(model.model_path)

# 读取 PCM 文件
pcm_file = "/mnt/d/vad_dump/vad_dump234前端音量条件后的/vad_in.pcm"
raw_data = np.fromfile(pcm_file, dtype=np.int16)
speech = raw_data.astype(np.float32) / 32768.0
chunk_stride = int(chunk_size * sample_rate / 1000)

# 输出目录与 PCM 同目录
output_dir = os.path.dirname(pcm_file)


def save_segment(data: np.ndarray, start_ms: int, end_ms: int, idx: int) -> None:
    filename = f"vad_segment_{idx}_{start_ms}ms-{end_ms}ms.wav"
    filepath = os.path.join(output_dir, filename)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data.tobytes())
    duration_ms = end_ms - start_ms
    print(f"  -> Saved: {filename} ({duration_ms}ms, {len(data)} samples)")


# VAD 流式处理
cache = {}
segment_count = 0
segment_start_ms = None
total_chunk_num = int((len(speech) - 1) / chunk_stride + 1)

for i in range(total_chunk_num):
    speech_chunk = speech[i * chunk_stride : (i + 1) * chunk_stride]
    is_final = i == total_chunk_num - 1

    res = model.generate(
        input=speech_chunk,
        cache=cache,
        is_final=is_final,
        chunk_size=chunk_size,
        speech_noise_thres=0.8,
        is_streaming_input=True,
        detect_mode=1,
    )

    if not res or not res[0]["value"]:
        continue

    segments = res[0]["value"]
    print(f"Chunk {i}: {segments}")

    for seg in segments:
        beg, end = seg[0], seg[1]

        # 语音开始
        if beg != -1:
            segment_start_ms = beg

        # 语音结束
        if end != -1 and segment_start_ms is not None:
            start_sample = int(segment_start_ms * sample_rate / 1000)
            end_sample = int(end * sample_rate / 1000)
            segment_data = raw_data[start_sample:end_sample]
            save_segment(segment_data, segment_start_ms, end, segment_count)
            segment_count += 1
            segment_start_ms = None

print(f"\nDone: {segment_count} segments saved to {output_dir}")
