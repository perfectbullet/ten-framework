#
#
# Agora Real Time Engagement
# Created by Tomas Liu in 2024-08.
# Copyright (c) 2024 Agora IO. All rights reserved.
#
#

import json
import aiohttp

from typing import Any
from dataclasses import dataclass

from ten_runtime import Cmd

from ten_runtime.async_ten_env import AsyncTenEnv
from ten_ai_base.config import BaseConfig
from ten_ai_base.types import (
    LLMToolMetadata,
    LLMToolMetadataParameter,
    LLMToolResult,
    LLMToolResultLLMResult,
)
from ten_ai_base.llm_tool import AsyncLLMToolBaseExtension

from .weather_sync_with_pinyin import fetch_weather


CMD_TOOL_REGISTER = "tool_register"
CMD_TOOL_CALL = "tool_call"
CMD_PROPERTY_NAME = "name"
CMD_PROPERTY_ARGS = "args"

TOOL_REGISTER_PROPERTY_NAME = "name"
TOOL_REGISTER_PROPERTY_DESCRIPTON = "description"
TOOL_REGISTER_PROPERTY_PARAMETERS = "parameters"
TOOL_CALLBACK = "callback"

CURRENT_TOOL_NAME = "get_current_weather"
# CURRENT_TOOL_DESCRIPTION = "Determine current weather in user's location."
CURRENT_TOOL_DESCRIPTION = "获取用户所在位置的当前天气。"
CURRENT_TOOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "location": {
            "type": "string",
            "description": "The city and state (use only English) e.g. San Francisco, CA",
        }
    },
    "required": ["location"],
}


@dataclass
class WeatherToolConfig(BaseConfig):
    api_key: str = ""


class WeatherToolExtension(AsyncLLMToolBaseExtension):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.session = None
        self.ten_env = None
        self.config: WeatherToolConfig = None

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_init")
        self.session = aiohttp.ClientSession()

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_start")

        self.config = await WeatherToolConfig.create_async(ten_env=ten_env)
        ten_env.log_info(f"config: {self.config}")
        if self.config.api_key:
            # Key present: register tools as usual.
            await super().on_start(ten_env)
        else:
            # Key missing: keep extension loaded but disabled; do not register tools.
            # This makes the weather tool optional and avoids failing app startup.
            ten_env.log_info(
                "WeatherToolExtension disabled: WEATHERAPI_API_KEY not set (optional)."
            )

        self.ten_env = ten_env

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_stop")

        # TODO: clean up resources
        if self.session:
            await self.session.close()
            self.session = None  # Ensure it can't be reused accidentally

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        ten_env.log_debug("on_deinit")

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))

        await super().on_cmd(ten_env, cmd)

    def get_tool_metadata(self, ten_env: AsyncTenEnv) -> list[LLMToolMetadata]:
        return [
            LLMToolMetadata(
                name=CURRENT_TOOL_NAME,
                description=CURRENT_TOOL_DESCRIPTION,
                parameters=[
                    LLMToolMetadataParameter(
                        name="location",
                        type="string",
                        description="城市的名称",
                        required=True,
                    ),
                ],
            ),
        ]

    async def run_tool(
        self, ten_env: AsyncTenEnv, name: str, args: dict
    ) -> LLMToolResult | None:
        ten_env.log_info(f"run_tool name: {name}, args: {args}")
        if name == CURRENT_TOOL_NAME:
            result = await self._get_current_weather(args)
            return LLMToolResultLLMResult(
                type="llmresult",
                content=json.dumps(result),
            )
        return LLMToolResultLLMResult(
                type="llmresult",
                content=json.dumps({}),
            )

    async def _get_current_weather(self, args: dict) -> Any:
        if "location" not in args:
            raise ValueError("Failed to get property")

        try:
            location = args["location"]
            self.ten_env.log_info(f"Fetching weather for location: {location}")
            weather = fetch_weather(location)
            self.ten_env.log_info(f"finished Fetching weather for location: {location}")
            return weather
        except Exception as e:
            self.ten_env.log_error(f"Failed to get current weather: {e}")
            return None
