"""
WebSocket TTS合成测试脚本
用于测试 ws://192.168.8.230:50002/streaming/ws 接口
"""
import asyncio
import json
import base64
import os
import struct
import time
import websockets

# 配置
WS_URL = "ws://192.168.8.230:50002/streaming/ws"
SPEAKER_ID = "胡桃"  # 请替换为你的说话人ID

# 多个文本片段
TEXT_CHUNKS = [
    {"text": "收到好友从远方寄来的生日礼物，", "chunk_id": 1},
    {"text": "那份意外的惊喜与深深的祝福", "chunk_id": 2},
    {"text": "让我心中充满了甜蜜的快乐，", "chunk_id": 3},
    {"text": "笑容如花儿般绽放。", "chunk_id": 4},
    {"text": "感谢有你陪伴我走过的每一天，", "chunk_id": 5},
    {"text": "你的友情如星光般璀璨，", "chunk_id": 6},
    {"text": "照亮了我前行的路，", "chunk_id": 7},
    {"text": "愿我们的友谊长存，", "chunk_id": 8},
    {"text": "如同这美好的时光，", "chunk_id": 9},
    {"text": "永远珍藏在心间。", "chunk_id": 10},
]


def add_wav_header(pcm_data: bytes, sample_rate: int = 16000, num_channels: int = 1, sample_width: int = 2) -> bytes:
    """为原始 PCM 数据添加 WAV 文件头"""
    # num_frames = len(pcm_data) // (num_channels * sample_width)
    byte_rate = sample_rate * num_channels * sample_width
    block_align = num_channels * sample_width
    
    wav_header = b'RIFF'
    wav_header += struct.pack('<I', 36 + len(pcm_data))
    wav_header += b'WAVE'
    
    wav_header += b'fmt '
    wav_header += struct.pack('<I', 16)
    wav_header += struct.pack('<H', 1)
    wav_header += struct.pack('<H', num_channels)
    wav_header += struct.pack('<I', sample_rate)
    wav_header += struct.pack('<I', byte_rate)
    wav_header += struct.pack('<H', block_align)
    wav_header += struct.pack('<H', sample_width * 8)
    
    wav_header += b'data'
    wav_header += struct.pack('<I', len(pcm_data))
    wav_header += pcm_data
    
    return wav_header


async def test_websocket_tts():
    """测试 WebSocket TTS 合成"""
    print("=" * 60)
    print("WebSocket TTS合成测试")
    print("=" * 60)
    print(f"连接地址: {WS_URL}")
    print(f"说话人: {SPEAKER_ID}")
    print()

    total_start_time = time.time()
    all_audio_data = []  # 存储所有音频片段
    total_chunks_processed = 0
    total_audio_bytes = 0

    try:
        async with websockets.connect(WS_URL) as websocket:
            print("✓ WebSocket 已连接")
            print()

            # 处理多个文本片段
            for chunk_info in TEXT_CHUNKS:
                chunk_text = chunk_info["text"]
                chunk_id = chunk_info["chunk_id"]

                print(f"[发送] Chunk #{chunk_id}: {chunk_text}")
                request_start_time = time.time()

                # 构建请求
                request = {
                    "action": "synthesize",
                    "text": chunk_text,
                    "spk_id": SPEAKER_ID,
                    "chunk_id": chunk_id
                }

                # 发送请求
                await websocket.send(json.dumps(request))
                print("  请求已发送")

                # 接收响应
                audio_chunks = []
                chunk_count = 0
                first_chunk_time = None

                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        response = json.loads(message)

                        if response["type"] == "audio":
                            # 记录首块时间
                            if first_chunk_time is None:
                                first_chunk_time = time.time()
                                ttfb = (first_chunk_time - request_start_time) * 1000
                                print(f"  首字节延迟: {ttfb:.2f}ms")

                            # 解码音频数据
                            audio_bytes = base64.b64decode(response["data"])
                            audio_chunks.append(audio_bytes)
                            chunk_count += 1

                            if chunk_count % 3 == 0:
                                total_bytes = sum(len(chunk) for chunk in audio_chunks)
                                print(f"  已接收 {chunk_count} 块，共 {total_bytes:,} 字节")

                        elif response["type"] == "complete":
                            receive_end_time = time.time()
                            receive_duration = (receive_end_time - request_start_time) * 1000

                            # 合并当前chunk的音频
                            chunk_audio = b''.join(audio_chunks)

                            # 添加到总音频列表
                            all_audio_data.append(chunk_audio)
                            total_chunks_processed += chunk_count
                            total_audio_bytes += len(chunk_audio)

                            audio_duration = (len(chunk_audio) / (16000 * 2)) if chunk_audio else 0

                            print("  ✓ 完成")
                            print(f"    块数: {chunk_count}")
                            print(f"    大小: {len(chunk_audio):,} 字节")
                            print(f"    耗时: {receive_duration:.2f}ms")
                            print(f"    音频时长: {audio_duration:.2f}s")
                            if audio_duration > 0:
                                rtf = receive_duration / (audio_duration * 1000)
                                print(f"    RTF: {rtf:.2f}x")
                            print()
                            break

                        elif response["type"] == "error":
                            print(f"  ✗ 错误: {response.get('data', 'Unknown error')}")
                            break

                    except asyncio.TimeoutError:
                        print("  ✗ 接收超时")
                        break

            # 合并所有音频为一个文件
            print("✓ 所有文本合成完成")
            print()

            if all_audio_data:
                print("=" * 60)
                print("正在合并音频...")
                print("=" * 60)

                # 合并所有音频数据
                complete_audio = b''.join(all_audio_data)

                # 添加 WAV 文件头
                output_file = "ws_output_complete.wav"
                audio_with_header = add_wav_header(complete_audio, sample_rate=16000)

                with open(output_file, 'wb') as f:
                    f.write(audio_with_header)

                file_size = os.path.getsize(output_file)
                total_duration = (len(complete_audio) / (16000 * 2)) if complete_audio else 0

                print(f"✓ 合并完成")
                print(f"  总块数: {total_chunks_processed}")
                print(f"  文件大小: {file_size:,} 字节 ({file_size / 1024:.2f} KB)")
                print(f"  总音频时长: {total_duration:.2f}s")
                print(f"  保存路径: {output_file}")
                print()

    except Exception as e:
        print(f"✗ 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 统计总耗时
    total_end_time = time.time()
    total_duration = (total_end_time - total_start_time) * 1000

    print(f"{'=' * 60}")
    print(f"总耗时: {total_duration:.2f}ms ({total_duration/1000:.2f}s)")
    print(f"{'=' * 60}")

    return True


async def main():
    print("\n" + "=" * 60)
    print("CosyVoice WebSocket TTS 测试")
    print("=" * 60 + "\n")
    
    success = await test_websocket_tts()
    
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
