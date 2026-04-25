#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import re
import asyncio
from datetime import datetime
import os
import traceback
import json

import aiohttp

from websocket import WebSocketConnectionClosedException
from ten_ai_base.const import LOG_CATEGORY_KEY_POINT, LOG_CATEGORY_VENDOR
from ten_ai_base.helper import generate_file_name, PCMWriter
from ten_ai_base.message import (
    ModuleError,
    ModuleErrorCode,
    ModuleErrorVendorInfo,
    ModuleType,
    TTSAudioEndReason,
)
from ten_ai_base.struct import TTSTextInput
from ten_ai_base.tts2 import AsyncTTS2BaseExtension
from ten_runtime import AsyncTenEnv

from .config import CosyTTSConfig
from .cosy_tts import (
    CosyTTSClient,
    MESSAGE_TYPE_PCM,
    MESSAGE_TYPE_CMD_ERROR,
    MESSAGE_TYPE_CMD_CANCEL,
    MESSAGE_TYPE_CMD_RESULT_GENERATED,
)


def get_channel_from_cmdline(ten_env) -> dict:
    """
    从 property.json 文件中读取 agora_rtc 的 channel 值并解析。

    Returns:
        dict: {
            "channel_name": str,  # 如 "employee_4_3_29"
            "team_id": str,       # 如 "4"，解析失败时使用默认值 "4"
            "user_id": str,       # 如 "86622292"，解析失败时使用默认值 "3"
            "employee_id": str    # 如 "29"，解析失败时使用默认值 "29"
        }
    """
    # 默认值
    default_team_id = "4"
    default_user_id = "3"
    default_employee_id = "29"
    default_channel_name = "employee_4_3_29"

    try:
        # 1. 从父进程命令行获取 property.json 文件路径
        parent_pid = os.getppid()
        ten_env.log_info(f"[get_channel] parent_pid: {parent_pid}")

        cmdline_path = f"/proc/{parent_pid}/cmdline"
        ten_env.log_info(f"[get_channel] reading cmdline from: {cmdline_path}")

        with open(cmdline_path, "r") as f:
            cmdline = f.read()
            # cmdline 中的参数用 \x00 分隔，替换为空格以便正则匹配
            cmdline_readable = cmdline.replace("\x00", " ")

            # 保存原始 cmdline 到本地文件（用于调试）
            output_file = f"/tmp/cmdline_pid_{parent_pid}.txt"
            with open(output_file, "wb") as out_f:
                out_f.write(cmdline.encode("utf-8", errors="replace"))
            ten_env.log_info(f"[get_channel] cmdline saved to: {output_file}")

            # 查找 --property 参数（使用替换后的 cmdline_readable）
            # 匹配 /tmp/xxx/property-xxx.json 或 /var/log/property-xxx.json 格式
            match = re.search(
                r"--property\s+(/[a-z]+/[^/]*/property-[^\.]+\.json|/var/log/property-[^\.]+\.json)",
                cmdline_readable,
            )
            if not match:
                ten_env.log_error(
                    "[get_channel] no --property found in cmdline, using defaults"
                )
                return {
                    "channel_name": default_channel_name,
                    "team_id": default_team_id,
                    "user_id": default_user_id,
                    "employee_id": default_employee_id,
                }
            property_path = match.group(1)
            # ten_env.log_info(f"[get_channel] found property path: {property_path}")

        # 2. 读取 property.json 文件
        ten_env.log_info(f"[get_channel] reading property file: {property_path}")
        with open(property_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 3. 导航到 agora_rtc 节点的 property，获取 channel 值
        graphs = data.get("ten", {}).get("predefined_graphs", [])
        ten_env.log_info(f"[get_channel] found {len(graphs)} predefined_graphs")
        if not graphs:
            ten_env.log_error(
                "[get_channel] no predefined_graphs found, using defaults"
            )
            return {
                "channel_name": None,
                "team_id": default_team_id,
                "user_id": default_user_id,
                "employee_id": default_employee_id,
            }

        nodes = graphs[0].get("graph", {}).get("nodes", [])
        ten_env.log_info(f"[get_channel] found {len(nodes)} nodes in graph")
        channel_name = None
        for node in nodes:
            node_name = node.get("name")
            if node_name == "agora_rtc":
                channel_name = node.get("property", {}).get("channel")
                ten_env.log_info(
                    f"[get_channel] found agora_rtc node, channel: {channel_name}"
                )
                break

        if not channel_name:
            ten_env.log_error(
                "[get_channel] no channel found in agora_rtc node, using defaults"
            )
            return {
                "channel_name": None,
                "team_id": default_team_id,
                "user_id": default_user_id,
                "employee_id": default_employee_id,
            }

        # 4. 解析 channel_name 格式: employee_<team_id>_<user_id>_<employee_id>
        parts = channel_name.split("_")
        ten_env.log_info(f"[get_channel] channel_name parts: {parts}, len={len(parts)}")
        if len(parts) >= 4 and parts[0] == "employee":
            ten_env.log_info(
                f"[get_channel] successfully parsed: team_id={parts[1]}, user_id={parts[2]}, employee_id={parts[3]}"
            )
            return {
                "channel_name": channel_name,
                "team_id": parts[1],
                "user_id": parts[2],
                "employee_id": parts[3],
            }
        else:
            # 格式不匹配，返回 channel_name 但使用默认的 team_id, user_id, employee_id
            ten_env.log_error(
                f"[get_channel] channel format mismatch: {channel_name}, using default ids"
            )
            return {
                "channel_name": channel_name,
                "team_id": default_team_id,
                "user_id": default_user_id,
                "employee_id": default_employee_id,
            }
    except Exception as e:
        ten_env.log_error(
            f"[get_channel] Exception: {e}, traceback: {traceback.format_exc()}"
        )
        # 发生任何错误时，返回默认值
        return {
            "channel_name": None,
            "team_id": default_team_id,
            "user_id": default_user_id,
            "employee_id": default_employee_id,
        }


class CosyTTSExtension(AsyncTTS2BaseExtension):
    def __init__(self, name: str) -> None:
        super().__init__(name)

        # TTS client for Cosy TTS service
        self.client: CosyTTSClient | None = None
        # Configuration for TTS settings
        self.config: CosyTTSConfig | None = None
        # Flag indicating if current request is finished
        self.current_request_finished: bool = True
        # ID of the current TTS request being processed
        self.current_request_id: str | None = None
        # Extension name for logging and identification
        self.name: str = name
        # Store PCMWriter instances for different request_ids
        self.recorder_map: dict[str, PCMWriter] = {}
        # Timestamp when TTS request was sent to service
        self.request_start_ts: datetime | None = None
        # Total audio duration for current request in milliseconds
        self.request_total_audio_duration_ms: int | None = None
        # Time to first byte for current request in milliseconds
        self.request_ttfb: int | None = None
        # Total audio bytes received for current request
        self.total_audio_bytes: int = 0
        # Background task for processing audio data
        self.audio_processor_task: asyncio.Task | None = None
        # Flag indicating if the first chunk has been processed
        self.first_chunk: bool = True
        # Flag indicating if tts_audio_end has been sent for current request
        # Count of audio chunks received
        self.chunk_count: int = 0
        # Flag indicating if the first request is being processed
        self.is_first_message_of_request: bool = False
        # Debug audio data (pre-loaded PCM audio for testing)
        self.debug_audio_data: bytes = b""
        # Current position in debug audio data for looping
        self.debug_audio_position: int = 0
        # Chunk size for sending debug audio (bytes)
        self.debug_audio_chunk_size: int = 3200  # 100ms at 16kHz mono 16-bit
        # Flag indicating if debug audio should continue playing after text_input_end
        self.debug_audio_active: bool = False

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        try:
            await super().on_init(ten_env)
            ten_env.log_debug("on_init")
            if self.config is None:
                config_json, _ = await self.ten_env.get_property_to_json("")
                self.config = CosyTTSConfig.model_validate_json(config_json)
                # Update params from config
                self.config.update_params()
                # Validate params
                self.config.validate_params()
                employee_id = get_channel_from_cmdline(ten_env)["employee_id"]

                # 从API获取voice
                self.config.voice = await self._get_voice_from_employee_api(
                    employee_id, ten_env
                )
                ten_env.log_info(
                    f"got employee_id: {employee_id}, resolved voice: {self.config.voice}"
                )

                self.ten_env.log_info(
                    f"cosy tts config: {self.config.to_str(sensitive_handling=True)}",
                    category=LOG_CATEGORY_KEY_POINT,
                )
            # Load debug audio if enabled
            if self.config.use_debug_audio:
                await self._load_debug_audio()
                self.ten_env.log_info(
                    f"Debug audio mode enabled, loaded {len(self.debug_audio_data)} bytes from {self.config.debug_audio_path}",
                    category=LOG_CATEGORY_KEY_POINT,
                )
            else:
                # Initialize Cosy TTS client
                # Use CosyTTSClient for local WebSocket service
                self.ten_env.log_info(
                    f"Using local CosyVoice service at: {self.config.local_service_url}",
                    category=LOG_CATEGORY_KEY_POINT,
                )
                self.client = CosyTTSClient(self.config, self.ten_env, self.vendor())

                self.client.start()

            self.audio_processor_task = asyncio.create_task(self._process_audio_data())
        except Exception as e:
            ten_env.log_error(f"on_init failed: {traceback.format_exc()}")
            await self._send_tts_error(str(e))

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)
        ten_env.log_debug("on_start")

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        if self.audio_processor_task:
            self.audio_processor_task.cancel()
            try:
                await self.audio_processor_task
            except asyncio.CancelledError:
                ten_env.log_info("Audio processor task cancelled.")
            self.audio_processor_task = None

        # Only stop client if not in debug audio mode
        if self.client and not self.config.use_debug_audio:
            # Stop client properly (local client has async stop method)
            if hasattr(self.client, "stop") and asyncio.iscoroutinefunction(
                self.client.stop
            ):
                await self.client.stop()
            self.client = None

        # Clean up all PCMWriters
        await self._cleanup_all_pcm_writers()

        await super().on_stop(ten_env)
        ten_env.log_debug("on_stop")

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(ten_env)
        ten_env.log_debug("on_deinit")

    async def cancel_tts(self) -> None:
        """
        Override cancel_tts to implement TTS-specific cancellation logic.
        This is called when a flush request is received.
        """
        self.ten_env.log_info(
            f"cancel_tts called, current_request_id: {self.current_request_id}"
        )

        # In debug mode, deactivate debug audio
        if self.config.use_debug_audio:
            self.debug_audio_active = False
            self.ten_env.log_info("Debug mode: deactivated debug audio streaming")

        # Cancel the TTS client (only in non-debug mode)
        if self.client and not self.config.use_debug_audio:
            self.ten_env.log_info(
                f"Cancelling TTS client for request ID: {self.current_request_id}"
            )
            self.client.cancel()

        # Handle audio end if there's an active request
        if self.request_start_ts and self.current_request_id:
            await self._handle_tts_audio_end(TTSAudioEndReason.INTERRUPTED)
            self.current_request_finished = True

    async def request_tts(self, t: TTSTextInput) -> None:
        """
        Override this method to handle TTS requests.
        This is called when the TTS request is made.
        """
        try:
            self.ten_env.log_info(
                f"KEYPOINT Requesting TTS for text: {t.text}, text_input_end: {t.text_input_end}, request_id: {t.request_id}, current_request_id: {self.current_request_id}"
            )

            # In debug mode, client is not initialized
            if not self.config.use_debug_audio and self.client is None:
                self.ten_env.log_error("Client is not initialized")
                return

            # Check if audio processor task is still running, restart if needed
            if self.audio_processor_task is None or self.audio_processor_task.done():
                self.ten_env.log_info("Audio processor task not running, restarting...")
                self.audio_processor_task = asyncio.create_task(
                    self._process_audio_data()
                )
                self.ten_env.log_info("Audio processor task restarted")

            if t.request_id != self.current_request_id:
                self.ten_env.log_info(
                    f"KEYPOINT New TTS request with ID: {t.request_id}"
                )
                if not self.current_request_finished:
                    # Complete previous request (non-debug mode only)
                    if not self.config.use_debug_audio:
                        self.client.complete()
                    self.current_request_finished = True

                self.current_request_id = t.request_id
                self.current_request_finished = False
                self.total_audio_bytes = 0  # Reset for new request
                self.request_ttfb = None
                self.first_chunk = True
                self.chunk_count = 0
                self.request_start_ts = datetime.now()
                self.is_first_message_of_request = True

                # Manage PCMWriter instances for audio recording
                await self._manage_pcm_writers(t.request_id)

            elif self.current_request_finished:
                error_msg = f"Received a message for a finished request_id '{t.request_id}' with text_input_end=False."
                self.ten_env.log_error(error_msg)
                return

            # Get audio stream from Cosy TTS
            self.ten_env.log_debug(
                f"send_text_to_tts_server: {t.text} of request_id: {t.request_id}",
                category=LOG_CATEGORY_VENDOR,
            )

            if (
                self.is_first_message_of_request
                and t.text.strip() == ""
                and t.text_input_end
            ):
                self.ten_env.log_info(
                    f"KEYPOINT skip empty text, request_id: {t.request_id}"
                )
                await self._handle_tts_audio_end()
                self.current_request_id = None
                return

            # Start audio synthesis (returns immediately)
            if t.text.strip() == "":
                self.ten_env.log_info(
                    f"KEYPOINT skip empty text, request_id: {t.request_id}"
                )
            else:
                # Add output characters to metrics
                char_count = len(t.text)
                self.metrics_add_output_characters(char_count)
                self.ten_env.log_info(
                    f"KEYPOINT add output characters to metrics: {char_count}, request_id: {t.request_id}"
                )

                # Start audio synthesis
                if not self.config.use_debug_audio:
                    # Normal mode: synthesize with TTS service
                    self.client.synthesize_audio(t.text, t.text_input_end)
                else:
                    # Debug mode: activate debug audio streaming
                    self.debug_audio_active = True
                    self.debug_audio_position = 0  # Reset to start of file
                    self.ten_env.log_info(
                        f"KEYPOINT Debug mode: activated debug audio streaming for request_id: {t.request_id}"
                    )
                self.is_first_message_of_request = False

            # Handle text input end
            if t.text_input_end:
                self.ten_env.log_info(
                    f"KEYPOINT finish session for request ID: {t.request_id}, current_request_id: {self.current_request_id}"
                )
                # Complete the request (non-debug mode only)
                if not self.config.use_debug_audio:
                    self.client.complete()
                # In debug mode, keep debug audio active for continuous playback
                # Don't set current_request_finished - audio will continue until cancelled
                if not self.config.use_debug_audio:
                    self.current_request_finished = True

        except WebSocketConnectionClosedException as e:
            self.ten_env.log_error(f"WebSocket connection closed, {e}")
            await self._send_tts_error(
                str(e),
                code=ModuleErrorCode.NON_FATAL_ERROR.value,
                vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
            )
            if self.client and not self.config.use_debug_audio:
                self.client.cancel()

        except Exception as e:
            self.ten_env.log_error(
                f"Error in request_tts: {traceback.format_exc()}. text: {t.text}, current_request_id: {self.current_request_id}"
            )
            await self._send_tts_error(
                str(e),
                code=ModuleErrorCode.FATAL_ERROR.value,
                vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
            )
            if self.client and not self.config.use_debug_audio:
                self.client.cancel()

    async def _process_audio_data(self) -> None:
        """
        Independent audio data process loop.
        This runs in the background and processes audio data from the client.
        Continuously processes data stream for multiple requests.
        done=True only marks end of current request, loop continues for next request.
        Only breaks on errors, reconnection happens on next synthesize_audio call.
        """
        try:
            self.ten_env.log_info("Starting audio process loop")

            while True:  # Continuous loop for processing multiple requests
                try:
                    # Debug audio mode: use pre-loaded audio file
                    if self.config.use_debug_audio:
                        (
                            done,
                            message_type,
                            data,
                        ) = await self._get_next_debug_audio_chunk()
                    else:
                        # Normal mode: get audio data from TTS client
                        self.ten_env.log_info("Waiting for audio data from client...")
                        done, message_type, data = await self.client.get_audio_data()

                    self.ten_env.log_info(
                        f"Received done: {done}, message_type: {message_type}, current_request_id: {self.current_request_id}"
                    )

                    # Process PCM audio chunks
                    if message_type == MESSAGE_TYPE_PCM:
                        audio_chunk = data

                        if (
                            audio_chunk is not None
                            and len(audio_chunk) > 0
                            and isinstance(audio_chunk, bytes)
                        ):
                            # Add recv audio chunks to metrics
                            self.metrics_add_recv_audio_chunks(audio_chunk)
                            self.chunk_count += 1
                            self.total_audio_bytes += len(audio_chunk)
                            # Calculate audio duration for this chunk
                            chunk_duration_ms = self._calculate_audio_duration(
                                len(audio_chunk), self.config.sample_rate
                            )
                            self.ten_env.log_info(
                                f"receive_audio: duration: {chunk_duration_ms}ms, bytes: {len(audio_chunk)}, total_audio_bytes: {self.total_audio_bytes + len(audio_chunk)} of request_id: {self.current_request_id}",
                            )

                            # Send TTS audio start on first chunk
                            if self.first_chunk:
                                await self._handle_first_audio_chunk()
                                self.first_chunk = False

                            # Write to dump file if enabled
                            await self._write_audio_to_dump_file(audio_chunk)

                            # Send audio data
                            await self.send_tts_audio_data(audio_chunk)
                        else:
                            self.ten_env.log_info(
                                f"Received empty or invalid payload for TTS response, current_request_id: {self.current_request_id}"
                            )
                    elif message_type == MESSAGE_TYPE_CMD_RESULT_GENERATED:
                        if isinstance(data, int):
                            self.metrics_add_input_characters(data)
                    elif message_type == MESSAGE_TYPE_CMD_ERROR:
                        self.ten_env.log_error(
                            f"vendor_error: {data}",
                            category=LOG_CATEGORY_VENDOR,
                        )
                        await self._send_tts_error(
                            str(data),
                            code=ModuleErrorCode.NON_FATAL_ERROR.value,
                            vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
                        )

                    elif message_type == MESSAGE_TYPE_CMD_CANCEL:
                        self.ten_env.log_info(
                            f"Received cancel message from client: {data}"
                        )

                    # Handle TTS audio end - send tts_audio_end on each done=True
                    # Cosy TTS may send done=True multiple times in streaming mode
                    if done:
                        self.ten_env.log_info(
                            f"Received done=True from TTS service, sending tts_audio_end. "
                            f"current_request_id: {self.current_request_id}, "
                            f"total_audio_bytes: {self.total_audio_bytes}"
                        )
                        await self._handle_tts_audio_end()

                except asyncio.CancelledError:
                    self.ten_env.log_info("Audio consumer task was cancelled.")
                    break
                except Exception as e:
                    self.ten_env.log_error(f"Error in audio consumer loop: {e}")
                    self.ten_env.log_error(
                        "Audio consumer loop breaking due to exception"
                    )
                    # Send an error message to notify the system of the failure
                    await self._send_tts_error(
                        str(e),
                        code=ModuleErrorCode.NON_FATAL_ERROR.value,
                        vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
                    )
                    # Break loop on error, will reconnect on next synthesize_audio
                    break

        except Exception as e:
            self.ten_env.log_error(f"Fatal error in audio consumer: {e}")
            await self._send_tts_error(
                str(e),
                code=ModuleErrorCode.NON_FATAL_ERROR.value,
                vendor_info=ModuleErrorVendorInfo(vendor=self.vendor()),
            )

    def synthesize_audio_sample_rate(self) -> int:
        """
        Get the sample rate for the TTS audio.
        """
        return self.config.sample_rate

    def vendor(self) -> str:
        """
        Get the vendor name for the TTS audio.
        """
        return "cosy"

    def _calculate_ttfb_ms(self, start_time: datetime) -> int:
        """
        Calculate Time To First Byte (TTFB) in milliseconds.

        Args:
            start_time: The timestamp when the request was sent

        Returns:
            TTFB in milliseconds
        """
        return int((datetime.now() - start_time).total_seconds() * 1000)

    def _calculate_audio_duration(
        self,
        bytes_length: int,
        sample_rate: int,
        channels: int = 1,
        sample_width: int = 2,
    ) -> int:
        """
        Calculate audio duration in milliseconds.

        Parameters:
        - bytes_length: Length of the audio data in bytes
        - sample_rate: Sample rate in Hz (e.g., 16000)
        - channels: Number of audio channels (default: 1 for mono)
        - sample_width: Number of bytes per sample (default: 2 for 16-bit PCM)

        Returns:
        - Duration in milliseconds (rounded down to nearest int)
        """
        bytes_per_second = sample_rate * channels * sample_width
        duration_seconds = bytes_length / bytes_per_second
        return int(duration_seconds * 1000)

    async def _cleanup_all_pcm_writers(self) -> None:
        """
        Clean up all PCMWriter instances.
        This is typically called during shutdown or cleanup operations.
        """
        for request_id, recorder in self.recorder_map.items():
            try:
                await recorder.flush()
                self.ten_env.log_info(f"Flushed PCMWriter for request_id: {request_id}")
            except Exception as e:
                self.ten_env.log_error(
                    f"Error flushing PCMWriter for request_id {request_id}: {e}"
                )

        # Clear the recorder map
        self.recorder_map.clear()

    def _get_pcm_dump_file_path(self, request_id: str) -> str:
        """
        Get the PCM dump file path.

        Returns:
            str: The complete path of the PCM dump file
        """
        if self.config is None:
            raise ValueError(
                "Configuration not initialized, cannot get PCM dump file path"
            )

        return os.path.join(
            self.config.dump_path,
            generate_file_name(f"{self.name}_out_{request_id}"),
        )

    async def _handle_first_audio_chunk(self) -> None:
        """
        Handle the first audio chunk from TTS service.

        This method:
        1. Sends TTS audio start event
        2. Calculates and records TTFB (Time To First Byte)
        3. Sends TTFB metrics
        4. Logs the operation
        """
        if self.request_start_ts:
            await self.send_tts_audio_start(
                self.current_request_id,
            )

            self.request_ttfb = self._calculate_ttfb_ms(self.request_start_ts)
            await self.send_tts_ttfb_metrics(
                request_id=self.current_request_id,
                ttfb_ms=self.request_ttfb,
                extra_metadata={
                    "model": (self.config.model if self.config else ""),
                    "voice": (self.config.voice if self.config else ""),
                },
            )

            self.ten_env.log_info(
                f"KEYPOINT Sent TTS audio start and TTFB metrics: {self.request_ttfb}ms, current_request_id: {self.current_request_id}"
            )

    async def _handle_tts_audio_end(
        self,
        reason: TTSAudioEndReason = TTSAudioEndReason.REQUEST_END,
    ) -> None:
        """
        Handle TTS audio end processing.

        This method:
        1. Validates that request_id is not None
        2. Calculates total audio duration
        3. Calculates request event interval
        4. Sends TTS audio end event
        5. Logs the operation

        Note: Skips sending if request_id is None (e.g., after cancellation)
        """
        # ✅ FIX: Skip sending if request_id is None
        if not self.current_request_id:
            self.ten_env.log_info(
                f"[tts] Skipping tts_audio_end with None request_id, reason: {reason}"
            )
            return

        if self.request_start_ts:
            self.request_total_audio_duration_ms = self._calculate_audio_duration(
                self.total_audio_bytes, self.config.sample_rate
            )
            request_event_interval = int(
                (datetime.now() - self.request_start_ts).total_seconds() * 1000
            )

            # Send TTS audio end event
            await self.send_tts_audio_end(
                request_id=self.current_request_id,
                request_event_interval_ms=request_event_interval,
                request_total_audio_duration_ms=self.request_total_audio_duration_ms,
                reason=reason,
            )
            # Send usage metrics
            await self.send_usage_metrics(self.current_request_id)

            self.ten_env.log_info(
                f"KEYPOINT Sent TTS audio end event, interval: {request_event_interval}ms, duration: {self.request_total_audio_duration_ms}ms (total_audio_bytes: {self.total_audio_bytes}), request_id: {self.current_request_id}"
            )

            # Don't clear current_request_id here - it will be cleared on next new request

    async def _manage_pcm_writers(self, request_id: str) -> None:
        """
        Manage PCMWriter instances for audio recording.
        Creates new PCMWriter for current request and cleans up old ones.

        Args:
            request_id: Current request ID to keep active
        """
        if not self.config or not self.config.dump:
            return

        # Clean up old PCMWriters (except current request_id)
        old_request_ids = [rid for rid in self.recorder_map.keys() if rid != request_id]

        for old_rid in old_request_ids:
            try:
                await self.recorder_map[old_rid].flush()
                del self.recorder_map[old_rid]
                self.ten_env.log_info(
                    f"Cleaned up old PCMWriter for request_id: {old_rid}"
                )
            except Exception as e:
                self.ten_env.log_error(
                    f"Error cleaning up PCMWriter for request_id {old_rid}: {e}"
                )

        # Create new PCMWriter if needed
        if request_id not in self.recorder_map:
            dump_file_path = self._get_pcm_dump_file_path(request_id)
            self.recorder_map[request_id] = PCMWriter(dump_file_path)
            self.ten_env.log_info(
                f"Created PCMWriter for request_id: {request_id}, file: {dump_file_path}"
            )

    async def _send_tts_error(
        self,
        message: str,
        vendor_code: str | None = None,
        vendor_message: str | None = None,
        vendor_info: ModuleErrorVendorInfo | None = None,
        code: int = ModuleErrorCode.FATAL_ERROR.value,
        request_id: str | None = None,
    ) -> None:
        """
        Send a TTS error message.
        """
        if vendor_code is not None:
            vendor_info = ModuleErrorVendorInfo(
                vendor=self.vendor(),
                code=vendor_code,
                message=vendor_message or "",
            )

        await self.send_tts_error(
            request_id or self.current_request_id,
            ModuleError(
                message=message,
                module=ModuleType.TTS,
                code=code,
                vendor_info=vendor_info,
            ),
        )

    async def _get_voice_from_employee_api(
        self, employee_id: str, ten_env: AsyncTenEnv
    ) -> str:
        """从员工API获取gender和tone，组合成voice值"""
        api_base_url = os.getenv("EMPLOYEE_API_BASE_URL", "http://192.168.8.234:8100")
        url = f"{api_base_url}/api/employee/detail/{employee_id}"
        default_voice = "hutao"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers={"Accept": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("code") == 200 and "data" in data:
                            employee_data = data["data"]
                            gender = employee_data.get("gender")
                            tone = employee_data.get("tone")

                            # 检查 gender 和 tone 是否有效
                            if gender is not None and tone:
                                voice = f"{gender}_{tone}"
                                ten_env.log_info(f"Generated voice from API: {voice}")
                                return voice

            ten_env.log_info(
                f"Invalid or missing gender/tone, using default voice: {default_voice}"
            )
            return default_voice
        except Exception as e:
            ten_env.log_error(
                f"Failed to fetch employee data: {e}, using default voice: {default_voice}"
            )
            return default_voice

    async def _write_audio_to_dump_file(self, audio_chunk: bytes) -> None:
        """
        Write audio chunk to dump file if enabled.
        """
        if (
            self.config
            and self.config.dump
            and self.current_request_id
            and self.current_request_id in self.recorder_map
        ):
            self.ten_env.log_info(
                f"KEYPOINT Writing audio chunk to dump file, dump path: {self.config.dump_path}, request_id: {self.current_request_id}"
            )
            asyncio.create_task(
                self.recorder_map[self.current_request_id].write(audio_chunk)
            )

    async def _load_debug_audio(self) -> None:
        """
        Load debug audio from file for testing without TTS service.
        Supports both WAV and raw PCM formats.
        """
        try:
            import wave

            self.ten_env.log_info(
                f"Attempting to load debug audio from: {self.config.debug_audio_path}"
            )

            # Try to open as WAV file first
            try:
                with wave.open(self.config.debug_audio_path, "rb") as wav_file:
                    # Get audio parameters
                    frames = wav_file.getnframes()
                    self.ten_env.log_info(
                        f"WAV file info - channels: {wav_file.getnchannels()}, "
                        f"sample_rate: {wav_file.getframerate()}, "
                        f"frames: {frames}, "
                        f"sample_width: {wav_file.getsampwidth()}"
                    )

                    # Read all frames and convert to bytes
                    self.debug_audio_data = wav_file.readframes(frames)
                    self.ten_env.log_info(
                        f"Loaded debug audio (WAV): {len(self.debug_audio_data)} bytes from {self.config.debug_audio_path}"
                    )
            except wave.Error:
                # Not a WAV file, treat as raw PCM
                with open(self.config.debug_audio_path, "rb") as f:
                    self.debug_audio_data = f.read()
                self.ten_env.log_info(
                    f"Loaded debug audio (raw PCM): {len(self.debug_audio_data)} bytes from {self.config.debug_audio_path}"
                )

            self.debug_audio_position = 0

        except FileNotFoundError as e:
            self.ten_env.log_error(
                f"Debug audio file not found: {self.config.debug_audio_path}, error: {e}"
            )
            raise ValueError(
                f"Debug audio file not found: {self.config.debug_audio_path}"
            )
        except Exception as e:
            self.ten_env.log_error(
                f"Failed to load debug audio: {e}, traceback: {traceback.format_exc()}"
            )
            raise ValueError(f"Failed to load debug audio: {e}")

    async def _get_next_debug_audio_chunk(self) -> tuple[bool, int, bytes | None]:
        """
        Get next chunk of debug audio data. Loops when reaching end of file.

        Returns:
            (done, message_type, data) tuple
            - done: Always False (debug audio loops until explicitly stopped)
            - message_type: MESSAGE_TYPE_PCM
            - data: Audio chunk bytes or None if debug audio is not active
        """
        # In debug mode, check if debug audio is active (has a request)
        if not self.debug_audio_active:
            await asyncio.sleep(0.05)  # Small delay to prevent busy waiting
            return (False, MESSAGE_TYPE_PCM, None)

        # If debug audio data is empty, return None
        if not self.debug_audio_data:
            await asyncio.sleep(0.05)
            return (False, MESSAGE_TYPE_PCM, None)

        # Get chunk based on current position
        chunk = self.debug_audio_data[
            self.debug_audio_position : self.debug_audio_position
            + self.debug_audio_chunk_size
        ]

        # Update position with wraparound
        self.debug_audio_position = (self.debug_audio_position + len(chunk)) % len(
            self.debug_audio_data
        )

        # Small delay to simulate real-time audio streaming
        # 100ms = 0.1 second for 3200 bytes at 16kHz
        await asyncio.sleep(0.1)

        return (False, MESSAGE_TYPE_PCM, chunk)
