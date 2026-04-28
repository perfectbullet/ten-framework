import asyncio
import json
import os
import re
import string
import time
from typing import Literal
from pathlib import Path
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
ENABLE_INTERRUPT_PHRASE = True


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
            "打断一下",
            "停一下",
            "别说了",
            "stop",
            "wait",
            "hold on",
        }

        # 状态标志：用于感知当前系统状态
        self.is_llm_streaming: bool = False  # LLM 是否正在流式输出
        # 有序列表管理 TTS 状态：最大长度100
        self.tts_status_dict: dict = {}  # {tts_request_id: {"tts_text_list": [], "audio_duration_list": []}}

    def _current_metadata(self) -> dict:
        return {"session_id": self.session_id, "turn_id": self.turn_id}

    def is_tts_playing(self) -> bool:
        """
        检查当前轮次是否有 TTS 正在播放。
        使用 self.turn_id 确定当前轮次，而非 max(keys())。
        """

        current_turn_id = str(self.turn_id)
        self.ten_env.log_info(
            f"[MainControlExtension] is_tts_playing {self.tts_status_dict}"
            f"current_turn_id {current_turn_id}"
        )
        if current_turn_id not in self.tts_status_dict:
            raise ValueError(
                f"[MainControlExtension] current_turn_id {current_turn_id}"
                f" no in {self.tts_status_dict}"
            )

        current_tts_status = self.tts_status_dict[current_turn_id]

        # 如果没有发送任何 TTS 文本，说明 TTS 还没开始，返回 False
        if not current_tts_status.get("tts_text_list"):
            return False

        # 如果有 TTS 文本但没有 audio_duration_list，说明 TTS 正在生成音频
        if not current_tts_status.get("audio_duration_list"):
            return True

        # 如果 text_input_end 还没收到，说明还在往 TTS 发文本，TTS 还会生成更多音频
        if not current_tts_status.get("text_input_end"):
            return True

        last_audio_duration_status = current_tts_status["audio_duration_list"][-1]

        playback_end_time = (
            current_tts_status["tts_audio_start_playing_time"]
            + last_audio_duration_status["duration_ms"] / 1000.0
        )

        current_time = time.time()
        self.ten_env.log_info(
            f"[MainControlExtension] playback_end_time {playback_end_time} "
            f"current_turn_id {current_turn_id} "
            f"current_time is {current_time} "
        )
        return current_time < playback_end_time

    def _is_interrupt_phrase(self, text: str) -> bool:
        """
        检查文本是否是打断短语。
        处理前后标点符号，如 "，打断一下" 或 "打断一下。"
        也支持重复字符，如 "停停停"、"等等等"
        """
        # 去除前后标点符号后检查
        text_clean = text.strip().strip(string.punctuation + "，。！？、；：''《》【】")
        text_lower = text_clean.lower()
        # 检查是否包含打断短语（只检查短语是否在输入文本中）
        for phrase in self._interrupt_phrases:
            if phrase.lower() in text_lower:
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
        ten_env.log_info("[MainControlExtension] TextIntentValidator initialized")

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
            # 新用户加入，重置对话状态
            self.turn_id = 0
            self.tts_status_dict.clear()
            self.is_llm_streaming = False

            await self._send_to_tts(self.config.greeting, True)
            await self._send_transcript("assistant", self.config.greeting, True, 100)

    @agent_event_handler(UserLeftEvent)
    async def _on_user_left(self, event: UserLeftEvent):
        self._rtc_user_count -= 1

    @agent_event_handler(ToolRegisterEvent)
    async def _on_tool_register(self, event: ToolRegisterEvent):
        await self.agent.register_llm_tool(event.tool, event.source)

    @agent_event_handler(ASRResultEvent)
    async def _on_asr_result(self, event: ASRResultEvent):
        # 使用新的 TTS 状态字典计算是否忙碌
        is_tts_busy = self.is_tts_playing()
        # 打印当前状态
        self.ten_env.log_info(
            f"[MainControlExtension] Current state: "
            f"LLM streaming={self.is_llm_streaming}, "
            f"TTS busy={is_tts_busy}, "
            f"ASR result: text='{event.text}'"
            f"event.final={event.final}"
        )
        self.session_id = event.metadata.get("session_id", "100")
        stream_id = int(self.session_id)
        if not event.text:
            return
        if not event.final:
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
        if self.text_intent_validator:
            (
                is_meaningful,
                elapsed,
                raw_response,
            ) = await self.text_intent_validator.is_meaningful(event.text)
            self.ten_env.log_info(
                f"[MainControlExtension] TextIntentValidator: "
                f"is_meaningful={is_meaningful}, elapsed={elapsed:.3f}s "
                f"raw_response is {raw_response}"
            )
            if not is_meaningful:
                self.ten_env.log_info(
                    f"[MainControlExtension] Skipping noise text: '{_truncate_text(event.text)}'"
                )
                return
        self.ten_env.log_info(f"[MainControlExtension] text_len={len(event.text)}")
        if len(event.text) < 4:
            return
        await self._interrupt()
        self.turn_id += 1
        # 这里要初始化当前轮次语音初始化状态
        self.tts_status_dict[str(self.turn_id)] = {
            "tts_text_list": [],
            "audio_duration_list": [],
            "text_input_end": False,
        }

        await self.agent.queue_llm_input(event.text)
        # 只在有意义文本且已打断后发送转录
        await self._send_transcript("user", event.text, event.final, stream_id)

    @agent_event_handler(LLMResponseEvent)
    async def _on_llm_response(self, event: LLMResponseEvent):
        self.ten_env.log_info(
            f"[MainControlExtension] _on_llm_response event.type={event.type},"
            f"[MainControlExtension] event.delta={event.delta}"
        )

        # 任何非 final 事件都标记 LLM 正在流式输出
        if not event.is_final:
            self.is_llm_streaming = True

        # message 类型的 TTS 发送
        if event.type == "message":
            if not event.is_final:
                await self._send_to_tts(event.delta, False)
            else:
                await self._send_to_tts(event.delta, True)
                self.is_llm_streaming = False
        await self._send_transcript(
            "assistant",
            event.text,
            event.is_final,
            100,
            data_type="text",
        )

    async def on_start(self, ten_env: AsyncTenEnv):
        ten_env.log_info("[MainControlExtension] on_start")
        # 启动定期检查 interrupt 标记和保存 TTS 状态字典的后台任务
        asyncio.create_task(self._periodic_check_interrupt())
        # 保存 TTS 状态字典到文件
        asyncio.create_task(self._save_tts_status_dict_to_file())

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
            ten_env.log_info(
                "[MainControlExtension] Received end_of_sentence, sending asr_finalize to ASR"
            )
            # Create asr_finalize data
            asr_finalize_data = Data.create("asr_finalize")
            asr_finalize_data.set_property_string(
                "finalize_id", f"vad_{int(time.time() * 1000)}"
            )
            await ten_env.send_data(asr_finalize_data)
            return

        # Handle start_of_sentence command from VAD
        if cmd_name == "start_of_sentence":
            ten_env.log_info("[MainControlExtension] Received start_of_sentence")
            return

        # Delegate other commands to agent
        await self.agent.on_cmd(cmd)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data):
        # 计算当前 TTS 是否忙碌（播放中）
        is_tts_busy = self.is_tts_playing()
        # 添加详细的调试日志
        self.ten_env.log_info(
            f"[MainControlExtension] TTS status check: "
            f"is_tts_busy={is_tts_busy}, "
            f"is_llm_streaming={self.is_llm_streaming}"
        )

        data_name = data.get_name()
        self.ten_env.log_info(f"[MainControlExtension] on_data received: {data_name}")
        # 处理 TTS 音频开始事件
        if data_name == "tts_audio_start":
            request_id, _ = data.get_property_string("request_id")
            # 安全检查：打断可能导致 entry 已被删除
            if request_id in self.tts_status_dict:
                # 注意：这是 TTS 开始"发送"音频的时间，不是"播报"开始时间
                # 播报实际开始时间会晚于这个值（存在网络+播放器缓冲延迟）
                self.tts_status_dict[request_id]["tts_audio_start_playing_time"] = (
                    time.time()
                )
            self.ten_env.log_info(
                f"[MainControlExtension] TTS audio started: request_id={request_id}"
            )
        # 处理 TTS 音频结束事件， 就是文本数据已经发送完成；并不能代表音频合成完成或者播放完成。
        elif data_name == "tts_audio_end":
            request_id, _ = data.get_property_string("request_id")
            duration_ms, _ = data.get_property_int("request_total_audio_duration_ms")
            reason, _ = data.get_property_int("reason")

            # 更新 TTS 状态列表
            if request_id in self.tts_status_dict:
                self.tts_status_dict[request_id]["audio_duration_list"].append(
                    {
                        "duration_ms": duration_ms,
                        "reason": reason,
                    }
                )

            self.ten_env.log_info(
                f"[MainControlExtension] TTS audio ended: request_id={request_id}, "
                f"duration_ms={duration_ms}, reason={reason}, "
            )
        # 处理 TTS 刷新结束事件（打断时触发）
        elif data_name == "tts_flush_end":
            # 打断时清空当前 TTS 状态
            current_turn_request_id = str(self.turn_id)
            if current_turn_request_id in self.tts_status_dict:
                self.ten_env.log_info(
                    f"[MainControlExtension] TTS flush ended - cleared status for: {current_turn_request_id}"
                )
            self.ten_env.log_info(
                "[MainControlExtension] TTS flush ended - cleared TTS status"
            )

        # 其他数据事件（非 TTS 事件）传递给 agent 处理
        elif (
            data_name != "tts_audio_start"
            and data_name != "tts_audio_end"
            and data_name != "tts_flush_end"
        ):
            self.ten_env.log_info(
                f"[MainControlExtension] not a tts event on_data received: {data_name}"
            )
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
            raise ValueError("should not get reasoning")
        self.ten_env.log_info(
            f"[MainControlExtension] Sent transcript: {role}, final={final}, text={_truncate_text(text)}"
        )

    async def _send_to_tts(self, text: str, is_final: bool):
        """
        Sends a sentence to the TTS system.
        """
        request_id = str(self.turn_id)

        # 初始化 TTS 状态记录
        if request_id not in self.tts_status_dict:
            if len(self.tts_status_dict) >= 100:
                # 删除最旧的记录
                oldest_key = next(iter(self.tts_status_dict))
                del self.tts_status_dict[oldest_key]
                self.ten_env.log_info(
                    f"[MainControlExtension] Removed oldest TTS status: {oldest_key}"
                )
            self.tts_status_dict[request_id] = {
                "tts_text_list": [],
                "audio_duration_list": [],
                "text_input_end": False,
            }

        # 更新文本列表
        self.tts_status_dict[request_id]["tts_text_list"].append(text)

        # 标记是否是最后一帧文本输入
        if is_final:
            self.tts_status_dict[request_id]["text_input_end"] = True

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
        # 打断时设置 has_interrupt
        current_turn_request_id = str(self.turn_id)
        if current_turn_request_id in self.tts_status_dict:
            self.tts_status_dict[current_turn_request_id]["has_interrupt"] = True
            self.ten_env.log_info(
                f"[MainControlExtension] Cleared TTS status for interrupted request: {current_turn_request_id}"
            )

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

            cmdline_path = f"/proc/{parent_pid}/cmdline"
            path_msg = f"[MainControlExtension] Reading cmdline from: {cmdline_path}"
            # self.ten_env.log_info(path_msg)

            try:
                with open(cmdline_path, "r") as f:
                    cmdline = f.read()
                # 过滤特殊字符，替换为空格
                cmdline = re.sub(r"[\x00-\x1F\x7F-\x9F]", " ", cmdline)
            except (FileNotFoundError, PermissionError) as e:
                # /proc 文件系统在某些环境中可能不可用
                error_msg = f"[MainControlExtension] Failed to read cmdline: {e}"
                self.ten_env.log_error(error_msg)
                return

            # 从命令行中提取 --property 参数
            match = re.search(r"--property\s+([^\s]+)", cmdline)
            if not match:
                no_param_msg = (
                    "[MainControlExtension] No --property parameter found in cmdline"
                )
                self.ten_env.log_info(no_param_msg)
                return

            property_path = match.group(1)

            if not os.path.exists(property_path):
                not_found_msg = (
                    f"[MainControlExtension] Property file not found: {property_path}"
                )
                self.ten_env.log_warn(not_found_msg)
                return

            # 读取并检查 interrupt 标记（在 ten 节点下）
            read_msg = f"[MainControlExtension] Reading property file: {property_path}"
            # self.ten_env.log_info(read_msg)
            with open(property_path, "r") as f:
                data = json.load(f)

            # 从 ten 节点下读取 interrupt 标记
            ten_data = data.get("ten", {})
            ten_keys = ", ".join(list(ten_data.keys()))
            keys_msg = f"[MainControlExtension] Ten data keys: {ten_keys}"
            # self.ten_env.log_info(keys_msg)

            interrupt_data = ten_data.get("interrupt", {})
            action = interrupt_data.get("action")

            check_msg = f"[MainControlExtension] Interrupt check: action={action}"
            self.ten_env.log_info(check_msg)

            # 检查是否是新的 interrupt 请求（时间戳比上次处理的新）
            if action == "flush":
                detected_msg = (
                    "[MainControlExtension] Detected interrupt from property.json"
                )
                self.ten_env.log_info(detected_msg)
                await self._interrupt()

                # 清除标记（从 ten 节点下）
                self.ten_env.log_info(
                    "[MainControlExtension] Clearing interrupt marker"
                )
                with open(property_path, "w") as f:
                    data["ten"]["interrupt"] = {}
                    json.dump(data, f)
                self.ten_env.log_info("[MainControlExtension] Interrupt marker cleared")
            else:
                no_new_msg = f"[MainControlExtension] No new interrupt to process: action={action}"
                # self.ten_env.log_info(no_new_msg)
        except Exception as e:
            # 记录错误以便诊断，包含详细的错误栈
            import traceback

            stack_trace = traceback.format_exc()
            error_msg = f"[MainControlExtension] Check interrupt failed: {e}\nStack trace:\n{stack_trace}"
            self.ten_env.log_error(error_msg)

    async def _save_tts_status_dict_to_file(self):
        """每1秒保存一次 TTS 状态字典到文件（异步）"""
        while not self.stopped:
            try:
                # 创建目录（如果不存在）
                save_dir = Path("tts_status_dict")
                save_dir.mkdir(exist_ok=True)

                # 保存到文件（使用线程池避免阻塞）
                save_file = save_dir / "tts_status_dict.json"
                await asyncio.to_thread(self._sync_save_tts_status_dict, save_file)

                # self.ten_env.log_info(
                #     f"[MainControlExtension] TTS status dict saved to {save_file}"
                # )
            except Exception as e:
                self.ten_env.log_error(
                    f"[MainControlExtension] Failed to save TTS status dict: {e}"
                )

            await asyncio.sleep(2)  # 每10秒保存一次

    def _sync_save_tts_status_dict(self, save_file: Path) -> None:
        """同步保存 TTS 状态字典（在线程池中执行）"""
        with open(save_file, "w", encoding="utf-8") as f:
            json.dump(self.tts_status_dict, f, ensure_ascii=False, indent=2)

    async def _periodic_check_interrupt(self):
        """定期检查 property.json 和保存 TTS 状态字典的后台任务"""
        self.ten_env.log_info(
            "[MainControlExtension] Starting periodic interrupt check and save task"
        )
        periodic_check_interrupt_times = 0
        while not self.stopped:
            await self._check_interrupt_file()
            await asyncio.sleep(1)  # 每 1 秒检查一次
            # self.ten_env.log_info(
            #     f"[MainControlExtension] _periodic_check_interrupt {periodic_check_interrupt_times}"
            # )
            periodic_check_interrupt_times = periodic_check_interrupt_times + 1
        self.ten_env.log_info(
            "[MainControlExtension] Periodic interrupt check and save task stopped"
        )
