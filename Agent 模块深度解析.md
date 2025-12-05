好的,我来详细解释 `agent` 模块的代码架构和作用,以及如何为集成 RAG 或 MCP 做准备。

## Agent 模块深度解析

### 整体架构概览

Agent 模块采用 **事件驱动 + 队列解耦** 的设计模式,核心目标是:
1. **解耦业务逻辑**: 将 ASR、LLM、TTS 的处理逻辑从 Extension 中分离
2. **可中断性**: 支持用户随时打断 AI 回复
3. **扩展性**: 便于添加新的事件类型和处理器

```
┌─────────────────────────────────────────────────────────────┐
│                    MainControlExtension                       │
│  (协调者 - 接收外部事件,委托给 Agent 处理)                   │
└───────────────────┬─────────────────────────────────────────┘
                    │ 委托处理
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                         Agent                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  ASR 队列    │  │  LLM 队列    │  │ 事件分发器   │       │
│  │  (顺序处理)  │  │  (可中断)    │  │ (回调注册)   │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              LLMExec (LLM 执行器)                     │   │
│  │  - 上下文管理  - 工具调用  - 流式响应                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心文件详解

### 1. **events.py** - 事件定义层

````python name=agent/events.py
```python
from pydantic import BaseModel
from typing import Literal, Union, Dict, Any

# ========== 事件基类 ==========
class AgentEventBase(BaseModel):
    """所有事件的基类,定义了事件的类型和名称"""
    type: Literal["cmd", "data"]  # cmd: 命令事件, data: 数据事件
    name: str  # 事件名称

# ========== 命令事件 (CMD Events) ==========
# 这些事件由外部系统触发,表示系统状态变化

class UserJoinedEvent(AgentEventBase):
    """用户加入事件 - 当用户进入房间时触发"""
    type: Literal["cmd"] = "cmd"
    name: Literal["on_user_joined"] = "on_user_joined"

class UserLeftEvent(AgentEventBase):
    """用户离开事件 - 当用户离开房间时触发"""
    type: Literal["cmd"] = "cmd"
    name: Literal["on_user_left"] = "on_user_left"

class ToolRegisterEvent(AgentEventBase):
    """工具注册事件 - 当新工具注册到系统时触发"""
    type: Literal["cmd"] = "cmd"
    name: Literal["tool_register"] = "tool_register"
    tool: LLMToolMetadata  # 工具的元数据
    source: str  # 工具来源的 extension 名称

# ========== 数据事件 (DATA Events) ==========
# 这些事件携带业务数据,表示数据流动

class ASRResultEvent(AgentEventBase):
    """语音识别结果事件 - ASR 输出的文本"""
    type: Literal["data"] = "data"
    name: Literal["asr_result"] = "asr_result"
    text: str  # 识别的文本
    final: bool  # 是否为最终结果 (true) 还是中间结果 (false)
    metadata: Dict[str, Any]  # 元数据 (如 session_id)

class LLMResponseEvent(AgentEventBase):
    """LLM 响应事件 - LLM 输出的文本"""
    type: Literal["message", "reasoning"] = "message"  
    # message: 正常回复, reasoning: 推理过程
    name: Literal["llm_response"] = "llm_response"
    delta: str  # 增量文本 (流式输出)
    text: str  # 累积的完整文本
    is_final: bool  # 是否结束
```
````

**设计要点:**
- ✅ **强类型定义**: 使用 Pydantic 确保数据结构的一致性
- ✅ **区分 CMD 和 DATA**: 命令事件表示状态变化,数据事件表示数据流
- 🎯 **扩展点**: 添加 RAG 事件时,只需新增如 `RAGQueryEvent`, `RAGResultEvent`

---

### 2. **decorators.py** - 装饰器工具

````python name=agent/decorators.py
```python
def agent_event_handler(event_type: AgentEvent):
    """
    装饰器: 标记方法为事件处理器
    
    工作原理:
    1. 在方法上添加 `_agent_event_type` 属性
    2. Agent 初始化时扫描所有装饰的方法
    3. 自动注册到事件分发系统
    
    用法:
        @agent_event_handler(ASRResultEvent)
        async def on_asr(self, event: ASRResultEvent):
            # 处理 ASR 结果
    """
    def wrapper(func):
        setattr(func, "_agent_event_type", event_type)
        return func
    return wrapper
```
````

**优势:**
- 🎨 **声明式编程**: 通过装饰器清晰表达意图
- 🔄 **自动注册**: 无需手动调用 `agent.on()` 注册
- 📝 **可读性强**: 一眼看出哪个方法处理哪个事件

---

### 3. **agent.py** - 核心控制器

这是最核心的文件,我逐段解析:

#### 3.1 初始化 - 双队列设计

````python name=agent/agent.py (初始化部分)
```python
class Agent:
    def __init__(self, ten_env: AsyncTenEnv):
        self.ten_env = ten_env
        self.stopped = False
        
        # ========== 回调注册表 ==========
        # key: 事件类型, value: 处理器列表
        self._callbacks: dict[AgentEvent, list[Callable]] = {}
        
        # ========== 双队列设计 ==========
        # 为什么需要两个队列?
        # 1. ASR 队列: 顺序处理,不可中断 (保证用户输入的完整性)
        # 2. LLM 队列: 可中断处理 (允许用户打断 AI 回复)
        self._asr_queue: asyncio.Queue[ASRResultEvent] = asyncio.Queue()
        self._llm_queue: asyncio.Queue[LLMResponseEvent] = asyncio.Queue()
        
        # 消费者任务
        self._asr_consumer: Optional[asyncio.Task] = None
        self._llm_consumer: Optional[asyncio.Task] = None
        self._llm_active_task: Optional[asyncio.Task] = None  # 当前正在处理的 LLM 任务
        
        # ========== LLM 执行器 ==========
        self.llm_exec = LLMExec(ten_env)
        # 注册回调: 当 LLM 输出时,转换为 LLMResponseEvent
        self.llm_exec.on_response = self._on_llm_response
        self.llm_exec.on_reasoning_response = self._on_llm_reasoning_response
        
        # 启动消费者
        self._asr_consumer = asyncio.create_task(self._consume_asr())
        self._llm_consumer = asyncio.create_task(self._consume_llm())
