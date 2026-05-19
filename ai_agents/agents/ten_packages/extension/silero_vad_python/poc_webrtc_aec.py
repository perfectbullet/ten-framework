"""POC: 验证 webrtc-audio-processing 的 AEC + AGC + NS 效果。

使用 VAD dump 的 PCM 文件（麦克风输入 + TTS 参考信号）进行处理，
输出处理前后的 WAV 文件用于对比。

用法:
    python poc_webrtc_aec.py --input_pcm <mic_pcm> --reverse_pcm <tts_pcm>
    python poc_webrtc_aec.py --input_pcm <mic_pcm>  # 无参考信号，仅 AGC+NS
"""

import argparse
import os
import wave

import numpy as np
from webrtc_audio_processing import AudioProcessingModule

SAMPLE_RATE = 16000
CHANNELS = 1
BYTES_PER_SAMPLE = 2
# WebRTC 要求每次处理 10ms
FRAME_SAMPLES = SAMPLE_RATE * 10 // 1000  # 160 samples
FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE  # 320 bytes


def save_wav(filepath: str, data: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


def main():
    parser = argparse.ArgumentParser(
        description="POC: webrtc-audio-processing AEC+AGC+NS"
    )
    parser.add_argument(
        "--input_pcm",
        default="/mnt/d/服务器上的数据/vad_dump/vad_in.pcm",
        help="麦克风输入 PCM 文件",
    )
    parser.add_argument(
        "--reverse_pcm",
        default="",
        help="TTS 参考信号文件（用于 AEC），不传则仅启用 AGC+NS",
    )
    parser.add_argument(
        "--aec_level",
        type=int,
        default=3,
        help="AEC 级别 0-3 (0=off, 1=low, 2=moderate, 3=high)",
    )
    parser.add_argument(
        "--ns_level",
        type=int,
        default=1,
        help="NS 级别 0-3 (1=低强度降噪，3 会消除低音量语音)",
    )
    parser.add_argument(
        "--agc_level",
        type=int,
        default=1,
        help="AGC 类型 0-3 (仅 1 有效，2/3 会消除低音量信号)",
    )
    parser.add_argument(
        "--system_delay",
        type=int,
        default=0,
        help="系统延迟(ms)，参考信号与麦克风之间的延迟估计",
    )
    parser.add_argument(
        "--start_ms",
        type=int,
        default=0,
        help="起始偏移 (ms)",
    )
    parser.add_argument(
        "--duration_ms",
        type=int,
        default=30000,
        help="处理时长 (ms)，默认 30s",
    )
    args = parser.parse_args()

    def read_audio(path: str) -> np.ndarray:
        """读取 PCM 或 WAV 文件，返回 int16 单声道数据。"""
        if path.endswith(".wav"):
            with wave.open(path, "rb") as wf:
                assert wf.getnchannels() == 1, "仅支持单声道 WAV"
                assert wf.getsampwidth() == 2, "仅支持 16-bit WAV"
                return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        return np.fromfile(path, dtype=np.int16)

    # 读取输入
    input_raw = read_audio(args.input_pcm)
    offset_samples = int(args.start_ms * SAMPLE_RATE / 1000)
    duration_samples = int(args.duration_ms * SAMPLE_RATE / 1000)
    input_raw = input_raw[offset_samples : offset_samples + duration_samples]
    print(f"输入: {args.input_pcm} ({len(input_raw)} samples, "
          f"{len(input_raw)/SAMPLE_RATE:.1f}s)")

    # 读取参考信号（TTS 输出）
    has_reverse = bool(args.reverse_pcm) and os.path.exists(args.reverse_pcm)
    if has_reverse:
        reverse_raw = read_audio(args.reverse_pcm)
        reverse_raw = reverse_raw[
            offset_samples : offset_samples + duration_samples
        ]
        print(f"参考: {args.reverse_pcm} ({len(reverse_raw)} samples, "
              f"{len(reverse_raw)/SAMPLE_RATE:.1f}s)")
    else:
        reverse_raw = None
        print("参考信号不存在，仅启用 AGC + NS")

    # 初始化 WebRTC AudioProcessing
    # 注意：必须通过构造函数参数启用功能，set_xxx_level 仅调整级别
    ap = AudioProcessingModule(
        aec_type=args.aec_level if has_reverse else 0,
        enable_ns=args.ns_level > 0,
        agc_type=args.agc_level if args.agc_level > 0 else 0,
        enable_vad=True,
    )
    ap.set_stream_format(SAMPLE_RATE, CHANNELS)
    if has_reverse:
        ap.set_reverse_stream_format(SAMPLE_RATE, CHANNELS)
    if args.ns_level > 0:
        ap.set_ns_level(args.ns_level)
    ap.set_system_delay(args.system_delay)

    # 输出目录
    output_dir = os.path.dirname(args.input_pcm)

    # 分帧处理
    total_frames = len(input_raw) // FRAME_SAMPLES
    output_frames = []
    voice_count = 0
    echo_count = 0

    for i in range(total_frames):
        # 近端帧（麦克风）
        start = i * FRAME_SAMPLES
        end = start + FRAME_SAMPLES
        frame_bytes = input_raw[start:end].tobytes()

        # 先喂参考信号（远端），再处理近端
        if has_reverse and i < len(reverse_raw) // FRAME_SAMPLES:
            rev_start = i * FRAME_SAMPLES
            rev_end = rev_start + FRAME_SAMPLES
            rev_bytes = reverse_raw[rev_start:rev_end].tobytes()
            ap.process_reverse_stream(rev_bytes)

        # 处理近端
        out_bytes = ap.process_stream(frame_bytes)
        out_frame = np.frombuffer(out_bytes, dtype=np.int16).copy()
        output_frames.append(out_frame)

        if ap.has_voice():
            voice_count += 1
        if ap.has_echo():
            echo_count += 1

        if (i + 1) % 1000 == 0:
            print(f"  处理进度: {i+1}/{total_frames} frames...")

    output_raw = np.concatenate(output_frames)

    # 统计信息
    input_rms = np.sqrt(np.mean(input_raw.astype(np.float32) ** 2))
    output_rms = np.sqrt(np.mean(output_raw.astype(np.float32) ** 2))
    input_peak = np.max(np.abs(input_raw))
    output_peak = np.max(np.abs(output_raw))

    print(f"\n=== 处理结果 ===")
    print(f"总帧数: {total_frames} ({total_frames * 10 / 1000:.1f}s)")
    print(f"检测到语音帧: {voice_count} ({voice_count/total_frames*100:.1f}%)")
    print(f"检测到回声帧: {echo_count} ({echo_count/total_frames*100:.1f}%)")
    print(f"输入  RMS: {input_rms:.1f}, Peak: {input_peak}")
    print(f"输出  RMS: {output_rms:.1f}, Peak: {output_peak}")
    gain_db = 20 * np.log10(output_rms / input_rms) if input_rms > 0 else 0
    print(f"增益: {gain_db:.1f} dB")

    # 保存输出（与输入文件同目录）
    basename = os.path.splitext(os.path.basename(args.input_pcm))[0]
    input_wav = os.path.join(output_dir, f"{basename}_original.wav")
    output_wav = os.path.join(output_dir, f"{basename}_agc_ns.wav")

    save_wav(input_wav, input_raw)
    save_wav(output_wav, output_raw)

    print(f"\n已保存:")
    print(f"  原始输入: {input_wav}")
    print(f"  处理输出: {output_wav}")


if __name__ == "__main__":
    main()
