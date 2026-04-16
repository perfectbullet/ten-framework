from datetime import datetime
import os
import asyncio

from typing_extensions import override
from .const import (
    DUMP_FILE_NAME,
    MODULE_NAME_ASR,
)
from ten_ai_base.asr import (
    ASRBufferConfig,
    ASRBufferConfigModeDiscard,
    ASRResult,
    AsyncASRBaseExtension,
)
from ten_ai_base.message import (
    ModuleError,
    ModuleErrorVendorInfo,
    ModuleErrorCode,
)
from ten_runtime import (
    AsyncTenEnv,
    AudioFrame,
    Data
)
from ten_ai_base.const import (
    LOG_CATEGORY_VENDOR,
    LOG_CATEGORY_KEY_POINT,
)

from ten_ai_base.dumper import Dumper
from .reconnect_manager import ReconnectManager
from .config import AliyunASRBigmodelConfig

# FunASR (local server) imports
from .funasr_adapter import (
    FunASRRecognition,
    FunASRRecognitionCallback,
    FunASRRecognitionResult,
)


class FunASRCallback(FunASRRecognitionCallback):
    """FunASR 回调处理类，桥接到扩展的异步事件循环"""

    def __init__(self, extension: "AliyunASRBigmodelExtension"):
        super().__init__()
        self.extension = extension
        self.ten_env = extension.ten_env
        self.loop = asyncio.get_event_loop()

    def on_open(self) -> None:
        """Callback when connection is established"""
        self.ten_env.log_info(
            "FunASR connection opened",
            category=LOG_CATEGORY_VENDOR,
        )
        asyncio.run_coroutine_threadsafe(
            self.extension.on_asr_open(), self.loop
        )

    def on_complete(self) -> None:
        """Callback when recognition is completed"""
        asyncio.run_coroutine_threadsafe(
            self.extension.on_asr_complete(), self.loop
        )

    def on_error(self, result: FunASRRecognitionResult) -> None:
        """Error handling callback"""
        self.ten_env.log_error(
            f"FunASR error: {result.message}",
            category=LOG_CATEGORY_VENDOR,
        )
        asyncio.run_coroutine_threadsafe(
            self.extension.on_asr_error(result), self.loop
        )

    def on_event(self, result: FunASRRecognitionResult) -> None:
        """Recognition result event callback"""
        self.ten_env.log_debug(f"FunASR result event: {result}")
        asyncio.run_coroutine_threadsafe(
            self.extension.on_asr_event(result), self.loop
        )

    def on_close(self) -> None:
        """Callback when connection is closed"""
        self.ten_env.log_info(
            "FunASR connection closed",
            category=LOG_CATEGORY_VENDOR,
        )
        asyncio.run_coroutine_threadsafe(
            self.extension.on_asr_close(), self.loop
        )


