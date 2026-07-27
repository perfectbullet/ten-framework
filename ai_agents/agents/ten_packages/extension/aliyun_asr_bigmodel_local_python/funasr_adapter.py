#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
"""本地 ASR WebSocket 服务的 Dashscope 兼容适配器。

服务采用 ``vllm_guide_zh_v2.md`` 中定义的 vLLM 协议：START、可选配置命令、
PCM 音频和 STOP。
"""

import asyncio
import json
import ssl
import threading
import time
import wave
from queue import Queue, Empty
from typing import Any, Dict, List, Optional
from websocket import ABNF, create_connection
from pathlib import Path
from datetime import datetime


class FunASRRecognitionResult:
    """vLLM WebSocket 识别结果。"""

    def __init__(self, message: Dict[str, Any]):
        """
        使用 vLLM WebSocket 消息初始化。

        Args:
            message: 服务端原始 JSON 消息。
        """
        self.raw_message = message
        self.status_code = 200
        self.request_id = message.get("wav_name", "default")
        self.code = None
        self.message = ""

    def get_sentences(self) -> List[Dict[str, Any]]:
        """获取服务端本次推送的已锁定句子快照。

        服务端会持续回传当前会话的累计 ``sentences``。结果对象没有跨消息状态，
        由扩展根据句子的时间范围过滤已发送的句子。
        """
        raw_sentences = self.raw_message.get("sentences")
        if not isinstance(raw_sentences, list):
            return []

        sentences: List[Dict[str, Any]] = []
        for raw_sentence in raw_sentences:
            if not isinstance(raw_sentence, dict):
                continue

            text = str(raw_sentence.get("text", "")).strip()
            if not text:
                continue

            start_ms = int(raw_sentence.get("start", 0) or 0)
            end_ms = int(raw_sentence.get("end", 0) or 0)
            sentences.append(
                {
                    "text": text,
                    "begin_time": start_ms,
                    "end_time": end_ms,
                    "words": [],
                    "final": True,
                }
            )

        return sentences

class FunASRRecognitionCallback:
    """Base callback class compatible with Dashscope's RecognitionCallback interface."""

    def on_open(self) -> None:
        """Called when WebSocket connection is established."""
        pass

    def on_complete(self) -> None:
        """Called when recognition is completed."""
        pass

    def on_error(self, result: FunASRRecognitionResult) -> None:
        """Called when an error occurs."""
        pass

    def on_close(self) -> None:
        """Called when WebSocket connection is closed."""
        pass

    def on_event(self, result: FunASRRecognitionResult) -> None:
        """Called when a recognition result is received."""
        pass