```
````

**架构亮点:**
- 🔀 **队列隔离**: ASR 和 LLM 处理互不阻塞
- ⏸️ **可中断性**: LLM 任务可以被取消,ASR 任务不可取消
- 🔌 **回调解耦**: LLMExec 不直接依赖 Agent,通过回调通信

#### 3.2 事件注册机制

````python name=agent/agent.py (事件注册)
```python
def on(
    self,
    event_type: AgentEvent,
    handler: Callable[[AgentEvent], Awaitable] = None,
):
    """
    注册事件处理器 (支持两种用法)
    
    用法 1: 直接注册
        agent.on(ASRResultEvent, handler_func)
    
    用法 2: 装饰器 (配合 @agent_event_handler)
        @agent.on(ASRResultEvent)
        async def handler(event):
            pass
    """
    def decorator(func: Callable[[AgentEvent], Awaitable]):
        self._callbacks.setdefault(event_type, []).append(func)
        return func
    
    if handler is None:
        return decorator  # 返回装饰器
    else:
        return decorator(handler)  # 直接注册
```
````

#### 3.3 事件分发器

````python name=agent/agent.py (事件分发)
```python
async def _dispatch(self, event: AgentEvent):
    """
    核心分发逻辑: 将事件分发给所有注册的处理器
    
    工作流程:
    1. 遍历所有注册的事件类型
    2. 使用 isinstance() 检查事件是否匹配
    3. 顺序执行所有匹配的处理器
    4. 错误隔离: 单个处理器失败不影响其他处理器
    """
    for etype, handlers in self._callbacks.items():
        if isinstance(event, etype):  # 类型匹配
            for h in handlers:
                try:
                    await h(event)  # 异步执行
                except asyncio.CancelledError:
                    raise  # 中断信号需要向上传播
                except Exception as e:
                    self.ten_env.log_error(f"Handler error for {etype}: {e}")
```
````

#### 3.4 双消费者模式

````python name=agent/agent.py (消费者)
```python
# ========== ASR 消费者: 顺序处理 ==========
async def _consume_asr(self):
    """
    ASR 队列消费者 - 简单的顺序处理
    特点: 不可中断,保证用户输入的完整性
    """
    while not self.stopped:
        event = await self._asr_queue.get()
        await self._dispatch(event)

# ========== LLM 消费者: 可中断处理 ==========
async def _consume_llm(self):
    """
    LLM 队列消费者 - 支持中断
    特点: 
    1. 将处理包装成 Task,保存引用
    2. 可以通过 task.cancel() 中断
    3. 捕获 CancelledError,优雅处理中断
    """
    while not self.stopped:
        event = await self._llm_queue.get()
        # 🔑 关键: 包装成 Task
        self._llm_active_task = asyncio.create_task(self._dispatch(event))
        try:
            await self._llm_active_task
        except asyncio.CancelledError:
            self.ten_env.log_info("[Agent] Active LLM task cancelled")
        finally:
            self._llm_active_task = None
```
````

**为什么 LLM 需要可中断?**
```
场景: 用户打断 AI 回复
1. AI 正在说: "今天天气..."
2. 用户说: "停!换个话题"
3. 系统需要:
   ① 停止 AI 继续输出 ✅ (取消 LLM Task)
   ② 清空 TTS 队列 ✅ (flush_llm)
   ③ 开始处理新输入 ✅
```

#### 3.5 中断机制

````python name=agent/agent.py (中断机制)
```python
async def flush_llm(self):
    """
    刷新 LLM 处理流程 (用于中断)
    
    步骤:
    1. 调用 llm_exec.flush() - 中止 LLM 请求
    2. 清空 LLM 事件队列 - 丢弃未处理的响应
    3. 取消当前活动任务 - 停止正在执行的处理器
    """
    # Step 1: 中止 LLM 请求
    await self.llm_exec.flush()
    
    # Step 2: 清空队列
    while not self._llm_queue.empty():
        try:
            self._llm_queue.get_nowait()
            self._llm_queue.task_done()
        except asyncio.QueueEmpty:
            break
    
    # Step 3: 取消活动任务
    if self._llm_active_task and not self._llm_active_task.done():
        self._llm_active_task.cancel()
        try:
            await self._llm_active_task  # 等待任务清理
        except asyncio.CancelledError:
            pass
        self._llm_active_task = None
```
````

#### 3.6 外部接口

````python name=agent/agent.py (外部接口)
```python
# ========== 接收外部命令 ==========
async def on_cmd(self, cmd: Cmd):
    """
    处理来自 TEN Runtime 的命令
    转换为标准事件: Cmd → AgentEvent
    """
    name = cmd.get_name()
    if name == "on_user_joined":
        await self._emit_direct(UserJoinedEvent())
    elif name == "on_user_left":
        await self._emit_direct(UserLeftEvent())
    elif name == "tool_register":
        tool_json, err = cmd.get_property_to_json("tool")
        tool = LLMToolMetadata.model_validate_json(tool_json)
        await self._emit_direct(
            ToolRegisterEvent(tool=tool, source=cmd.get_source().extension_name)
        )

