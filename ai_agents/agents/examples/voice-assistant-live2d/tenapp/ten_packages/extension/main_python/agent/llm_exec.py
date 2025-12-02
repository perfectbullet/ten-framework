#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import asyncio
import json
import traceback
from typing import Awaitable, Callable, Literal, Optional
from ten_ai_base.const import CMD_PROPERTY_RESULT
from ten_ai_base.helper import AsyncQueue
from ten_ai_base.struct import (
    LLMMessage,
    LLMMessageContent,
    LLMMessageFunctionCall,
    LLMMessageFunctionCallOutput,
    LLMRequest,
    LLMResponse,
    LLMResponseMessageDelta,
    LLMResponseMessageDone,
    LLMResponseReasoningDelta,
    LLMResponseReasoningDone,
    LLMResponseToolCall,
    parse_llm_response,
)
from ten_ai_base.types import LLMToolMetadata, LLMToolResult
from ..helper import _send_cmd, _send_cmd_ex
from ten_runtime import AsyncTenEnv, Loc, StatusCode
import uuid

from .Retrieval_RAGFlow_Client import RAGFlowRetrievalClient


class LLMExec:
    """
    Context for LLM operations, including ASR and TTS.
    This class handles the interaction with the LLM, including processing commands and data.
    """

    def __init__(self, ten_env: AsyncTenEnv):
        self.ten_env = ten_env
        self.input_queue = AsyncQueue()# 用户输入队列
        self.stopped = False
        # ========== 回调函数 ==========
        self.on_response: Optional[
            Callable[[AsyncTenEnv, str, str, bool], Awaitable[None]]
        ] = None
        # 推理回调
        self.on_reasoning_response: Optional[
            Callable[[AsyncTenEnv, str, str, bool], Awaitable[None]]
        ] = None
        # 正常响应回调
        self.on_tool_call: Optional[
            Callable[[AsyncTenEnv, LLMToolMetadata], Awaitable[None]]
        ] = None
        self.current_task: Optional[asyncio.Task] = None
        self.loop = asyncio.get_event_loop()
        # 启动输入队列处理
        self.loop.create_task(self._process_input_queue())
        # ========== 工具注册表 ==========
        self.available_tools: list[LLMToolMetadata] = []
        self.tool_registry: dict[str, str] = {}
        self.available_tools_lock = (
            asyncio.Lock()
        )  # Lock to ensure thread-safe access
        # ========== 对话上下文 ==========
        self.contexts: list[LLMMessage] = []
        # 示例结构:
        # [
        #   {"role": "user", "content": "今天天气怎么样?"},
        #   {"role": "assistant", "content": "今天北京晴天"},
        #   {"role": "user", "content": "那明天呢?"}
        # ]
        self.current_request_id: Optional[str] = None
        self.current_text = None

    async def queue_input(self, item: str) -> None:
        await self.input_queue.put(item)

    async def flush(self) -> None:
        """
        Flush the input queue to ensure all items are processed.
        This is useful for ensuring that all pending inputs are handled before stopping.
        """
        await self.input_queue.flush()
        if self.current_request_id:
            request_id = self.current_request_id
            self.current_request_id = None
            await _send_cmd(
                self.ten_env, "abort", "llm", {"request_id": request_id}
            )
        if self.current_task:
            self.current_task.cancel()

    async def stop(self) -> None:
        """
        Stop the LLMExec processing.
        This will stop the input queue processing and any ongoing tasks.
        """
        self.stopped = True
        await self.flush()
        if self.current_task:
            self.current_task.cancel()

    async def register_tool(self, tool: LLMToolMetadata, source: str) -> None:
        """
        Register tools with the LLM.
        This method sends a command to register the provided tools.
        """
        async with self.available_tools_lock:
            self.available_tools.append(tool)
            self.tool_registry[tool.name] = source

    async def _process_input_queue(self):
        """
        Process the input queue for commands and data.
        This method runs in a loop, processing items from the queue.
        处理用户输入队列

        工作流程:
        1. 从队列取出用户文本
        2. 包装成 LLMMessageContent
        3. 发送到 LLM
        4. 等待流式响应
        """
        while not self.stopped:
            try:
                text = await self.input_queue.get()     # 阻塞等待
                new_message = LLMMessageContent(role="user", content=text)

                # 创建任务并等待
                self.current_task = self.loop.create_task(
                    self._send_to_llm(self.ten_env, new_message)
                )
                await self.current_task

            except asyncio.CancelledError:
                self.ten_env.log_info("LLMExec processing cancelled.")
                text = self.current_text
                self.current_text = None
                if self.on_response and text:
                    await self.on_response(self.ten_env, "", text, True)
            except Exception as e:
                self.ten_env.log_error(
                    f"Error processing input queue: {traceback.format_exc()}"
                )
            finally:
                self.current_task = None

    async def _queue_context(
        self, ten_env: AsyncTenEnv, new_message: LLMMessage
    ) -> None:
        """
        Queue a new message to the LLM context.
        This method appends the new message to the existing context and sends it to the LLM.
        """
        ten_env.log_info(f"_queue_context: {new_message}")
        self.contexts.append(new_message)

    async def _write_context(
        self,
        ten_env: AsyncTenEnv,
        role: Literal["user", "assistant"],
        content: str,
    ) -> None:
        last_context = self.contexts[-1] if self.contexts else None
        if last_context and last_context.role == role:
            # If the last context has the same role, append to its content
            last_context.content = content
        else:
            # Otherwise, create a new context message
            new_message = LLMMessageContent(role=role, content=content)
            await self._queue_context(ten_env, new_message)

    async def _send_to_llm(
        self, ten_env: AsyncTenEnv, new_message: LLMMessage
    ) -> None:
        """
        发送消息到 LLM 并处理流式响应
        步骤:
        1. 合并上下文 + 新消息
        2. 构造 LLMRequest (包含工具列表)
        3. 调用 LLM Extension
        4. 流式处理响应
        """

        # ===== 新增:RAG 检索 =====
        ten_env.log_info(
            f"_send_to_llm: new_message {new_message}"
        )
        if new_message.role == "user":
            retrieved_docs = await self._retrieve_relevant_docs(new_message.content)
            if retrieved_docs:
                # 将检索结果注入消息
                enriched_content = self._enrich_with_context(
                    new_message.content,
                    retrieved_docs
                )
                new_message.content = enriched_content
        # ===== RAG 检索结束 =====

        # Step 1: 合并上下文
        messages = self.contexts.copy()
        messages.append(new_message)
        # Step 2: 构造请求
        request_id = str(uuid.uuid4())
        self.current_request_id = request_id
        llm_input = LLMRequest(
            request_id=request_id,
            messages=messages,
            streaming=True,  # 关键: 启用流式输出
            parameters={"temperature": 0.7},
            tools=self.available_tools, # 传递工具列表
        )
        input_json = llm_input.model_dump()
        # Step 3: 发送命令
        ten_env.log_info(
            f"_send_to_llm: input_json {input_json}"
        )
        response = _send_cmd_ex(ten_env, "chat_completion", "llm", input_json)
        ten_env.log_info(
            f"_send_to_llm: response {response}"
        )

        # Step 4: 处理流式响应
        # Queue the new message to the context
        await self._queue_context(ten_env, new_message)     # 保存到上下文

        async for cmd_result, _ in response:
            if cmd_result and cmd_result.is_final() is False:
                if cmd_result.get_status_code() == StatusCode.OK:
                    response_json, _ = cmd_result.get_property_to_json(None)
                    ten_env.log_info(
                        f"_send_to_llm: response_json {response_json}"
                    )
                    completion = parse_llm_response(response_json)
                    await self._handle_llm_response(completion)

    async def _handle_llm_response(self, llm_output: LLMResponse | None):
        """
        处理 LLM 响应 - 使用 Python 3.10+ 的模式匹配
        支持的响应类型:
        1. MessageDelta: 流式文本增量
        2. MessageDone: 文本完成
        3. ReasoningDelta/Done: 推理过程 (如 o1 模型)
        4. ToolCall: 工具调用请求
        """
        self.ten_env.log_info(f"_handle_llm_response: {llm_output}")

        match llm_output:
            # ========== 流式文本 ==========
            case LLMResponseMessageDelta():
                delta = llm_output.delta    # 增量文本
                text = llm_output.content   # 累积文本
                self.current_text = text
                if delta and self.on_response:
                    # 触发回调 → 转换为 LLMResponseEvent
                    await self.on_response(self.ten_env, delta, text, False)
                # 更新上下文
                if text:
                    await self._write_context(self.ten_env, "assistant", text)
            # ========== 文本完成 ==========
            case LLMResponseMessageDone():
                text = llm_output.content
                self.current_text = None
                if self.on_response and text:
                    await self.on_response(self.ten_env, "", text, True)
            case LLMResponseReasoningDelta():
                delta = llm_output.delta
                text = llm_output.content
                if delta and self.on_reasoning_response:
                    await self.on_reasoning_response(
                        self.ten_env, delta, text, False
                    )
            # ========== 推理过程 ==========
            case LLMResponseReasoningDone():
                text = llm_output.content
                if self.on_reasoning_response and text:
                    await self.on_reasoning_response(
                        self.ten_env, "", text, True
                    )
            # ========== 工具调用 ==========
            case LLMResponseToolCall():
                self.ten_env.log_info(
                    f"_handle_llm_response: invoking tool call {llm_output.name}"
                )
                src_extension_name = self.tool_registry.get(llm_output.name)
                result, _ = await _send_cmd(
                    self.ten_env,
                    "tool_call",
                    src_extension_name,
                    {
                        "name": llm_output.name,
                        "arguments": llm_output.arguments,
                    },
                )

                if result.get_status_code() == StatusCode.OK:
                    r, _ = result.get_property_to_json(CMD_PROPERTY_RESULT)
                    tool_result: LLMToolResult = json.loads(r)

                    self.ten_env.log_info(f"tool_result: {tool_result}")

                    context_function_call = LLMMessageFunctionCall(
                        name=llm_output.name,
                        arguments=json.dumps(llm_output.arguments),
                        call_id=llm_output.tool_call_id,
                        id=llm_output.response_id,
                        type="function_call",
                    )
                    if tool_result["type"] == "llmresult":
                        result_content = tool_result["content"]
                        if isinstance(result_content, str):
                            await self._queue_context(
                                self.ten_env, context_function_call
                            )
                            await self._send_to_llm(
                                self.ten_env,
                                LLMMessageFunctionCallOutput(
                                    output=result_content,
                                    call_id=llm_output.tool_call_id,
                                    type="function_call_output",
                                ),
                            )
                        else:
                            self.ten_env.log_error(
                                f"Unknown tool result content: {result_content}"
                            )
                    elif tool_result["type"] == "requery":
                        pass
                        # self.memory_cache = []
                        # self.memory_cache.pop()
                        # result_content = tool_result["content"]
                        # nonlocal message
                        # new_message = {
                        #     "role": "user",
                        #     "content": self._convert_to_content_parts(
                        #         message["content"]
                        #     ),
                        # }
                        # new_message["content"] = new_message[
                        #     "content"
                        # ] + self._convert_to_content_parts(
                        #     result_content
                        # )
                        # await self.queue_input_item(
                        #     True, messages=[new_message], no_tool=True
                        # )
                else:
                    self.ten_env.log_error("Tool call failed")

    async def _retrieve_relevant_docs(self, query: str) -> list[str]:
        """
        使用 RAGFlow 的接口检索相关文档
        """
        # if '天气' in query:
        #     return []  # 如果是天气相关问题，跳过检索
        # if '你好' in query:
        #     return []
        try:
            # 配置客户端
            client = RAGFlowRetrievalClient(
                base_url="http://192.168.8.231:9380/v1/api/",  # 修改为您的实际URL
                api_token="ragflow-ZjN2M5MTY2NWJjMzExZjA5Yjg0OTNlMz"  # 修改为您的实际Token
            )
            # 执行检索
            # 修改为实际的知识库ID, 目前这个id是测试的默认知识库id, 账号是刘伟的测试环境
            #
            result = client.retrieval(
                kb_id=["02a723a85bc411f09b8493e33f5c065d"],
                question=query
            )
            # 检查响应状态
            if result.get("code") != 0:
                print(f"❌ 错误: {result.get('message', '未知错误')}")
                print(f"错误代码: {result.get('code', 'N/A')}")
                return []
            docs = []
            # 解析数据
            data = result.get("data", {})
            chunks = data.get("chunks", [])
            if chunks:
                for idx, chunk in enumerate(chunks, 1):  # 显示前5个
                    # 显示内容(优先使用带权重的内容)
                    content = chunk.get('content_with_weight') or chunk.get('content_ltks', '')
                    if content:
                        docs.append(content)
            return docs
        except Exception as e:
            self.ten_env.log_error(f"ChromaDB retrieval failed: {e}")
        return []

    def _enrich_with_context(self, query: str, docs: list[str]) -> str:
        """将检索结果格式化为提示词"""
        context = "\n\n".join([f"\n{doc}" for i, doc in enumerate(docs)])
        prompt_v1 = f"""参考以下文档回答问题:

{context}

用户问题: {query}"""

        prompt_v2 = f"""你是一个专业的问答助手。
请使用参考文档回答问。
如果参考文档可以直接回答问题，那么直接用参考文档中相关的片段进行回答不要自己发挥。
如果参考文档通过概括可以回答问题，那么请结合参考文档进行概括回答。
如果是天气信息，结合工具回答。


以下是示例1：
问题：介绍蜡模的制作的过程
参考文档: # 1. 蜡模的制作
蜡材的可塑性良好，可以进行精细的雕刻。因此，失蜡法常用于青铜、白银、黄金等金属器物的精密铸造。从重量只有几克的精致小物到成吨重的器物，都可以用失蜡法铸造出来。
# （1）准备工作
在正式开始制作青铜钟的蜡模前，需要先在土地上挖一个3米多深的坑。坑内需要保持干燥，并且需要修葺得如同房舍一样工整。接下来的制模操作将在这个深坑里进行。
# (2) 制作三合土内模
混合石灰、黏土和细砂（也就是常被用作建筑材料的三合土）制作青铜钟的内模。内模需要做得平整光滑，不能有一丝裂缝，内模形状如图1-1所示。
# (3) 制作油蜡内模
当用三合土做的青铜钟内模完全干透后，用牛油和黄蜡的混合物（牛油和黄蜡的比例为8:2）在内模上涂上几寸厚（1寸约为3.33厘米，涂抹的厚度等同于最后青铜钟的厚度）。把油蜡层涂抹平整以后开始精细地雕刻上面的图案和文字，完成青铜钟蜡模的雕蜡工作，效果如图1-2所示。
回答：蜡模的制作的过程如下：
1.准备工作
在正式开始制作青铜钟的蜡模前，需要先在土地上挖一个3米多深的坑。坑内需要保持干燥，并且需要修葺得如同房舍一样工整。接下来的制模操作将在这个深坑里进行。
2.制作三合土内模
混合石灰、黏土和细砂（也就是常被用作建筑材料的三合土）制作青铜钟的内模。内模需要做得平整光滑，不能有一丝裂缝，内模形状如图1-1所示。
3.制作油蜡内模
当用三合土做的青铜钟内模完全干透后，用牛油和黄蜡的混合物（牛油和黄蜡的比例为8:2）在内模上涂上几寸厚（1寸约为3.33厘米，涂抹的厚度等同于最后青铜钟的厚度）。把油蜡层涂抹平整以后开始精细地雕刻上面的图案和文字，完成青铜钟蜡模的雕蜡工作，效果如图1-2所示。


以下是示例2：
问题：金属浇铸的步骤
参考文档: # 金属浇铸
可以用来浇铸的金属有金、银、铜、铁等，这里以青铜钟为例进行浇铸技巧的讲解。
# (1) 准备铜材料
在浇注金属液前，需要准备等量的铜材料。 0.5千克 油蜡的体积等同于 5千克 铜的体积，据此计算出制作这个青铜钟需要的铜材料的数量，准备将其熔化（通常在制作油蜡内模的时候就会确定油蜡的使用量）。
# (2) 浇铸
青铜钟模具巨大，需要用大量铜溶液进行一气呵成的浇铸，通常会在青铜钟模具的周围修筑几个熔炉和土槽。土槽的上端连接熔炉，下端倾斜，连接模具的浇铸开口处，土槽两边需要用炭火围起来以保持温度。当所有熔炉内的铜熔化以后，一齐打开所有熔炉的塞口，铜溶液就会沿着土槽一起流进模具，青铜钟就铸造完成了，浇铸流程如图1-4所示。
# （3）开模
浇铸好后，等待青铜钟冷却，然后砸碎泥壳模具，清理缝隙，检查一下浇铸的成品，青铜钟就制成了。
# （4）铸造佛像
没有那么大体量的小型器物（如一尊精致的佛像）的铸造原理与青铜钟的铸造原理是一样的。工匠会在油蜡层进行精细雕刻，如图1-5所示，有些时候也会把底座和佛像分开雕刻，然后将其焊接在一起。
回答：金属浇铸主要步骤有
1.准备铜材料
在浇注金属液前，需要准备等量的铜材料。 0.5千克 油蜡的体积等同于 5千克 铜的体积，据此计算出制作这个青铜钟需要的铜材料的数量，准备将其熔化（通常在制作油蜡内模的时候就会确定油蜡的使用量）。
2.浇铸
青铜钟模具巨大，需要用大量铜溶液进行一气呵成的浇铸，通常会在青铜钟模具的周围修筑几个熔炉和土槽。土槽的上端连接熔炉，下端倾斜，连接模具的浇铸开口处，土槽两边需要用炭火围起来以保持温度。当所有熔炉内的铜熔化以后，一齐打开所有熔炉的塞口，铜溶液就会沿着土槽一起流进模具，青铜钟就铸造完成了，浇铸流程如图1-4所示。
3.开模
浇铸好后，等待青铜钟冷却，然后砸碎泥壳模具，清理缝隙，检查一下浇铸的成品，青铜钟就制成了。
4.铸造佛像
没有那么大体量的小型器物（如一尊精致的佛像）的铸造原理与青铜钟的铸造原理是一样的。工匠会在油蜡层进行精细雕刻，有些时候也会把底座和佛像分开雕刻，然后将其焊接在一起。


以下是示例3：
问题：失蜡铸造原理
参考文档: # 失蜡铸造原理
现代首饰的铸造环节是基于传统的失蜡铸造，应用现代加工机器完成的精密铸造。失蜡铸造又被称为熔模铸造，是以焚失法为基础发展而成的一种铸造方法。失蜡铸造方法（以下简称“失蜡法”）有着悠久的应用历史，直到科技发展迅速的今天，也仍在应用。
《天工开物》中的冶铸篇关于中国古代使用失蜡法进行铸造的详细记述，能够让我们清晰地了解失蜡法的原理及一件器物的铸造过程。下面我们以万斤重的青铜钟和精致的小佛像为例，还原当时的蜡模制作步骤与铸造情景。
回答：失蜡铸造原理
失蜡铸造又被称为熔模铸造，是以焚失法为基础发展而成的一种铸造方法。失蜡铸造方法（以下简称“失蜡法”）有着悠久的应用历史，直到科技发展迅速的今天，也仍在应用。《天工开物》中的冶铸篇关于中国古代使用失蜡法进行铸造的详细记述，能够让我们清晰地了解失蜡法的原理及一件器物的铸造过程。


以下是示例4：
问题：机械制造实习课程的主讲老师是谁？
参考文档: 机械制造实习课程 主讲老师 李双寿
李双寿（1968年2月—），清华大学教授，现任清华大学基础工业训练中心主任。1986年至2001年就读于清华大学机械工程系，先后获学士、硕士及博士学位。1994年起任教于清华大学金属工艺学教研室，历任讲师、副主任、主任，2009年3月起任现职。
回答：机械制造实习是由李双寿老师主讲的。李双寿是清华大学教授，现任清华大学基础工业训练中心主任。


问题：{query} 
参考文档：{context} 
回答："""

        log_txt = f'prompt is {prompt_v2}'
        self.ten_env.log_info(log_txt)
        return prompt_v2