class AliyunASRBigmodelExtension(AsyncASRBaseExtension):
    """Aliyun ASR Big Model Extension"""

    def __init__(self, name: str):
        super().__init__(name)
        self.connected: bool = False
        self.recognition: FunASRRecognition | None = None
        self.config: AliyunASRBigmodelConfig | None = None
        self.audio_dumper: Dumper | None = None
        self.sent_user_audio_duration_ms_before_last_reset: int = 0
        self.last_finalize_timestamp: int = 0

        # Reconnection manager
        self.reconnect_manager: ReconnectManager | None = None

        # Callback instance
        self.recognition_callback: FunASRCallback | None = None

        # Flag to track if connection close is expected (e.g., after finalize)
        self._closing_intentionally: bool = False

    @override
    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(ten_env)
        ten_env.log_info("Deinitializing Aliyun ASR Bigmodel Extension")
        if self.audio_dumper:
            await self.audio_dumper.stop()
            self.audio_dumper = None

    @override
    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        """Handle incoming data"""
        data_name = data.get_name()
        ten_env.log_info(f"asr on_data: data_name {data_name}")
        # Handle end_of_audio message from test
        if data_name == "end_of_audio":
            self.ten_env.log_info("Received end_of_audio, calling finalize")
            await self.finalize(session_id=None)
            return
        # Call parent's on_data for other messages
        await super().on_data(ten_env, data)

    @override
    def vendor(self) -> str:
        """获取 ASR 厂商名称"""
        return "funasr_local"

    @override
    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        await super().on_init(ten_env)

        # Initialize reconnection manager
        self.reconnect_manager = ReconnectManager(logger=ten_env)

        config_json, _ = await ten_env.get_property_to_json("")

        try:
            temp_config = AliyunASRBigmodelConfig.model_validate_json(
                config_json
            )

            self.config = temp_config
            self.config.update(self.config.params)
            ten_env.log_info(
                f"FunASR ASR config: {self.config.to_json()}",
                category=LOG_CATEGORY_KEY_POINT,
            )

            if self.config.dump:
                dump_file_path = os.path.join(
                    self.config.dump_path, DUMP_FILE_NAME
                )
                self.audio_dumper = Dumper(dump_file_path)

        except Exception as e:
            ten_env.log_error(f"Invalid FunASR ASR config: {e}")
            self.config = AliyunASRBigmodelConfig.model_validate_json("{}")
            await self.send_asr_error(
                ModuleError(
                    module=MODULE_NAME_ASR,
                    code=ModuleErrorCode.FATAL_ERROR.value,
                    message=str(e),
                ),
            )

    @override
    async def start_connection(self) -> None:
        """启动 FunASR ASR 连接"""
        assert self.config is not None

        try:
            await self.stop_connection()

            if self.audio_dumper:
                await self.audio_dumper.start()

            await self._start_funasr_connection()

            self.ten_env.log_info("FunASR ASR connection started successfully")

        except Exception as e:
            self.ten_env.log_error(
                f"Failed to start FunASR connection: {e}"
            )
            await self.send_asr_error(
                ModuleError(
                    module=MODULE_NAME_ASR,
                    code=ModuleErrorCode.FATAL_ERROR.value,
                    message=str(e),
                ),
            )

    async def _start_funasr_connection(self) -> None:
        """启动 FunASR WebSocket ASR 连接"""
        self.recognition_callback = FunASRCallback(self)

        self.recognition = FunASRRecognition(
            host=self.config.funasr_host,
            port=self.config.funasr_port,
            is_ssl=self.config.funasr_is_ssl,
            chunk_size=self.config.funasr_chunk_size,
            chunk_interval=self.config.funasr_chunk_interval,
            mode=self.config.funasr_mode,
            wav_name="default",
            callback=self.recognition_callback,
            sample_rate=self.config.sample_rate,
            format="pcm",
            language_hints=self.config.language_hints,
            hotwords=self.config.funasr_hotwords,
            itn=self.config.funasr_itn,
        )

        self.recognition.start()

    async def on_asr_open(self) -> None:
        """Handle callback when connection is established"""
        self.ten_env.log_info("FunASR ASR connection opened")
        self.connected = True
        # Reset timeline and audio duration
        self.sent_user_audio_duration_ms_before_last_reset += (
            self.audio_timeline.get_total_user_audio_duration()
        )
        self.audio_timeline.reset()

    async def on_asr_complete(self) -> None:
        """Handle callback when recognition is completed"""
        self.ten_env.log_info("FunASR ASR recognition completed")

    async def on_asr_error(self, result: FunASRRecognitionResult) -> None:
        """Handle error callback"""
        self.ten_env.log_error(f"FunASR ASR error: {result.message}")
        # Send error information
        await self.send_asr_error(
            ModuleError(
                module=MODULE_NAME_ASR,
                code=ModuleErrorCode.NON_FATAL_ERROR.value,
                message=result.message,
            ),
            ModuleErrorVendorInfo(
                vendor=self.vendor(),
                code=(
                    str(result.status_code)
                    if hasattr(result, "status_code")
                    else "unknown"
                ),
                message=result.message,
            ),
        )

    async def on_asr_event(self, result: FunASRRecognitionResult) -> None:
        """处理识别结果事件回调"""
        try:
            # 通知重连管理器连接成功
            if self.reconnect_manager and self.connected:
                self.reconnect_manager.mark_connection_successful()

            self.ten_env.log_debug(
                f"FunASR result: {result}",
                category=LOG_CATEGORY_VENDOR,
            )

            sentence = result.get_sentence()
            if isinstance(sentence, dict) and "text" in sentence and sentence["text"]:
                text = sentence["text"]
                is_final = FunASRRecognitionResult.is_sentence_end(sentence)

                # 从 stamp_sents 提取时间戳（仅最终结果有此字段）
                start_ms = int(sentence.get("begin_time", 0) or 0)
                end_ms = int(sentence.get("end_time", 0) or 0)

                # 如果有词级时间戳，从最后一个词获取结束时间
                if end_ms == 0 and "words" in sentence and sentence["words"]:
                    last_word = sentence["words"][-1]
                    if "end_time" in last_word and last_word["end_time"]:
                        end_ms = int(last_word["end_time"])
                        self.ten_env.log_debug(
                            f"Using last word end_time: {end_ms} as sentence end_time"
                        )

                duration_ms = end_ms - start_ms if end_ms > start_ms else 0

                # 计算实际起始时间（映射到全局时间轴）
                if start_ms > 0:
                    actual_start_ms = int(
                        self.audio_timeline.get_audio_duration_before_time(start_ms)
                        + self.sent_user_audio_duration_ms_before_last_reset
                    )
                else:
                    actual_start_ms = 0

                self.ten_env.log_debug(
                    f"FunASR result: {text}, is_final: {is_final}, "
                    f"start_ms: {actual_start_ms}, duration_ms: {duration_ms}"
                )

                # 处理 ASR 结果
                if self.config is not None:
                    await self._handle_asr_result(
                        text=text,
                        final=is_final,
                        start_ms=actual_start_ms,
                        duration_ms=duration_ms,
                        language=self.config.normalized_language,
                    )
                else:
                    self.ten_env.log_error(
                        "Cannot handle ASR result: config is None"
                    )

        except Exception as e:
            self.ten_env.log_error(f"Error processing FunASR result: {e}")

    async def on_asr_close(self) -> None:
        """Handle callback when connection is closed"""
        self.ten_env.log_debug("FunASR ASR connection closed")
        self.connected = False

        # Only reconnect if this was an unexpected close (not intentional)
        if not self._closing_intentionally and not self.stopped:
            self.ten_env.log_warn(
                "FunASR ASR connection closed unexpectedly. Reconnecting..."
            )
            await self._handle_reconnect()
        else:
            # Reset the intentional close flag for next connection
            self._closing_intentionally = False

    @override
    async def finalize(self, session_id: str | None) -> None:
        """Finalize recognition"""
        assert self.config is not None

        self.last_finalize_timestamp = int(datetime.now().timestamp() * 1000)
        self.ten_env.log_info(
            f"FunASR finalize start at {self.last_finalize_timestamp}",
            category=LOG_CATEGORY_VENDOR,
        )

        # FunASR uses send_audio_frame with is_speaking: false to finalize
        await self._handle_finalize_funasr()

    def _clean_leading_punctuation(self, text: str) -> str:
        """Remove leading punctuation from ASR result text."""
        # Common Chinese and English punctuation marks at the beginning
        leading_punct = '，,。.！!？?；;：:、\t\n\r '
        while text and text[0] in leading_punct:
            text = text[1:]
        return text

    async def _handle_asr_result(
        self,
        text: str,
        final: bool,
        start_ms: int = 0,
        duration_ms: int = 0,
        language: str = "",
    ):
        """Process ASR recognition result"""
        assert self.config is not None

        # Clean leading punctuation from ASR result
        text = self._clean_leading_punctuation(text)

        if final:
            await self._finalize_end()

        asr_result = ASRResult(
            text=text,
            final=final,
            start_ms=start_ms,
            duration_ms=duration_ms,
            language=language,
            words=[],
        )

        await self.send_asr_result(asr_result)

    async def _handle_finalize_funasr(self):
        """Handle FunASR finalization by sending is_speaking: false"""
        if self.recognition and self.recognition.is_running():
            self.ten_env.log_debug("FunASR finalize: waiting for queue to drain before sending stop")
            self.ten_env.log_debug("FunASR finalize: sending is_speaking: false")
            # Set flag to indicate intentional close, so on_asr_close won't try to reconnect
            self._closing_intentionally = True
            # 发送结束标记
            self.recognition.stop()
        else:
            self.ten_env.log_debug("FunASR finalize: recognition not running")

    async def _handle_reconnect(self):
        """Handle reconnection"""
        if not self.reconnect_manager:
            self.ten_env.log_error("ReconnectManager not initialized")
            return

        # Check if retry is still possible
        if not self.reconnect_manager.can_retry():
            self.ten_env.log_warn("No more reconnection attempts allowed")
            await self.send_asr_error(
                ModuleError(
                    module=MODULE_NAME_ASR,
                    code=ModuleErrorCode.FATAL_ERROR.value,
                    message="No more reconnection attempts allowed",
                )
            )
            return

        # Attempt reconnection
        success = await self.reconnect_manager.handle_reconnect(
            connection_func=self.start_connection,
            error_handler=self.send_asr_error,
        )

        if success:
            self.ten_env.log_debug(
                "Reconnection attempt initiated successfully"
            )
        else:
            info = self.reconnect_manager.get_attempts_info()
            self.ten_env.log_debug(
                f"Reconnection attempt failed. Status: {info}"
            )

    async def _finalize_end(self) -> None:
        """Handle finalization end logic"""
        if self.last_finalize_timestamp != 0:
            timestamp = int(datetime.now().timestamp() * 1000)
            latency = timestamp - self.last_finalize_timestamp
            self.ten_env.log_debug(
                f"FunASR finalize end at {timestamp}, latency: {latency}ms"
            )
            self.last_finalize_timestamp = 0
            await self.send_asr_finalize_end()

    async def stop_connection(self) -> None:
        """Stop ASR connection"""
        try:
            if self.recognition:
                self.recognition.stop()
                self.recognition = None

            self.recognition_callback = None
            self.connected = False
            self.ten_env.log_info("FunASR ASR connection stopped")

        except Exception as e:
            self.ten_env.log_error(f"Error stopping FunASR connection: {e}")

    @override
    def is_connected(self) -> bool:
        """Check connection status"""
        is_connected = self.connected and self.recognition is not None
        # self.ten_env.log_debug(f"Aliyun ASR is_connected: {is_connected}")
        return is_connected

    @override
    def buffer_strategy(self) -> ASRBufferConfig:
        """Buffer strategy configuration"""
        return ASRBufferConfigModeDiscard()

    @override
    def input_audio_sample_rate(self) -> int:
        """Input audio sample rate"""
        assert self.config is not None
        return self.config.sample_rate

    @override
    async def send_audio(
        self, frame: AudioFrame, session_id: str | None
    ) -> bool:
        """Send audio data"""
        assert self.config is not None

        if not self.recognition or not self.connected:
            return False

        buf = None
        try:
            buf = frame.lock_buf()
            audio_data = bytes(buf)

            # Dump audio data
            if self.audio_dumper:
                await self.audio_dumper.push_bytes(audio_data)

            # Update timeline
            self.audio_timeline.add_user_audio(
                int(len(audio_data) / (self.config.sample_rate / 1000 * 2))
            )

            # Send audio data to FunASR recognition service
            try:
                self.recognition.send_audio_frame(audio_data)
            except Exception as e:
                # 如果是 WebSocket 已关闭相关的错误，静默处理
                error_msg = str(e)
                if "WebSocket" in error_msg or "closed" in error_msg.lower() or "not running" in error_msg.lower():
                    self.ten_env.log_debug("WebSocket closed, discarding audio frame")
                else:
                    self.ten_env.log_error(f"Error in send_audio_frame: {e}")
                return False

            frame.unlock_buf(buf)
            return True

        except Exception as e:
            self.ten_env.log_error(f"Error sending audio to FunASR: {e}")
            if buf is not None:
                frame.unlock_buf(buf)
            return False
