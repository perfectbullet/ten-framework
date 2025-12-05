# RAG 检索集成方案

要在现有架构中添加 RAG(检索增强生成)能力,需要在 LLM 请求前插入文档检索步骤。以下是推荐的实现方案:

---

## 方案一:在 `_send_to_llm` 前添加检索层

修改 `llm_exec.py` 中的 `_send_to_llm` 方法:

```python
async def _send_to_llm(
    self, ten_env: AsyncTenEnv, new_message: LLMMessage
) -> None:
    """发送消息到 LLM 并处理流式响应"""
    
    # ===== 新增:RAG 检索 =====
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
    
    # 原有逻辑:合并上下文
    messages = self.contexts.copy()
    messages.append(new_message)
    
    # ... 后续代码不变
```

添加检索方法:

```python
async def _retrieve_relevant_docs(self, query: str) -> list[str]:
    """
    调用向量数据库检索相关文档
    
    可选实现:
    1. 调用 OceanBase PowerRAG API
    2. 调用 Pinecone/Milvus 等向量库
    3. 调用本地 FAISS 索引
    """
    try:
        # 示例:通过 TEN 命令调用 RAG Extension
        result, _ = await _send_cmd(
            self.ten_env,
            "retrieve",  # 新增命令
            "rag_extension",  # 目标扩展
            {"query": query, "top_k": 3}
        )
        
        if result.get_status_code() == StatusCode.OK:
            docs_json, _ = result.get_property_to_json("documents")
            docs = json.loads(docs_json)
            return [doc["content"] for doc in docs]
    except Exception as e:
        self.ten_env.log_error(f"RAG retrieval failed: {e}")
    
    return []

def _enrich_with_context(self, query: str, docs: list[str]) -> str:
    """将检索结果格式化为提示词"""
    context = "\n\n".join([f"[文档 {i+1}]\n{doc}" for i, doc in enumerate(docs)])
    return f"""参考以下文档回答问题:

{context}

用户问题: {query}"""
```

---

## 方案二:创建独立的 RAG Extension

在 `ten_packages/extension/` 下新建 `rag_retriever/`:

```python
# rag_retriever/extension.py
from ten import AsyncExtension, AsyncTenEnv, Cmd, CmdResult, StatusCode
import aiohttp
import json

class RAGRetrieverExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.vector_store_url = None
        self.collection_name = None
    
    async def on_start(self, async_ten_env: AsyncTenEnv) -> None:
        # 加载配置
        self.vector_store_url = await async_ten_env.get_property_string("vector_store_url")
        self.collection_name = await async_ten_env.get_property_string("collection_name")
    
    async def on_cmd(self, async_ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        if cmd.get_name() == "retrieve":
            query = cmd.get_property_string("query")
            top_k = cmd.get_property_int("top_k") or 3
            
            # 调用向量数据库
            docs = await self._query_vector_store(query, top_k)
            
            # 返回结果
            result = CmdResult.create(StatusCode.OK, cmd)
            result.set_property_from_json("documents", json.dumps(docs))
            await async_ten_env.return_result(result)
    
    async def _query_vector_store(self, query: str, top_k: int) -> list[dict]:
        """查询向量数据库"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.vector_store_url}/search",
                json={"query": query, "top_k": top_k, "collection": self.collection_name}
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("documents", [])
        return []
```

配置文件 `rag_retriever/property.json`:

```json
{
  "_ten": {
    "type": "extension",
    "name": "rag_retriever",
    "version": "0.1.0"
  },
  "vector_store_url": "http://localhost:19530",
  "collection_name": "my_docs"
}
```

---

## 方案三:集成 OceanBase PowerRAG

如果要复用已有的 OceanBase 能力,修改 `extension.py`:

```python
# 在 OceanBaseChatClient 中添加检索方法
async def retrieve_documents(
    self, 
    query: str, 
    top_k: int = 3
) -> list[dict]:
    """仅检索文档,不生成回复"""
    url = f"{self.cfg.base_url}/{self.cfg.ai_database_name}/collections/{self.cfg.collection_id}/search"
    
    async with self.session.post(
        url,
        headers={"Authorization": f"Bearer {self.cfg.api_key}"},
        json={"query": query, "top_k": top_k}
    ) as resp:
        if resp.status == 200:
            result = await resp.json()
            return result.get("documents", [])
    return []
```

在 `extension.py` 中添加新命令处理:

```python
async def on_cmd(self, async_ten_env: AsyncTenEnv, cmd: Cmd) -> None:
    cmd_name = cmd.get_name()
    
    if cmd_name == "retrieve":  # 新增检索命令
        query = cmd.get_property_string("query")
        docs = await self.client.retrieve_documents(query)
        
        result = CmdResult.create(StatusCode.OK, cmd)
        result.set_property_from_json("documents", json.dumps(docs))
        await async_ten_env.return_result(result)
    # ... 原有逻辑
```

---

## 推荐实现步骤

1. **选择方案一**(最简单):
   - 直接在 `llm_exec.py` 中添加检索逻辑
   - 复用 OceanBase Extension 的检索能力

2. **配置 graph.json**:
   ```json
   {
     "nodes": [
       {"type": "extension", "name": "agent"},
       {"type": "extension", "name": "llm"},
       {"type": "extension", "name": "oceanbase_powerrag"}
     ],
     "connections": [
       {"extension": "agent", "cmd": ["retrieve"], "dest": "oceanbase_powerrag"}
     ]
   }
   ```

3. **测试流程**:
   - 用户输入 → Agent → RAG 检索 → 注入上下文 → LLM 生成

---

## 关键优化点

- **缓存**:对相同查询缓存检索结果
- **混合检索**:结合关键词 + 向量检索
- **Rerank**:对检索结果重排序提升相关性
- **引用标注**:在回复中标注文档来源

需要更详细的实现或遇到错误可以继续提问。