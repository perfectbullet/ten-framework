# extension.py 代码详解

这是一个 **OceanBase PowerRAG** 的 TEN 框架扩展实现,用于将 OceanBase 的 AI 数据库能力集成到 LLM2 架构中。

## 核心组件

### 1. **配置类 (`OceanBaseLLM2Config`)**

```python
class OceanBaseLLM2Config(BaseModel):
    base_url: str = ""              # OceanBase API 基础 URL
    api_key: str = ""               # 认证密钥
    ai_database_name: str = ""      # AI 数据库名称
    collection_id: str = ""         # 集合 ID
    user_id: str = "TenAgent"       # 用户标识
    failure_info: str = ""          # 失败时返回的提示信息
```

使用 Pydantic 进行配置验证和管理。

---

### 2. **客户端类 (`OceanBaseChatClient`)**

负责与 OceanBase PowerRAG API 的实际通信:

#### 核心方法

**`get_chat_completions`** - 流式获取聊天补全响应:

1. **提取用户输入**
   ```python
   for m in request_input.messages or []:
       if (m.role or "").lower() == "user":
           prompt = m.content or prompt
   ```
   遍历消息历史,提取最后一条用户消息

2. **构建请求**
   ```python
   url = f"{self.cfg.base_url}/{self.cfg.ai_database_name}/collections/{self.cfg.collection_id}/chat"
   payload = {"stream": True, "jsonFormat": True, "content": prompt}
   ```

3. **处理 SSE 流式响应**
   ```python
   async for raw in resp.content:
       line = raw.decode("utf-8", errors="ignore").strip()
       if line.startswith("data:"):
           data_json = json.loads(data_str)
           chunk = data_json.get("answer", {}).get("content")
           # 生成增量消息
           yield LLMResponseMessageDelta(...)
   ```

4. **错误处理**
   - HTTP 错误:返回友好错误消息
   - 异常捕获:记录日志并返回失败信息

---

### 3. **扩展类 (`OceanBasePowerRAGExtension`)**

继承自 `AsyncLLM2BaseExtension`,实现 TEN 框架的生命周期管理:

#### 生命周期方法

**`on_start`** - 启动时初始化:
```python
# 1. 加载配置
cfg_json, _ = await self.ten_env.get_property_to_json("")
self.config = OceanBaseLLM2Config.model_validate_json(cfg_json)

# 2. 验证必需字段
missing = [key for key in ("base_url", "api_key", ...) if not getattr(self.config, key)]

# 3. 创建客户端
self.client = OceanBaseChatClient(async_ten_env, self.config)
```

**`on_stop`** - 停止时清理资源:
```python
if self.client:
    await self.client.aclose()  # 关闭 HTTP 会话
```

#### 核心功能方法

**`on_call_chat_completion`** - 处理聊天请求:
```python
def on_call_chat_completion(self, async_ten_env, request_input):
    return self.client.get_chat_completions(request_input)
```
直接委托给客户端处理

**`on_retrieve_prompt`** - 获取提示词:
```python
async def on_retrieve_prompt(self, async_ten_env, request):
    return LLMResponseRetrievePrompt(prompt="")  # PowerRAG 不使用系统提示词
```

---

## 工作流程

1. **初始化阶段**
   - 加载配置(API 地址、密钥、数据库信息)
   - 验证配置完整性
   - 创建 HTTP 客户端

2. **请求处理**
   - 接收 `LLMRequest`
   - 提取用户消息
   - 发送 PUT 请求到 PowerRAG API
   - 解析 SSE 流式响应

3. **响应生成**
   - 发送多个 `LLMResponseMessageDelta`(增量内容)
   - 最后发送 `LLMResponseMessageDone`(完成标记)

4. **清理阶段**
   - 关闭 HTTP 会话
   - 释放资源

---

## 关键特性

- **流式响应**:使用 `AsyncGenerator` 逐块返回内容
- **错误容错**:完善的异常处理和日志记录
- **资源管理**:自动管理 aiohttp 会话的生命周期
- **LLM2 协议兼容**:遵循 TEN 框架的 LLM2 接口规范

这个实现允许 TEN 代理系统通过 OceanBase 的 RAG 能力增强 LLM 响应。