# ========== 接收外部数据 ==========
async def on_data(self, data: Data):
    """
    处理来自 TEN Runtime 的数据
    转换为标准事件: Data → AgentEvent
    """
    if data.get_name() == "asr_result":
        asr_json, _ = data.get_property_to_json(None)
        asr = json.loads(asr_json)
        await self._emit_asr(
            ASRResultEvent(
                text=asr.get("text", ""),
                final=asr.get("final", False),
                metadata=asr.get("metadata", {}),
            )
        )
```
````

---

### 4. **llm_exec.py** - LLM 执行器

这是与 LLM 交互的核心组件,负责:
1. **上下文管理**: 维护完整的对话历史
2. **工具调用**: 支持 Function Calling
3. **流式处理**: 增量式输出

#### 4.1 核心数据结构

````python name=agent/llm_exec.py (数据结构)
```python
class LLMExec:
    def __init__(self, ten_env: AsyncTenEnv):
        # ========== 输入队列 ==========
        self.input_queue = AsyncQueue()  # 用户输入队列
        
        # ========== 对话上下文 ==========
        self.contexts: list[LLMMessage] = []
        # 示例结构:
        # [
        #   {"role": "user", "content": "今天天气怎么样?"},
        #   {"role": "assistant", "content": "今天北京晴天"},
        #   {"role": "user", "content": "那明天呢?"}
        # ]
        
        # ========== 工具注册表 ==========
        self.available_tools: list[LLMToolMetadata] = []
        self.tool_registry: dict[str, str] = {}  # tool_name → extension_name
        
        # ========== 回调函数 ==========
        self.on_response: Optional[Callable] = None  # 正常响应回调
        self.on_reasoning_response: Optional[Callable] = None  # 推理回调
        
        # 启动输入队列处理
        self.loop.create_task(self._process_input_queue())
```
````

#### 4.2 输入队列处理

````python name=agent/llm_exec.py (输入处理)
```python
async def _process_input_queue(self):
    """
    处理用户输入队列
    
    工作流程:
    1. 从队列取出用户文本
    2. 包装成 LLMMessageContent
    3. 发送到 LLM
    4. 等待流式响应
    """
    while not self.stopped:
        try:
            text = await self.input_queue.get()  # 阻塞等待
            new_message = LLMMessageContent(role="user", content=text)
            
            # 创建任务并等待
            self.current_task = self.loop.create_task(
                self._send_to_llm(self.ten_env, new_message)
            )
            await self.current_task
            
        except asyncio.CancelledError:
            # 中断时的清理逻辑
            text = self.current_text
            self.current_text = None
            if self.on_response and text:
                # 发送当前累积的文本作为最终结果
                await self.on_response(self.ten_env, "", text, True)
```
````

#### 4.3 发送到 LLM

````python name=agent/llm_exec.py (发送逻辑)
```python
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
    # Step 1: 合并上下文
    messages = self.contexts.copy()
    messages.append(new_message)
    
    # Step 2: 构造请求
    request_id = str(uuid.uuid4())
    self.current_request_id = request_id
    llm_input = LLMRequest(
        request_id=request_id,
        messages=messages,
        streaming=True,  # 🔑 关键: 启用流式输出
        parameters={"temperature": 0.7},
        tools=self.available_tools  # 🔧 传递工具列表
    )
    
    # Step 3: 发送命令
    response = _send_cmd_ex(ten_env, "chat_completion", "llm", llm_input.model_dump())
    
    # Step 4: 处理流式响应
    await self._queue_context(ten_env, new_message)  # 保存到上下文
    
    async for cmd_result, _ in response:
        if cmd_result and not cmd_result.is_final():
            response_json, _ = cmd_result.get_property_to_json(None)
            completion = parse_llm_response(response_json)
            await self._handle_llm_response(completion)  # 分发响应
```
````

#### 4.4 响应处理 (模式匹配)

````python name=agent/llm_exec.py (响应处理)
```python
async def _handle_llm_response(self, llm_output: LLMResponse | None):
    """
    处理 LLM 响应 - 使用 Python 3.10+ 的模式匹配
    
    支持的响应类型:
    1. MessageDelta: 流式文本增量
    2. MessageDone: 文本完成
    3. ReasoningDelta/Done: 推理过程 (如 o1 模型)
    4. ToolCall: 工具调用请求
    """
    match llm_output:
        # ========== 流式文本 ==========
        case LLMResponseMessageDelta():
            delta = llm_output.delta  # 增量文本
            text = llm_output.content  # 累积文本
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
        
        # ========== 推理过程 ==========
        case LLMResponseReasoningDelta():
            if self.on_reasoning_response:
                await self.on_reasoning_response(
                    self.ten_env, llm_output.delta, llm_output.content, False
                )
        
        # ========== 工具调用 ==========
        case LLMResponseToolCall():
            await self._handle_tool_call(llm_output)
