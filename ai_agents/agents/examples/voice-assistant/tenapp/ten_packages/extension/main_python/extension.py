import json
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
from .agent.ollama_client import OllamaClient
from .config import OllamaConfig
from .agent.events import (
    ASRResultEvent,
    LLMResponseEvent,
    ToolRegisterEvent,
    UserJoinedEvent,
    UserLeftEvent,
)
from .helper import _send_cmd, _send_data, parse_sentences
from .config import MainControlConfig  # assume extracted from your base model

import uuid


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
        self.ollama_client: OllamaClient = None
        self.ollama_config: OllamaConfig = None

        self.stopped: bool = False
        self._rtc_user_count: int = 0
        self.sentence_fragment: str = ""
        self.turn_id: int = 0
        self.session_id: str = "0"

        # 打断短语列表 - 这些短语会触发打断但不发送给 LLM
        self._interrupt_phrases = {
            "打断一下", "停一下", "等一下", "别说了", "稍等一下", "我知道了", "好的，我知道了", "好的我知道了"
            "stop", "wait", "hold on",
        }

    def _current_metadata(self) -> dict:
        return {"session_id": self.session_id, "turn_id": self.turn_id}

    def _is_interrupt_phrase(self, text: str) -> bool:
        """
        检查文本是否是打断短语。
        处理前后标点符号，如 "，打断一下" 或 "打断一下。"
        也支持重复字符，如 "停停停"、"等等等"
        """
        import string
        import re

        # 去除前后标点符号后检查
        text_clean = text.strip().strip(string.punctuation + "，。！？、；：""''《》【】")
        text_lower = text_clean.lower()

        # 检查是否包含打断短语
        for phrase in self._interrupt_phrases:
            if phrase.lower() in text_lower or text_lower in phrase.lower():
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

        # Initialize Ollama client from environment variables
        self.ollama_config = OllamaConfig.from_env()
        if self.ollama_config.enabled:
            self.ollama_client = OllamaClient(
                base_url=self.ollama_config.base_url,
                model=self.ollama_config.model,
                timeout=self.ollama_config.timeout,
            )
            ten_env.log_info(
                f"[MainControlExtension] Ollama client initialized: {self.ollama_config.base_url}, model={self.ollama_config.model}"
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
        self.session_id = event.metadata.get("session_id", "100")
        stream_id = int(self.session_id)
        if not event.text:
            return

        self.ten_env.log_info(
            f"[MainControlExtension] ASR result: text='{_truncate_text(event.text)}', final={event.final}, len={len(event.text)}"
        )

        # 检查是否是打断短语（在语义验证之前）
        if event.final and self._is_interrupt_phrase(event.text):
            self.ten_env.log_info(
                f"[MainControlExtension] Interrupt phrase detected: '{_truncate_text(event.text)}', calling _interrupt()"
            )
            await self._interrupt()
            await self._send_transcript("user", event.text, event.final, stream_id)
            return  # 不发送给 LLM

        # Semantic validation using Ollama (only on final results)
        if event.final and self.ollama_client:
            is_meaningful, elapsed, raw_response = await self.ollama_client.is_meaningful(event.text)
            self.ten_env.log_info(
                f"[MainControlExtension] Ollama validation: text='{_truncate_text(event.text)}', is_meaningful={is_meaningful}, elapsed={elapsed:.3f}s, response={_truncate_text(raw_response, 30)}"
            )
            if not is_meaningful:
                self.ten_env.log_info(
                    f"[MainControlExtension] Skipping noise text: '{_truncate_text(event.text)}'"
                )
                return

        if event.final or len(event.text) > 2:
            self.ten_env.log_info(
                f"[MainControlExtension] Calling _interrupt() due to ASR result (final={event.final}, text_len={len(event.text)})"
            )
            await self._interrupt()
            self.ten_env.log_info("[MainControlExtension] _interrupt() completed")

        if event.final:
            self.turn_id += 1
            await self.agent.queue_llm_input(event.text)
        await self._send_transcript("user", event.text, event.final, stream_id)

    @agent_event_handler(LLMResponseEvent)
    async def _on_llm_response(self, event: LLMResponseEvent):
        if not event.is_final and event.type == "message":
            sentences, self.sentence_fragment = parse_sentences(
                self.sentence_fragment, event.delta
            )
            for s in sentences:
                await self._send_to_tts(s, False)

        if event.is_final and event.type == "message":
            remaining_text = self.sentence_fragment or ""
            self.sentence_fragment = ""
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

    async def on_stop(self, ten_env: AsyncTenEnv):
        ten_env.log_info("[MainControlExtension] on_stop")
        self.stopped = True
        await self.agent.stop()
        if self.ollama_client:
            await self.ollama_client.close()

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd):
        await self.agent.on_cmd(cmd)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data):
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
        中断正在进行的大语言模型（LLM）和语音合成（TTS）生成过程。该操作通常在检测到用户语音时触发。
        """
        self.sentence_fragment = ""
        await self.agent.flush_llm()
        await _send_data(
            self.ten_env, "tts_flush", "tts", {"flush_id": str(uuid.uuid4())}
        )
        await _send_cmd(self.ten_env, "flush", "agora_rtc")
        self.ten_env.log_info("[MainControlExtension] Interrupt signal sent")
