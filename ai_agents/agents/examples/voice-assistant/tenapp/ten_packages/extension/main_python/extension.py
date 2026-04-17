import asyncio
import json
import os
import re
import string
import time
from typing import Literal

from .agent.decorators import agent_event_handler
from ten_runtime import (
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
    Data,
)

from .agent.agent import Agent
from .agent.text_intent_validator import TextIntentValidator
from .agent.events import (
    ASRResultEvent,
    LLMResponseEvent,
    ToolRegisterEvent,
    UserJoinedEvent,
    UserLeftEvent,
)
from .helper import _send_cmd, _send_data
from .sentence_buffer import SentenceBuffer
from .config import MainControlConfig  # assume extracted from your base model

import uuid

# 是否支持打断短语
ENABLE_INTERRUPT_PHRASE  = False

def _truncate_text(text: str, max_len: int = 50) -> str:
    """截断文本用于日志显示，保留开头和结尾"""
    if len(text) <= max_len:
        return text
    half_len = (max_len - 3) // 2
    return f"{text[:half_len]}...{text[-half_len:]}"


class MainControlExtension(AsyncExtension):
    """
    The entry point of the agent module.
    Consumes semantic AgentEvents from the Agent class and drives the runtime behavior.
    """

    def __init__(self, name: str):
        super().__init__(name)
        self.ten_env: AsyncTenEnv = None
        self.agent: Agent = None
        self.config: MainControlConfig = None
        self.text_intent_validator: TextIntentValidator = None

        self.stopped: bool = False
        self._rtc_user_count: int = 0
        # SentenceBuffer: max_length=60字, max_time=0.8秒
        self.sentence_buffer = SentenceBuffer(max_length=60, max_time=0.8)
        self.turn_id: int = 0
        self.session_id: str = "0"

        # 打断短语列表 - 这些短语会触发打断但不发送给 LLM
        # 注意：避免使用容易误触发的短语如单独的"好的"、"等一下"、"稍等一下"
        self._interrupt_phrases = {
            "打断一下", "停一下", "别说了",
            "stop", "wait", "hold on",
        }

        # Track last processed interrupt timestamp to avoid duplicate processing
        self._last_interrupt_timestamp: int = 0

        # 状态标志：用于感知当前系统状态
        self.is_llm_streaming: bool = False  # LLM 是否正在流式输出
        # tts_audio_start_time 作为音频开始播放时间（在第一个 tts_audio_end 时校正）
        self.tts_audio_start_time: float = 0.0
        # 累计音频时长：所有已生成音频的总时长
        self.accumulated_audio_duration_ms: int = 0
        # 标记是否已校正过 tts_audio_start_time（避免重复校正）
        self._tts_start_time_calibrated: bool = False

    def _current_metadata(self) -> dict:
        return {"session_id": self.session_id, "turn_id": self.turn_id}

    def _is_interrupt_phrase(self, text: str) -> bool:
        """
        检查文本是否是打断短语。
        处理前后标点符号，如 "，打断一下" 或 "打断一下。"
        也支持重复字符，如 "停停停"、"等等等"
        """
        # 去除前后标点符号后检查
        text_clean = text.strip().strip(string.punctuation + "，。！？、；：""''《》【】")
        text_lower = text_clean.lower()

        # 检查是否包含打断短语（只检查短语是否在输入文本中）
        for phrase in self._interrupt_phrases:
            if phrase.lower() in text_lower:
                return True

        # 检查重复的打断意图字符（如：停停停、等等等、别别别、stopstop）
        # 匹配单个汉字重复3次及以上
        if re.match(r'^([停等别])\1{2,}$', text_clean):
            return True
        # 匹配英文单词重复2次及以上（如：stopstop）
        if re.match(r'^([a-z]+)\1{1,}$', text_lower):
            return True

        return False

    async def on_init(self, ten_env: AsyncTenEnv):
        self.ten_env = ten_env

        # Load config from runtime properties
        config_json, _ = await ten_env.get_property_to_json(None)
        self.config = MainControlConfig.model_validate_json(config_json)

        self.agent = Agent(ten_env)

        # Initialize TextIntentValidator with default configuration
        self.text_intent_validator = TextIntentValidator()
        ten_env.log_info(
            "[MainControlExtension] TextIntentValidator initialized"
        )

        # Now auto-register decorated methods
        for attr_name in dir(self):
            fn = getattr(self, attr_name)
            event_type = getattr(fn, "_agent_event_type", None)
            if event_type:
                self.agent.on(event_type, fn)

    # === Register handlers with decorators ===
    @agent_event_handler(UserJoinedEvent)
    async def _on_user_joined(self, event: UserJoinedEvent):
        self._rtc_user_count += 1
        if self._rtc_user_count == 1 and self.config and self.config.greeting:
            await self._send_to_tts(self.config.greeting, True)
            await self._send_transcript(
                "assistant", self.config.greeting, True, 100
            )

    @agent_event_handler(UserLeftEvent)
    async def _on_user_left(self, event: UserLeftEvent):
        self._rtc_user_count -= 1

    @agent_event_handler(ToolRegisterEvent)
    async def _on_tool_register(self, event: ToolRegisterEvent):
        await self.agent.register_llm_tool(event.tool, event.source)

    @agent_event_handler(ASRResultEvent)
    async def _on_asr_result(self, event: ASRResultEvent):
        # 使用累计时长计算是否忙碌
        is_tts_busy = (self.accumulated_audio_duration_ms > 0 and
                       time.time() < (self.tts_audio_start_time +
                                       self.accumulated_audio_duration_ms / 1000.0))
        # 打印当前状态
        self.ten_env.log_info(
            f"[MainControlExtension] Current state: "
            f"LLM streaming={self.is_llm_streaming}, "
            f"TTS busy={is_tts_busy}, "
            f"accumulated_duration={self.accumulated_audio_duration_ms}ms"
            f"ASR result: text='{event.text}'"
            f"event.final={event.final}"
        )
        self.session_id = event.metadata.get("session_id", "100")
        stream_id = int(self.session_id)
        if not event.text or not event.final:
            return

        # 检查是否是打断短语（在语义验证之前）
        if ENABLE_INTERRUPT_PHRASE and self._is_interrupt_phrase(event.text):
            self.ten_env.log_info(
                f"[MainControlExtension] Interrupt phrase detected: '{_truncate_text(event.text)}', calling _interrupt()"
            )
            await self._interrupt()
            return  # 不发送给 LLM

        # 检查 TTS 或 LLM 是否忙碌（在播报期间不处理新的 ASR 结果）
        if is_tts_busy or self.is_llm_streaming:
            self.ten_env.log_info(
                "[MainControlExtension] Skipping ASR result: TTS/LLM is busy"
            )
            return

        # Semantic validation using TextIntentValidator (only on final results)
        corrected_text = None
        if self.text_intent_validator:
            is_meaningful, elapsed, _, corrected_text = await self.text_intent_validator.is_meaningful(event.text)
            self.ten_env.log_info(
                f"[MainControlExtension] TextIntentValidator: "
                f"original='{_truncate_text(event.text)}', "
                f"corrected='{_truncate_text(corrected_text) if corrected_text else 'N/A'}', "
                f"is_meaningful={is_meaningful}, elapsed={elapsed:.3f}s"
            )
            if not is_meaningful:
                self.ten_env.log_info(
                    f"[MainControlExtension] Skipping noise text: '{_truncate_text(event.text)}'"
                )
                return
        self.ten_env.log_info(f"[MainControlExtension] text_len={len(event.text)}")
        if len(event.text) > 4:
            await self._interrupt()
            self.turn_id += 1
            # Use corrected text for LLM if available
            llm_text = corrected_text if corrected_text else event.text
            await self.agent.queue_llm_input(llm_text)
            # 只在有意义文本且已打断后发送转录
            await self._send_transcript("user", event.text, event.final, stream_id)

    @agent_event_handler(LLMResponseEvent)
    async def _on_llm_response(self, event: LLMResponseEvent):
        self.ten_env.log_info(f"[MainControlExtension] _on_llm_response event.type={event.type}")

        # 流式输出开始
        if not event.is_final and event.type == "message":
            self.is_llm_streaming = True
            # 注意：不在这里初始化播放完成时间，将在 tts_audio_start 时记录开始时间

            sentences = self.sentence_buffer.feed(event.delta)
            for s in sentences:
                await self._send_to_tts(s, False)

        # 流式输出结束
        if event.is_final and event.type == "message":
            self.is_llm_streaming = False
            # 注意：不在这里设置播放完成时间，因为 TTS 音频输出是异步的
            remaining_text = self.sentence_buffer.flush()
            await self._send_to_tts(remaining_text, True)

        await self._send_transcript(
            "assistant",
            event.text,
            event.is_final,
            100,
            data_type=("reasoning" if event.type == "reasoning" else "text"),
        )

    async def on_start(self, ten_env: AsyncTenEnv):
        ten_env.log_info("[MainControlExtension] on_start")

        # 启动定期检查 interrupt 标记的后台任务
        asyncio.create_task(self._periodic_check_interrupt())

    async def on_stop(self, ten_env: AsyncTenEnv):
        ten_env.log_info("[MainControlExtension] on_stop")
        self.stopped = True
        await self.agent.stop()
        if self.text_intent_validator:
            await self.text_intent_validator.close()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd):
        cmd_name = cmd.get_name()
        self.ten_env.log_info(f"[MainControlExtension] on_cmd received: {cmd_name}")

        # Handle interrupt command directly
        if cmd_name == "interrupt":
            ten_env.log_info("[MainControlExtension] Received interrupt command")
            await self._interrupt()
            return

        # Handle end_of_sentence command from VAD - send asr_finalize to ASR
        if cmd_name == "end_of_sentence":
            ten_env.log_info("[MainControlExtension] Received end_of_sentence, sending asr_finalize to ASR")
            # Create asr_finalize data
            asr_finalize_data = Data.create("asr_finalize")
            asr_finalize_data.set_property_string("finalize_id", f"vad_{int(time.time() * 1000)}")
            await ten_env.send_data(asr_finalize_data)
            return

        # Handle start_of_sentence command from VAD
        if cmd_name == "start_of_sentence":
            ten_env.log_info("[MainControlExtension] Received start_of_sentence")
            return

        # Delegate other commands to agent
        await self.agent.on_cmd(cmd)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data):
        data_name = data.get_name()
        self.ten_env.log_info(f"[MainControlExtension] on_data received: {data_name}")

        # 处理 TTS 音频开始事件
        if data_name == "tts_audio_start":
            request_id, _ = data.get_property_string("request_id")
            # 新的 TTS 请求开始，重置状态
            self.tts_audio_start_time = 0.0  # 将在第一个 tts_audio_end 时校正
            self.accumulated_audio_duration_ms = 0
            self._tts_start_time_calibrated = False
            self.ten_env.log_info(
                f"[MainControlExtension] TTS audio started: request_id={request_id}, "
                f"will calibrate start_time on first audio_end"
            )
        # 处理 TTS 音频结束事件
        elif data_name == "tts_audio_end":
            request_id, _ = data.get_property_string("request_id")
            duration_ms, _ = data.get_property_int("request_total_audio_duration_ms")
            reason, _ = data.get_property_int("reason")

            # 只累加正常完成的音频（reason=1 是 REQUEST_END）
            # reason=2 是 INTERRUPTED，不应该累加
            if reason == 1:
                self.accumulated_audio_duration_ms = duration_ms
                # 第一次收到正常完成的音频时，校正 tts_audio_start_time
                # 这样计算出的播放结束时间更准确
                if not self._tts_start_time_calibrated:
                    self.tts_audio_start_time = time.time() - (duration_ms / 1000.0)
                    self._tts_start_time_calibrated = True
                    self.ten_env.log_info(
                        f"[MainControlExtension] Calibrated tts_audio_start_time to {self.tts_audio_start_time:.2f} "
                        f"(based on first audio_end with duration={duration_ms}ms)"
                    )

            self.ten_env.log_info(
                f"[MainControlExtension] TTS audio ended: request_id={request_id}, "
                f"duration_ms={duration_ms}, reason={reason}, "
                f"accumulated={self.accumulated_audio_duration_ms}ms"
            )
        # 处理 TTS 刷新结束事件（打断时触发）
        elif data_name == "tts_flush_end":
            # 打断时清空累计时长和校准标记，表示没有待播放音频
            self.accumulated_audio_duration_ms = 0
            self._tts_start_time_calibrated = False
            # 保持 tts_audio_start_time 不变
            self.ten_env.log_info("[MainControlExtension] TTS flush ended - cleared accumulated duration")

        # 其他数据事件（非 TTS 事件）传递给 agent 处理
        elif data_name != "tts_audio_start" and data_name != "tts_audio_end" and data_name != "tts_flush_end":
            self.ten_env.log_info(f"[MainControlExtension] not a tts event on_data received: {data_name}")
            await self.agent.on_data(data)

    # === helpers ===
    async def _send_transcript(
        self,
        role: str,
        text: str,
        final: bool,
        stream_id: int,
        data_type: Literal["text", "reasoning"] = "text",
    ):
        """
        Sends the transcript (ASR or LLM output) to the message collector.
        """
        if data_type == "text":
            await _send_data(
                self.ten_env,
                "message",
                "message_collector",
                {
                    "data_type": "transcribe",
                    "role": role,
                    "text": text,
                    "text_ts": int(time.time() * 1000),
                    "is_final": final,
                    "stream_id": stream_id,
                },
            )
        elif data_type == "reasoning":
            # 应该
            await _send_data(
                self.ten_env,
                "message",
                "message_collector",
                {
                    "data_type": "raw",
                    "role": role,
                    "text": json.dumps(
                        {
                            "type": "reasoning",
                            "data": {
                                "text": text,
                            },
                        }
                    ),
                    "text_ts": int(time.time() * 1000),
                    "is_final": final,
                    "stream_id": stream_id,
                },
            )
        self.ten_env.log_info(
            f"[MainControlExtension] Sent transcript: {role}, final={final}, text={_truncate_text(text)}"
        )

    async def _send_to_tts(self, text: str, is_final: bool):
        """
        Sends a sentence to the TTS system.
        """
        request_id = f"tts-request-{self.turn_id}"
        await _send_data(
            self.ten_env,
            "tts_text_input",
            "tts",
            {
                "request_id": request_id,
                "text": text,
                "text_input_end": is_final,
                "metadata": self._current_metadata(),
            },
        )
        self.ten_env.log_info(
            f"[MainControlExtension] Sent to TTS: is_final={is_final}, text={_truncate_text(text)}"
        )

    async def _interrupt(self):
        """
        中断正在进行的大语言模型（LLM）和语音合成（TTS）生成过程。
        该操作通常在检测到用户语音时触发。
        """
        # 打断时清空累计时长和校准标记
        self.accumulated_audio_duration_ms = 0
        self._tts_start_time_calibrated = False
        # 保持 tts_audio_start_time 不变

        await self.agent.flush_llm()
        await _send_data(
            self.ten_env, "tts_flush", "tts", {"flush_id": str(uuid.uuid4())}
        )
        await _send_cmd(self.ten_env, "flush", "agora_rtc")
        self.ten_env.log_info("[MainControlExtension] Interrupt signal sent")

    async def _check_interrupt_file(self):
        """定期检查 property.json 中的 interrupt 标记"""
        try:
            # 获取 property.json 文件路径（通过读取父进程的命令行参数）
            parent_pid = os.getppid()
            # pid_msg = f"[MainControlExtension] Parent PID: {parent_pid}"
            # self.ten_env.log_info(pid_msg)

            cmdline_path = f'/proc/{parent_pid}/cmdline'
            path_msg = f"[MainControlExtension] Reading cmdline from: {cmdline_path}"
            self.ten_env.log_info(path_msg)

            try:
                with open(cmdline_path, 'r') as f:
                    cmdline = f.read()
                # 过滤特殊字符，替换为空格
                cmdline = re.sub(r'[\x00-\x1F\x7F-\x9F]', ' ', cmdline)
            except (FileNotFoundError, PermissionError) as e:
                # /proc 文件系统在某些环境中可能不可用
                error_msg = f"[MainControlExtension] Failed to read cmdline: {e}"
                self.ten_env.log_error(error_msg)
                return

            # 从命令行中提取 --property 参数
            match = re.search(r'--property\s+([^\s]+)', cmdline)
            if not match:
                no_param_msg = "[MainControlExtension] No --property parameter found in cmdline"
                self.ten_env.log_info(no_param_msg)
                return

            property_path = match.group(1)

            if not os.path.exists(property_path):
                not_found_msg = f"[MainControlExtension] Property file not found: {property_path}"
                self.ten_env.log_warn(not_found_msg)
                return

            # 读取并检查 interrupt 标记（在 ten 节点下）
            read_msg = f"[MainControlExtension] Reading property file: {property_path}"
            self.ten_env.log_info(read_msg)
            with open(property_path, 'r') as f:
                data = json.load(f)

            # 从 ten 节点下读取 interrupt 标记
            ten_data = data.get("ten", {})
            ten_keys = ", ".join(list(ten_data.keys()))
            keys_msg = f"[MainControlExtension] Ten data keys: {ten_keys}"
            self.ten_env.log_info(keys_msg)

            interrupt_data = ten_data.get("interrupt", {})
            action = interrupt_data.get("action")
            timestamp = interrupt_data.get("timestamp", 0)

            check_msg = f"[MainControlExtension] Interrupt check: action={action}, timestamp={timestamp}, last_timestamp={self._last_interrupt_timestamp}"
            self.ten_env.log_info(check_msg)

            # 检查是否是新的 interrupt 请求（时间戳比上次处理的新）
            if action == "flush" and timestamp > self._last_interrupt_timestamp:
                self._last_interrupt_timestamp = timestamp
                detected_msg = f"[MainControlExtension] Detected interrupt from property.json, timestamp={timestamp}"
                self.ten_env.log_info(detected_msg)
                await self._interrupt()

                # 清除标记（从 ten 节点下）
                self.ten_env.log_info("[MainControlExtension] Clearing interrupt marker")
                with open(property_path, 'w') as f:
                    data["ten"]["interrupt"] = {}
                    json.dump(data, f)
                self.ten_env.log_info("[MainControlExtension] Interrupt marker cleared")
            else:
                no_new_msg = f"[MainControlExtension] No new interrupt to process: action={action}, timestamp={timestamp}, last_timestamp={self._last_interrupt_timestamp}"
                self.ten_env.log_info(no_new_msg)
        except Exception as e:
            # 记录错误以便诊断，包含详细的错误栈
            import traceback
            stack_trace = traceback.format_exc()
            error_msg = f"[MainControlExtension] Check interrupt failed: {e}\nStack trace:\n{stack_trace}"
            self.ten_env.log_error(error_msg)

    async def _periodic_check_interrupt(self):
        """定期检查 property.json 的后台任务"""
        self.ten_env.log_info("[MainControlExtension] Starting periodic interrupt check task")
        periodic_check_interrupt_times = 0
        while not self.stopped:
            await self._check_interrupt_file()
            await asyncio.sleep(1)  # 每 1 秒检查一次
            self.ten_env.log_info(f"[MainControlExtension] _periodic_check_interrupt {periodic_check_interrupt_times}")
            periodic_check_interrupt_times = periodic_check_interrupt_times + 1
        self.ten_env.log_info("[MainControlExtension] Periodic interrupt check task stopped")