```
````

#### 4.5 工具调用处理

````python name=agent/llm_exec.py (工具调用)
```python
async def _handle_tool_call(self, llm_output: LLMResponseToolCall):
    """
    处理工具调用 (Function Calling)
    
    工作流程:
    1. 从 tool_registry 查找工具所在的 extension
    2. 发送 tool_call 命令到目标 extension
    3. 等待工具执行结果
    4. 将结果作为新消息发送回 LLM
    5. LLM 基于工具结果继续生成回复
    """
    self.ten_env.log_info(f"Invoking tool call: {llm_output.name}")
    
    # Step 1: 查找工具
    src_extension_name = self.tool_registry.get(llm_output.name)
    
    # Step 2: 调用工具
    result, _ = await _send_cmd(
        self.ten_env,
        "tool_call",
        src_extension_name,
        {
            "name": llm_output.name,
            "arguments": llm_output.arguments,
        },
    )
    
    # Step 3: 处理结果
    if result.get_status_code() == StatusCode.OK:
        r, _ = result.get_property_to_json(CMD_PROPERTY_RESULT)
        tool_result: LLMToolResult = json.loads(r)
        
        if tool_result["type"] == "llmresult":
            result_content = tool_result["content"]
            
            # Step 4: 保存工具调用到上下文
            context_function_call = LLMMessageFunctionCall(
                name=llm_output.name,
                arguments=json.dumps(llm_output.arguments),
                call_id=llm_output.tool_call_id,
            )
            await self._queue_context(self.ten_env, context_function_call)
            
            # Step 5: 将工具结果发送回 LLM
            await self._send_to_llm(
                self.ten_env,
                LLMMessageFunctionCallOutput(
                    output=result_content,
                    call_id=llm_output.tool_call_id,
                ),
            )
```
````

---

## 集成 RAG/MCP 的架构设计建议

根据代码审查和您的需求,我建议以下方案:

### 方案 1: RAG 作为工具 (推荐用于简单场景)

```python
# 新增事件类型
class RAGQueryEvent(AgentEventBase):
    """RAG 查询事件"""
    type: Literal["data"] = "data"
    name: Literal["rag_query"] = "rag_query"
    query: str
    context_window: int = 5

class RAGResultEvent(AgentEventBase):
    """RAG 查询结果"""
    type: Literal["data"] = "data"
    name: Literal["rag_result"] = "rag_result"
    results: List[Dict[str, Any]]
    metadata: Dict[str, Any]
```

**集成步骤:**
1. 创建 `rag_tool_python` extension
2. 注册到 LLM 的工具列表
3. LLM 决定何时调用 RAG
4. 工具返回结果后,LLM 基于结果生成回复

### 方案 2: RAG 作为前置增强 (推荐用于复杂场景)

创建新文件建议参考我之前提到的代码质量规则,我发现当前代码存在以下问题:让我详细解释 Agent 模块的代码架构和作用,并为你规划 RAG/MCP 的集成方案。

---

## Agent 模块详细解析

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     MainControlExtension                     │
│  (extension.py - 事件路由器)                                  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Agent (agent.py)                           │   │
│  │  - 事件队列管理 (_asr_queue, _llm_queue)              │   │
│  │  - 事件分发器 (_dispatch)                             │   │
│  │  - 回调注册表 (_callbacks)                            │   │
│  │                                                        │   │
│  │  ┌──────────────────────────────────────────────┐    │   │
│  │  │    LLMExec (llm_exec.py)                     │    │   │
│  │  │  - 输入队列 (input_queue)                    │    │   │
│  │  │  - 上下文管理 (contexts[])                   │    │   │
│  │  │  - 工具注册表 (tool_registry)                │    │   │
│  │  │  - 流式处理 (_handle_llm_response)           │    │   │
│  │  └──────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件详解

### 1. **MainControlExtension (extension.py)**

**职责**: 作为 TEN Framework 扩展的入口点,负责事件路由

```python
class MainControlExtension(AsyncExtension):
    """
    🎯 核心职责:
    1. 初始化 Agent 和配置
    2. 将 TEN 运行时事件 (on_cmd/on_data) 路由到 Agent
    3. 管理会话状态 (用户数量、轮次ID)
    4. 处理 TTS 和转录输出
    """
    
    # 🔧 关键属性
    agent: Agent                    # 内部代理
    config: MainControlConfig       # 配置
    _rtc_user_count: int            # 当前用户数
    turn_id: int                    # 对话轮次
    sentence_fragment: str          # 句子片段缓存
```

**关键方法:**

#### `on_init` - 初始化
```python
async def on_init(self, ten_env: AsyncTenEnv):
    """
    1. 加载配置
    2. 创建 Agent 实例
    3. 自动注册装饰器标注的事件处理器
    """
    self.agent = Agent(ten_env)
    
    # 通过反射找到所有 @agent_event_handler 装饰的方法
    for attr_name in dir(self):
        fn = getattr(self, attr_name)
        event_type = getattr(fn, "_agent_event_type", None)
        if event_type:
            self.agent.on(event_type, fn)  # 注册到 Agent
```

#### 事件处理器 (使用装饰器)

```python
@agent_event_handler(UserJoinedEvent)
async def _on_user_joined(self, event: UserJoinedEvent):
    """用户加入时发送欢迎语"""
    self._rtc_user_count += 1
    if self._rtc_user_count == 1:
        await self._send_to_tts(self.config.greeting, True)

@agent_event_handler(ASRResultEvent)
async def _on_asr_result(self, event: ASRResultEvent):
    """
    处理语音识别结果
    
    流程:
    1. 如果是最终结果 → 发送到 LLM
    2. 如果文本长度 > 2 或是最终结果 → 触发中断
    3. 发送转录到 message_collector
    """
    if event.final or len(event.text) > 2:
        await self._interrupt()  # 🔥 打断当前 AI 回复
    
    if event.final:
        self.turn_id += 1
        await self.agent.queue_llm_input(event.text)  # 🚀 发送到 LLM

