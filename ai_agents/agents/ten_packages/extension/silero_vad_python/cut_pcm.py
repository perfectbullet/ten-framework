"""从 PCM 文件中截取指定时间段并保存为 WAV。"""

import argparse
import wave

import numpy as np

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2


def main():
    parser = argparse.ArgumentParser(description="截取 PCM 音频片段保存为 WAV")
    parser.add_argument("--audio_file", required=True, help="输入 PCM 文件路径")
    parser.add_argument("--start_ms", type=int, required=True, help="起始时间 (ms)")
    parser.add_argument("--end_ms", type=int, required=True, help="结束时间 (ms)")
    parser.add_argument("--output", help="输出 WAV 文件路径 (默认自动生成)")
    args = parser.parse_args()

    raw = np.fromfile(args.audio_file, dtype=np.int16)
    start_sample = int(args.start_ms * SAMPLE_RATE / 1000)
    end_sample = int(args.end_ms * SAMPLE_RATE / 1000)

    segment = raw[start_sample:end_sample]
    duration_ms = args.end_ms - args.start_ms

    output = args.output or f"cut_{args.start_ms}ms-{args.end_ms}ms.wav"
    with wave.open(output, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(BYTES_PER_SAMPLE)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(segment.tobytes())

    print(f"已保存: {output} ({duration_ms}ms, {len(segment)} samples)")


if __name__ == "__main__":
    main()