class FunASRRecognition:
    """
    FunASR WebSocket Recognition client with Dashscope-compatible interface.

    This class adapts the FunASR WebSocket API to match Dashscope's Recognition interface,
    enabling drop-in replacement in the TEN Framework extension.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: str = "10095",
        is_ssl: bool = False,
        chunk_size: str = "5,10,5",
        chunk_interval: int = 10,
        mode: str = "2pass",
        wav_name: str = "default",
        callback: Optional[FunASRRecognitionCallback] = None,
        # Dashscope-compatible parameters (may not all be used by FunASR)
        model: str = "",
        format: str = "pcm",
        sample_rate: int = 16000,
        language_hints: List[str] = None,
        send_buffer_size: int = 23040,  # Buffer size in bytes (default: 0.72s @ 16kHz 16-bit mono)
        **kwargs,
    ):
        """
        Initialize FunASR WebSocket recognition client.

        Args:
            host: FunASR server host
            port: FunASR server port
            is_ssl: Whether to use WSS (True) or WS (False)
            chunk_size: FunASR chunk size parameter (e.g., "5,10,5")
            chunk_interval: Chunk interval in milliseconds
            mode: Recognition mode ("2pass", "offline", "online")
            wav_name: Audio stream identifier
            callback: Callback handler for recognition events
            model: Model name (for compatibility, not used by FunASR directly)
            format: Audio format (default: "pcm")
            sample_rate: Audio sample rate (default: 16000)
            language_hints: Language hints (for compatibility)
            send_buffer_size: Audio send buffer size in bytes (default: 23040 = 0.72s @ 16kHz)
            **kwargs: Additional parameters (hotwords, itn, etc.)
        """
        self.host = host
        self.port = port
        self.is_ssl = is_ssl
        self.chunk_size = chunk_size
        self.chunk_interval = chunk_interval
        self.mode = mode
        self.wav_name = wav_name
        self.callback = callback
        self.sample_rate = sample_rate
        self.format = format
        self.language_hints = language_hints or []
        self.kwargs = kwargs

        # Connection state
        self.websocket = None
        self._thread_recv = None
        self.msg_queue = Queue()
        self._offline_msg_done = False  # 跟踪是否收到最终结果（is_final == True）
        self._session_active = False

        # Asyncio event loop for thread-safe callbacks
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop in current thread
            pass

        # Message counter for JSON file naming
        self._msg_counter = 0
        self._json_output_dir = Path("msg_dict_json")
        self._json_output_dir.mkdir(exist_ok=True)

        # Audio data buffer for debugging (collects all sent audio data)
        self._audio_data_buffer: List[bytes] = []
        self._audio_dump_dir = Path("send_audio_save")
        self._audio_dump_enabled: bool = True

        # Audio send buffer for batch sending
        self._send_buffer_size = send_buffer_size
        self._send_buffer: List[bytes] = []

    def _save_msg_dict_to_json(self, msg_dict: Dict[str, Any]) -> None:
        """
        Save msg_dict to a JSON file with timestamp.

        Args:
            msg_dict: The message dictionary to save
        """
        try:
            self._msg_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[
                :-3
            ]  # Remove last 3 digits of microseconds
            filename = f"msg_{self._msg_counter:04d}_{timestamp}.json"
            filepath = self._json_output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(msg_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # Silently fail to avoid disrupting the main recognition flow
            print(f"Failed to save msg_dict to JSON: {e}")

    def start(self, **kwargs) -> None:
        """
        Start WebSocket connection and recognition (compatible with Dashscope API).

        Args:
            **kwargs: Additional parameters to override initialization values
        """
        if self.websocket is not None:
            raise RuntimeError("Recognition is already running")

        # Update parameters if provided
        self.kwargs.update(kwargs)

        try:
            # Build WebSocket URI
            protocol = "wss" if self.is_ssl else "ws"
            uri = f"{protocol}://{self.host}:{self.port}/ws"

            # Create SSL context for WSS
            if self.is_ssl:
                ssl_context = ssl.SSLContext()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_opt = {"cert_reqs": ssl.CERT_NONE}
            else:
                ssl_context = None
                ssl_opt = None

            # Establish WebSocket connection
            self.websocket = create_connection(uri, sslopt=ssl_opt, ssl=ssl_context)
            self._offline_msg_done = False  # 重置最终结果标志
            self._send_buffer.clear()  # Clear any stale buffered data from previous session

            # Start message receiving thread
            self._thread_recv = threading.Thread(
                target=self._thread_receive_messages, daemon=True
            )
            self._thread_recv.start()

            # Create audio dump directory if enabled
            if self._audio_dump_enabled:
                self._audio_dump_dir.mkdir(exist_ok=True)
                print(
                    f"[Audio Dump] Audio dump enabled, saving to: {self._audio_dump_dir.absolute()}"
                )

            # Trigger on_open callback
            if self.callback:
                self._safe_callback(self.callback.on_open)

        except Exception as e:
            self.websocket = None
            error_result = FunASRRecognitionResult(
                {"text": "", "error": str(e), "is_final": False}
            )
            error_result.status_code = 500
            error_result.message = f"Failed to connect to FunASR server: {e}"

            if self.callback:
                self._safe_callback(self.callback.on_error, error_result)
            raise

    def _thread_receive_messages(self) -> None:
        """Background thread to receive WebSocket messages and trigger callbacks."""
        try:
            while self.websocket is not None:
                try:
                    msg = self.websocket.recv()
                    if msg is None or len(msg) == 0:
                        continue

                    # Parse JSON message
                    msg_dict = json.loads(msg)

                    # 检测最终结果，设置标志（参考 funasr_wss_client.py 第 255-256 行）
                    is_final = (
                        msg_dict.get("is_final", False)
                        or msg_dict.get("mode") == "2pass-offline"
                    )
                    if is_final:
                        self._offline_msg_done = True

                    # Save msg_dict to JSON file
                    self._save_msg_dict_to_json(msg_dict)

                    result = FunASRRecognitionResult(msg_dict)

                    # Queue the message for potential synchronous access
                    self.msg_queue.put(msg_dict)

                    # Trigger on_event callback
                    if self.callback:
                        self._safe_callback(self.callback.on_event, result)

                except Exception as e:
                    # WebSocket 关闭或其他异常
                    if self.websocket is not None:
                        # 只有在 websocket 还存在时才报告错误
                        error_result = FunASRRecognitionResult(
                            {"text": "", "error": str(e), "is_final": False}
                        )
                        error_result.status_code = 500
                        error_result.message = f"Error receiving message: {e}"

                        if self.callback:
                            self._safe_callback(self.callback.on_error, error_result)
                    break
        finally:
            # Connection closed
            if self.callback:
                self._safe_callback(self.callback.on_close)

    def _safe_callback(self, callback_func, *args) -> None:
        """
        Safely invoke callback function in asyncio event loop context.

        This ensures thread-safe callback execution when callbacks are coroutines
        or need to interact with asyncio-based code.
        """
        if self.loop and self.loop.is_running():
            # If we have an event loop, schedule the callback there
            if asyncio.iscoroutinefunction(callback_func):
                asyncio.run_coroutine_threadsafe(callback_func(*args), self.loop)
            else:
                self.loop.call_soon_threadsafe(callback_func, *args)
        else:
            # No event loop or not running, call directly
            callback_func(*args)

    def _flush_send_buffer(self) -> None:
        """Send any accumulated audio data in the buffer."""
        if not self._send_buffer:
            return
        if self.websocket is None:
            self._send_buffer.clear()
            return

        try:
            combined_data = b"".join(self._send_buffer)
            self.websocket.send(combined_data, ABNF.OPCODE_BINARY)
            self._send_buffer.clear()
        except Exception:
            # Connection closed or error
            self._send_buffer.clear()

    def _start_session(self) -> None:
        """在发送 PCM 音频前启动一轮 vLLM 识别会话。"""
        if self.websocket is None or self._session_active:
            return

        self.websocket.send("START")

        if self.language_hints:
            language = self.language_hints[0]
            language_map = {"zh": "中文", "zh-CN": "中文"}
            self.websocket.send(f"LANGUAGE:{language_map.get(language, language)}")

        hotwords = str(self.kwargs.get("hotwords", "")).strip()
        if hotwords:
            self.websocket.send(f"HOTWORDS:{hotwords}")

        self._session_active = True

    def send_audio_frame(self, audio_data: bytes) -> None:
        """
        Send audio frame to FunASR server (compatible with Dashscope API).
        Audio data is buffered until buffer_size is reached before sending.

        Args:
            audio_data: Raw audio bytes (PCM format)
        """
        if self.websocket is None:
            # WebSocket 已关闭，静默返回而不是抛出异常
            return

        try:
            self._start_session()

            # Collect audio data for debugging
            if self._audio_dump_enabled:
                self._audio_data_buffer.append(audio_data)

            # Accumulate audio data in send buffer
            self._send_buffer.append(audio_data)

            # Calculate accumulated buffer size
            buffer_size = sum(len(chunk) for chunk in self._send_buffer)

            # Flush when buffer reaches threshold
            if buffer_size >= self._send_buffer_size:
                combined_data = b"".join(self._send_buffer)
                self.websocket.send(combined_data, ABNF.OPCODE_BINARY)
                self._send_buffer.clear()
        except Exception:
            # 连接已关闭或其他错误，不是致命问题
            # 静默处理，让调用方决定是否重试
            self._send_buffer.clear()

    def _save_as_wav(self, pcm_data: bytes, wav_path: Path, sample_rate: int) -> None:
        """
        Save PCM data as WAV file with proper header.

        Args:
            pcm_data: Raw PCM audio data (16-bit, mono)
            wav_path: Output WAV file path
            sample_rate: Sample rate (e.g., 16000)
        """
        try:
            with wave.open(str(wav_path), "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit = 2 bytes
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_data)
            print(f"[Audio Dump] WAV file saved: {wav_path}")
        except Exception as e:
            print(f"[Audio Dump] Failed to save WAV file: {e}")

    def _save_audio_dump(self) -> None:
        """
        Save collected audio data to PCM and WAV files.
        Called when WebSocket connection is closed.
        """
        try:
            # Generate timestamp-based filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"asr_audio_dump_{timestamp}"

            # Merge all audio chunks
            combined_pcm = b"".join(self._audio_data_buffer)
            total_bytes = len(combined_pcm)

            # Calculate duration (16-bit mono PCM: 2 bytes per sample)
            duration_seconds = total_bytes / (self.sample_rate * 2)

            # Save as PCM
            pcm_path = self._audio_dump_dir / f"{base_filename}.pcm"
            with open(pcm_path, "wb") as f:
                f.write(combined_pcm)

            # Save as WAV (with proper header for easy playback)
            wav_path = self._audio_dump_dir / f"{base_filename}.wav"
            self._save_as_wav(combined_pcm, wav_path, self.sample_rate)

            print("[Audio Dump] Audio dump saved:")
            print(f"[Audio Dump]   - PCM: {pcm_path}")
            print(f"[Audio Dump]   - WAV: {wav_path}")
            print(f"[Audio Dump]   - Total bytes: {total_bytes}")
            print(
                f"[Audio Dump]   - Duration: ~{duration_seconds:.1f} seconds @ {self.sample_rate}Hz 16bit mono"
            )

            # Clear buffer for next session
            self._audio_data_buffer.clear()

        except Exception as e:
            print(f"[Audio Dump] Failed to save audio dump: {e}")

    def stop(self, timeout: float = 2.0) -> None:
        """
        Stop recognition and close WebSocket connection (compatible with Dashscope API).

        Args:
            timeout: Base time to wait before checking for final results
        """
        if self.websocket is None:
            return  # 已经停止

        try:
            # Flush any remaining buffered audio data before sending end-of-speech
            self._flush_send_buffer()

            # 发送 vLLM 会话结束标记。
            self.send_end_of_speech()

            # Wait base time (参考 funasr_wss_client.py 第 226 行)
            time.sleep(timeout)

            # 循环等待最终结果（参考 funasr_wss_client.py 第 231-232 行）
            # 最多等待 10 秒，避免无限等待
            for _ in range(10):
                if self._offline_msg_done:
                    break
                time.sleep(1)

            # Close WebSocket
            self.websocket.close()
        except Exception:
            # Log error but continue cleanup
            pass
        finally:
            # 先关闭 websocket，这样残留的 send_audio_frame 会自然失败
            self.websocket = None

            # Clear send buffer
            self._send_buffer.clear()

            # Save audio dump if enabled and data was collected
            if self._audio_dump_enabled and self._audio_data_buffer:
                self._save_audio_dump()

            # Trigger on_complete callback
            if self.callback:
                self._safe_callback(self.callback.on_complete)

    def send_end_of_speech(self) -> None:
        """
        Send end-of-speech marker without closing the connection.
        This allows continuous speech recognition sessions.
        Also saves audio dump if enabled.
        """
        if self.websocket is None:
            return

        try:
            # 发送 STOP 前先发送缓冲区中剩余的音频。
            self._flush_send_buffer()

            if not self._session_active:
                return

            # vLLM 要求发送文本 STOP，不能发送旧 FunASR 的
            # {"is_speaking": false} JSON 消息。
            self.websocket.send("STOP")
            self._session_active = False

            # Save audio dump if enabled and data was collected
            if self._audio_dump_enabled and self._audio_data_buffer:
                self._save_audio_dump()
        except Exception as e:
            print(f"[FunASR] Failed to send end-of-speech: {e}")

    def is_running(self) -> bool:
        """Check if recognition is currently running."""
        return (
            self.websocket is not None
            and self._thread_recv is not None
            and self._thread_recv.is_alive()
        )

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Get the last message from queue (for synchronous usage patterns)."""
        try:
            return self.msg_queue.get_nowait()
        except Empty:
            return None