@agent_event_handler(LLMResponseEvent)
async def _on_llm_response(self, event: LLMResponseEvent):
    """
    处理 LLM 响应
    
    流程:
    1. 流式输出时 → 按句子分割并发送到 TTS
    2. 最终输出时 → 发送剩余文本到 TTS
    """
    if not event.is_final:
        # 使用 parse_sentences 按标点符号分割句子
        sentences, self.sentence_fragment = parse_sentences(
            self.sentence_fragment, event.delta
        )
        for s in sentences:
            await self._send_to_tts(s, False)  # 💬 逐句播放
```

#### 核心辅助方法

```python
async def _interrupt(self):
    """
    🛑 中断当前对话
    
    触发时机: 用户开始说话时
    
    执行操作:
    1. 清空句子片段缓存
    2. 清空 LLM 队列
    3. 清空 TTS 队列
    4. 清空 RTC 音频缓冲区
    """
    self.sentence_fragment = ""
    await self.agent.flush_llm()
    await _send_data(self.ten_env, "tts_flush", "tts", {...})
    await _send_cmd(self.ten_env, "flush", "agora_rtc")

async def _send_to_tts(self, text: str, is_final: bool):
    """发送文本到 TTS 系统"""
    await _send_data(
        self.ten_env,
        "tts_text_input",
        "tts",
        {
            "request_id": f"tts-request-{self.turn_id}",
            "text": text,
            "text_input_end": is_final,
        },
    )
```

---

### 2. **Agent (agent/agent.py)**

**职责**: 事件驱动的调度核心,管理 ASR 和 LLM 事件队列

```python
class Agent:
    """
    🎯 核心职责:
    1. 维护两个独立的事件队列 (ASR/LLM)
    2. 提供事件注册机制 (观察者模式)
    3. 调度 LLMExec 处理 LLM 请求
    4. 支持可中断的 LLM 任务
    """
    
    # 🔧 关键属性
    _callbacks: dict[AgentEvent, list[Callable]]  # 事件回调注册表
    _asr_queue: asyncio.Queue[ASRResultEvent]     # ASR 事件队列
    _llm_queue: asyncio.Queue[LLMResponseEvent]   # LLM 事件队列
    llm_exec: LLMExec                             # LLM 执行器
    _llm_active_task: Optional[asyncio.Task]      # 当前活跃的 LLM 任务
```

#### 事件注册机制

```python
def on(self, event_type: AgentEvent, handler: Callable):
    """
    注册事件处理器 (观察者模式)
    
    支持两种用法:
    1. agent.on(ASRResultEvent, async_handler)
    2. @agent.on(ASRResultEvent)
       async def handler(event): ...
    """
    def decorator(func: Callable):
        self._callbacks.setdefault(event_type, []).append(func)
        return func
    
    if handler is None:
        return decorator
    else:
        return decorator(handler)

async def _dispatch(self, event: AgentEvent):
    """分发事件到所有注册的处理器"""
    for etype, handlers in self._callbacks.items():
        if isinstance(event, etype):
            for h in handlers:
                await h(event)  # 🚀 调用处理器
```

#### 双队列消费者

```python
async def _consume_asr(self):
    """
    ASR 事件消费者
    
    特点: 顺序处理,不可中断
    """
    while not self.stopped:
        event = await self._asr_queue.get()
        await self._dispatch(event)

async def _consume_llm(self):
    """
    LLM 事件消费者
    
    特点: 可中断 (用于实现打断功能)
    """
    while not self.stopped:
        event = await self._llm_queue.get()
        
        # 作为独立任务运行,可以被取消
        self._llm_active_task = asyncio.create_task(self._dispatch(event))
        
        try:
            await self._llm_active_task
        except asyncio.CancelledError:
            self.ten_env.log_info("[Agent] LLM task cancelled")
        finally:
            self._llm_active_task = None
```

#### TEN 运行时接口

```python
async def on_cmd(self, cmd: Cmd):
    """
    处理来自 TEN 运行时的命令
    
    支持的命令:
    - on_user_joined: 用户加入
    - on_user_left: 用户离开
    - tool_register: 工具注册
    """
    name = cmd.get_name()
    if name == "on_user_joined":
        await self._emit_direct(UserJoinedEvent())
    elif name == "tool_register":
        tool_json, _ = cmd.get_property_to_json("tool")
        tool = LLMToolMetadata.model_validate_json(tool_json)
        await self._emit_direct(ToolRegisterEvent(tool=tool, source=...))

async def on_data(self, data: Data):
    """
    处理来自 TEN 运行时的数据
    
    支持的数据:
    - asr_result: 语音识别结果
    """
    if data.get_name() == "asr_result":
        asr_json, _ = data.get_property_to_json(None)
        asr = json.loads(asr_json)
        await self._emit_asr(ASRResultEvent(
            text=asr["text"],
            final=asr["final"],
            metadata=asr.get("metadata", {})
        ))
```

#### LLM 控制接口

```python
async def queue_llm_input(self, text: str):
    """队列化用户输入到 LLM"""
    await self.llm_exec.queue_input(text)

async def flush_llm(self):
    """
    🛑 清空 LLM 队列和任务
    
    执行操作:
    1. 调用 llm_exec.flush() 中止当前请求
    2. 清空 _llm_queue
    3. 取消 _llm_active_task
    """
    await self.llm_exec.flush()
    
    # 清空队列
    while not self._llm_queue.empty():
        self._llm_queue.get_nowait()
    
    # 取消活跃任务
    if self._llm_active_task and not self._llm_active_task.done():
        self._llm_active_task.cancel()
        await self._llm_active_task  # 等待取消完成
```

---

### 3. **LLMExec (agent/llm_exec.py)**

**职责**: LLM 执行器,负责与 LLM 的交互

```python
class LLMExec:
    """
    🎯 核心职责:
    1. 管理 LLM 输入队列
    2. 维护对话上下文
    3. 处理流式响应
    4. 支持工具调用 (Function Calling)
    """
    
    # 🔧 关键属性
    input_queue: AsyncQueue                       # 输入队列
    contexts: list[LLMMessage]                    # 对话上下文
    tool_registry: dict[str, str]                 # 工具注册表
    available_tools: list[LLMToolMetadata]        # 可用工具列表
    current_request_id: Optional[str]             # 当前请求ID
    on_response: Callable                         # 响应回调
    on_reasoning_response: Callable               # 推理响应回调
```

#### 输入队列处理

```python
async def _process_input_queue(self):
    """
    处理输入队列
    
    流程:
    1. 从队列取出用户输入
    2. 构造 LLMMessageContent
    3. 调用 _send_to_llm 发送请求
    4. 处理取消异常 (中断时)
    """
    while not self.stopped:
        try:
            text = await self.input_queue.get()
            new_message = LLMMessageContent(role="user", content=text)
            
            self.current_task = self.loop.create_task(
                self._send_to_llm(self.ten_env, new_message)
            )
            await self.current_task
            
        except asyncio.CancelledError:
            # 🔥 处理中断: 将当前文本标记为完成
            text = self.current_text
            if self.on_response and text:
                await self.on_response(self.ten_env, "", text, True)
```

#### 发送到 LLM

```python
async def _send_to_llm(self, ten_env: AsyncTenEnv, new_message: LLMMessage):
    """
    发送请求到 LLM
    
    流程:
    1. 复制上下文并添加新消息
    2. 构造 LLMRequest (包含工具列表)
    3. 调用 send_cmd_ex 发送命令 (流式)
    4. 逐个处理响应片段
    """
    messages = self.contexts.copy()
    messages.append(new_message)
    
    request_id = str(uuid.uuid4())
    self.current_request_id = request_id
    
    llm_input = LLMRequest(
        request_id=request_id,
        messages=messages,
        streaming=True,  # 🌊 流式输出
        tools=self.available_tools,  # 🔧 工具列表
    )
    
    response = _send_cmd_ex(ten_env, "chat_completion", "llm", llm_input.model_dump())
    
    # 队列化新消息到上下文
    await self._queue_context(ten_env, new_message)
    
    # 🔄 流式处理响应
    async for cmd_result, _ in response:
        if cmd_result and not cmd_result.is_final():
            response_json, _ = cmd_result.get_property_to_json(None)
            completion = parse_llm_response(response_json)
            await self._handle_llm_response(completion)
```

#### 响应处理 (支持多种类型)

```python
async def _handle_llm_response(self, llm_output: LLMResponse):
    """
    处理 LLM 响应
    
    支持的响应类型:
    1. LLMResponseMessageDelta - 流式文本片段
    2. LLMResponseMessageDone - 文本生成完成
    3. LLMResponseReasoningDelta - 推理过程片段 (如 o1 模型)
    4. LLMResponseReasoningDone - 推理完成
    5. LLMResponseToolCall - 工具调用
    """
    match llm_output:
        case LLMResponseMessageDelta():
            # 🌊 流式文本
            delta = llm_output.delta
            text = llm_output.content
            self.current_text = text
            
            if delta and self.on_response:
                await self.on_response(self.ten_env, delta, text, False)
            
            # 更新上下文
            await self._write_context(self.ten_env, "assistant", text)
        
        case LLMResponseMessageDone():
            # ✅ 文本完成
            text = llm_output.content
            if self.on_response and text:
                await self.on_response(self.ten_env, "", text, True)
        
        case LLMResponseToolCall():
            # 🔧 工具调用
            src_extension = self.tool_registry.get(llm_output.name)
            
            # 调用工具扩展
            result, _ = await _send_cmd(
                self.ten_env,
                "tool_call",
                src_extension,
                {"name": llm_output.name, "arguments": llm_output.arguments},
            )
            
            # 将工具结果添加到上下文
            if result.get_status_code() == StatusCode.OK:
                tool_result = json.loads(result.get_property_to_json("result"))
                
                # 添加 function_call 消息
                await self._queue_context(
                    self.ten_env,
                    LLMMessageFunctionCall(
                        name=llm_output.name,
                        arguments=json.dumps(llm_output.arguments),
                        call_id=llm_output.tool_call_id,
                    )
                )
                
                # 添加 function_call_output 并继续对话
                await self._send_to_llm(
                    self.ten_env,
                    LLMMessageFunctionCallOutput(
                        output=tool_result["content"],
                        call_id=llm_output.tool_call_id,
                    ),
                )
```

#### 上下文管理

```python
async def _write_context(
    self, ten_env: AsyncTenEnv, role: Literal["user", "assistant"], content: str
):
    """
    写入上下文
    
    逻辑:
    - 如果最后一条消息的 role 相同 → 更新内容
    - 否则 → 添加新消息
    """
    last_context = self.contexts[-1] if self.contexts else None
    if last_context and last_context.role == role:
        last_context.content = content  # 更新
    else:
        new_message = LLMMessageContent(role=role, content=content)
        await self._queue_context(ten_env, new_message)  # 添加
```

---

### 4. **事件定义 (agent/events.py)**

```python
# 基类
class AgentEventBase(BaseModel):
    type: Literal["cmd", "data"]
    name: str

# 命令事件
class UserJoinedEvent(AgentEventBase):
    type: Literal["cmd"] = "cmd"
    name: Literal["on_user_joined"] = "on_user_joined"

class UserLeftEvent(AgentEventBase):
    type: Literal["cmd"] = "cmd"
    name: Literal["on_user_left"] = "on_user_left"

class ToolRegisterEvent(AgentEventBase):
    type: Literal["cmd"] = "cmd"
    name: Literal["tool_register"] = "tool_register"
    tool: LLMToolMetadata
    source: str

# 数据事件
class ASRResultEvent(AgentEventBase):
    type: Literal["data"] = "data"
    name: Literal["asr_result"] = "asr_result"
    text: str
    final: bool
    metadata: Dict[str, Any]

class LLMResponseEvent(AgentEventBase):
    type: Literal["message", "reasoning"] = "message"
    name: Literal["llm_response"] = "llm_response"
    delta: str       # 增量文本
    text: str        # 完整文本
    is_final: bool   # 是否结束

# 联合类型
AgentEvent = Union[
    UserJoinedEvent,
    UserLeftEvent,
    ToolRegisterEvent,
    ASRResultEvent,
    LLMResponseEvent,
]
```

---

## 集成 RAG/MCP 的方案

根据上面的分析,我为你设计了一个优雅的集成方案:

### 方案 1: **RAG 作为 LLM 前置增强器**

**架构:**
```
用户输入 → RAGExecutor.enrich() → LLMExec._send_to_llm()
```

**实现步骤:**

#### 1. 新增 `agent/rag/` 目录

```python
# agent/rag/rag_executor.py
class RAGExecutor:
    """RAG 查询增强器"""
    
    def __init__(self, ten_env: AsyncTenEnv, retriever: BaseRetriever):
        self.ten_env = ten_env
        self.retriever = retriever
        self.context_enricher = ContextEnricher()
    
    async def enrich(self, query: str, history: List[LLMMessage]) -> str:
        """
        增强用户查询
        
        流程:
        1. 提取查询意图
        2. 检索相关文档 (Top-K)
        3. 格式化增强上下文
        """
        # 提取意图
        intent = self._extract_intent(query, history)
        
        # 检索
        results = await self.retriever.retrieve(intent, top_k=3)
        
        # 格式化
        enriched = self.context_enricher.format(query, results)
        
        self.ten_env.log_info(f"[RAG] Original: {query}")
        self.ten_env.log_info(f"[RAG] Enriched: {enriched}")
        
        return enriched
    
    def _extract_intent(self, query: str, history: List[LLMMessage]) -> str:
        """提取查询意图 (考虑历史)"""
        if not history:
            return query
        
        # 简单策略: 结合最后一轮对话
        last_assistant_msg = next(
            (msg for msg in reversed(history) if msg.role == "assistant"),
            None
        )
        
        if last_assistant_msg:
            return f"上下文: {last_assistant_msg.content}\n问题: {query}"
        else:
            return query
```

```python
# agent/rag/retriever.py
from abc import ABC, abstractmethod

class BaseRetriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> List[RAGResult]:
        pass

@dataclass
class RAGResult:
    content: str
    score: float
    metadata: Dict[str, Any]

class VectorRetriever(BaseRetriever):
    """向量检索器 (FAISS/Milvus/ChromaDB)"""
    
    def __init__(self, index_path: str, embedding_model: str = "text-embedding-ada-002"):
        self.index = self._load_index(index_path)
        self.embedding_model = embedding_model
    
    async def retrieve(self, query: str, top_k: int = 5) -> List[RAGResult]:
        # 1. 查询向量化
        query_embedding = await self._embed(query)
        
        # 2. 向量检索
        results = self.index.search(query_embedding, top_k)
        
        # 3. 格式化结果
        return [
            RAGResult(
                content=res["text"],
                score=res["score"],
                metadata=res["metadata"]
            )
            for res in results
        ]
```

```python
# agent/rag/context_enricher.py
class ContextEnricher:
    """上下文增强器"""
    
    def format(self, query: str, results: List[RAGResult]) -> str:
        """
        格式化增强上下文
        
        策略: 将检索结果作为"参考资料"附加到查询前
        """
        if not results:
            return query
        
        context_parts = ["# 参考资料\n"]
        for i, res in enumerate(results, 1):
            context_parts.append(f"## 资料 {i} (相关度: {res.score:.2f})\n")
            context_parts.append(f"{res.content}\n\n")
        
        context_parts.append(f"# 用户问题\n{query}")
        
        return "".join(context_parts)
```

#### 2. 修改 `LLMExec._process_input_queue()`

```python
class LLMExec:
    def __init__(self, ten_env: AsyncTenEnv):
        # 原有属性...
        
        # 🆕 RAG 增强器 (可选)
        self.rag_executor: Optional[RAGExecutor] = None
    
    async def _process_input_queue(self):
        while not self.stopped:
            try:
                text = await self.input_queue.get()
                
                # 🆕 RAG 前置增强
                if self.rag_executor:
                    enriched_text = await self.rag_executor.enrich(
                        text, self.contexts
                    )
                else:
                    enriched_text = text
                
                new_message = LLMMessageContent(role="user", content=enriched_text)
                self.current_task = self.loop.create_task(
                    self._send_to_llm(self.ten_env, new_message)
                )
                await self.current_task
            except asyncio.CancelledError:
                # 处理取消...
                pass
```

#### 3. 配置和初始化

```python
# extension.py
async def on_init(self, ten_env: AsyncTenEnv):
    # 加载配置
    config_json, _ = await ten_env.get_property_to_json(None)
    self.config = MainControlConfig.model_validate_json(config_json)
    
    # 创建 Agent
    self.agent = Agent(ten_env)
    
    # 🆕 可选: 启用 RAG
    if self.config.enable_rag:
        ten_env.log_info("[MainControl] Initializing RAG...")
        
        retriever = VectorRetriever(
            index_path=self.config.rag_index_path,
            embedding_model=self.config.rag_embedding_model
        )
        
        rag_executor = RAGExecutor(ten_env, retriever)
        self.agent.llm_exec.rag_executor = rag_executor
        
        ten_env.log_info("[MainControl] RAG initialized")
    
    # 注册事件处理器...
```

```json
// property.json 配置
{
  "greeting": "你好!我是语音助手。",
  "enable_rag": true,
  "rag_index_path": "/path/to/vector_index",
  "rag_embedding_model": "text-embedding-ada-002"
}
```

---

### 方案 2: **MCP 作为上下文管理器**

**架构:**
```
LLMExec.contexts → MCPContextManager.sync() → MCP Server
                    ↑ 持久化到外部存储
```

**实现步骤:**

#### 1. 新增 `agent/mcp/` 目录

```python
# agent/mcp/context_manager.py
class MCPContextManager:
    """Model Context Protocol 上下文管理器"""
    
    def __init__(self, ten_env: AsyncTenEnv, server_url: str):
        self.ten_env = ten_env
        self.client = MCPClient(server_url)
        self.session_id: Optional[str] = None
    
    async def create_session(self, metadata: Dict[str, Any]) -> str:
        """创建新会话"""
        response = await self.client.create_context({
            "type": "conversation",
            "metadata": metadata
        })
        self.session_id = response["context_id"]
        return self.session_id
    
    async def sync_messages(self, messages: List[LLMMessage]):
        """同步消息到 MCP Server"""
        if not self.session_id:
            raise RuntimeError("Session not created")
        
        await self.client.update_context(
            self.session_id,
            {
                "messages": [msg.model_dump() for msg in messages],
                "updated_at": int(time.time())
            }
        )
    
    async def get_history(self, limit: int = 10) -> List[LLMMessage]:
        """从 MCP Server 获取历史"""
        if not self.session_id:
            return []
        
        response = await self.client.get_context(self.session_id)
        messages_data = response.get("messages", [])
        
        return [LLMMessage.model_validate(msg) for msg in messages_data[-limit:]]
```

```python
# agent/mcp/client.py
class MCPClient:
    """MCP 协议客户端"""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.session = aiohttp.ClientSession()
    
    async def create_context(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建上下文"""
        async with self.session.post(
            f"{self.server_url}/contexts",
            json=data
        ) as resp:
            return await resp.json()
    
    async def update_context(self, context_id: str, updates: Dict[str, Any]):
        """更新上下文"""
        async with self.session.patch(
            f"{self.server_url}/contexts/{context_id}",
            json=updates
        ) as resp:
            return await resp.json()
    
    async def get_context(self, context_id: str) -> Dict[str, Any]:
        """获取上下文"""
        async with self.session.get(
            f"{self.server_url}/contexts/{context_id}"
        ) as resp:
            return await resp.json()
```

#### 2. 修改 `LLMExec` 集成 MCP

```python
class LLMExec:
    def __init__(self, ten_env: AsyncTenEnv):
        # 原有属性...
        
        # 🆕 MCP 上下文管理器 (可选)
        self.mcp_manager: Optional[MCPContextManager] = None
    
    async def _queue_context(self, ten_env: AsyncTenEnv, new_message: LLMMessage):
        """队列化新消息到上下文"""
        ten_env.log_info(f"_queue_context: {new_message}")
        self.contexts.append(new_message)
        
        # 🆕 同步到 MCP Server
        if self.mcp_manager:
            await self.mcp_manager.sync_messages(self.contexts)
```

#### 3. 初始化 MCP

```python
# extension.py
async def on_init(self, ten_env: AsyncTenEnv):
    # ... 加载配置 ...
    
    self.agent = Agent(ten_env)
    
    # 🆕 可选: 启用 MCP
    if self.config.enable_mcp:
        ten_env.log_info("[MainControl] Initializing MCP...")
        
        mcp_manager = MCPContextManager(
            ten_env,
            server_url=self.config.mcp_server_url
        )
        
        # 创建会话
        session_id = await mcp_manager.create_session({
            "user_id": "default_user",
            "created_at": int(time.time())
        })
        
        self.agent.llm_exec.mcp_manager = mcp_manager
        
        ten_env.log_info(f"[MainControl] MCP session created: {session_id}")
```

## 对比两种方案

| 特性         | RAG 方案          | MCP 方案            |
| ------------ | ----------------- | ------------------- |
| **集成位置** | LLM 前置          | 上下文同步          |
| **主要作用** | 增强查询,补充知识 | 持久化上下文,跨会话 |
| **性能影响** | 每次查询增加延迟  | 异步同步,影响小     |
| **复杂度**   | 中等 (需要向量库) | 低 (HTTP 请求)      |
| **适用场景** | 知识密集型对话    | 多轮长对话,用户历史 |

## 推荐方案

**建议同时集成 RAG 和 MCP**,因为它们解决不同问题:

1. **RAG**: 在用户提问时,实时检索相关知识
2. **MCP**: 持久化对话历史,支持跨会话恢复

**集成顺序:**
1. 先实现 RAG (更核心,提升回答质量)
2. 再实现 MCP (增强功能,支持长期记忆)

**下一步行动:**
请告诉我你希望:
1. 我创建完整的代码重构 PR (包含 RAG/MCP)?
2. 还是先提供单个模块的详细实现示例?
3. 或者你有其他特定需求?