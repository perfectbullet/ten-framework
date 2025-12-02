import json
from typing import List, Optional, Dict, Any

import requests
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama


class RAGFlowRetrievalClient:
    """RAGFlow检索API客户端"""

    def __init__(self, base_url: str, api_token: str, ollama_base_url: str = "http://192.168.8.231:11434",
                 ollama_model: str = "qwen2.5:7b"):
        """
        初始化客户端

        Args:
            base_url: API基础URL,例如 "http://localhost:5000"
            api_token: API Token (从APIToken表获取)
            ollama_base_url: Ollama服务地址
            ollama_model: 使用的本地模型名称
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }

        # 初始化相关性检测模型
        self.llm = ChatOllama(
            model=ollama_model,
            format="json",
            temperature=0,
            base_url=ollama_base_url
        )

        # 定义相关性检测提示模板
        self.relevance_template = PromptTemplate(
            template="""你是一个文档相关性评估员，负责评估检索到的文档与用户问题的相关性。\n 
            以下是检索到的文档： \n\n {context} \n\n
            以下是用户问题： {question} \n
            如果文档包含与用户问题相关的关键词或语义内容，则评为相关。\n
            请给出二元评分 'yes' 或 'no' 来表示文档是否与问题相关。
            返回格式: {{"relevance": "yes"}} 或 {{"relevance": "no"}}""",
            input_variables=["context", "question"],
        )

        self.retrieval_grader = self.relevance_template | self.llm | JsonOutputParser()

    def retrieval(
            self,
            kb_id: List[str],
            question: str,
            doc_ids: Optional[List[str]] = None,
            page: int = 1,
            page_size: int = 3,
            similarity_threshold: float = 0.2,
            vector_similarity_weight: float = 0.3,
            top_k: int = 1024,
            highlight: bool = False,
            keyword: bool = False,
            rerank_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        调用检索接口

        Args:
            kb_id: 知识库ID列表（必需）
            question: 查询问题（必需）
            doc_ids: 文档ID列表（可选）
            page: 页码，默认1
            page_size: 每页大小，默认30
            similarity_threshold: 相似度阈值，默认0.2
            vector_similarity_weight: 向量相似度权重，默认0.3
            top_k: Top K结果数量，默认1024
            highlight: 是否高亮显示，默认False
            keyword: 是否进行关键词提取，默认False
            rerank_id: 重排序模型ID（可选）

        Returns:
            API响应结果
        """
        url = f"{self.base_url}/retrieval"

        payload = {
            "kb_id": kb_id,
            "question": question,
            "page": page,
            "page_size": page_size,
            "similarity_threshold": similarity_threshold,
            "vector_similarity_weight": vector_similarity_weight,
            "top_k": top_k,
            "highlight": highlight,
            "keyword": keyword
        }

        # 添加可选参数
        if doc_ids:
            payload["doc_ids"] = doc_ids
        if rerank_id:
            payload["rerank_id"] = rerank_id

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            # 打印请求信息
            # print(f"📤 Request URL: {url}")
            # print(f"📤 Request Headers: {json.dumps(self.headers, indent=2)}")
            # print(f"📤 Request Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            # print(f"\n📥 Response Status: {response.status_code}")
            # 解析响应
            result = response.json()
            # print(f"retrieval Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

            return result

        except requests.exceptions.RequestException as e:
            print(f"❌ Request Error: {e}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            print(f"❌ JSON Decode Error: {e}")
            print(f"Response Text: {response.text}")
            return {"error": "Invalid JSON response"}

    def retrieve_docs(self, query: str, relevant: bool = True) -> list[str]:
        """
        使用 RAGFlow 的接口检索相关文档
        然后通过相关性检测去掉无用的文档
        Args:
            query: 查询问题
            relevant: 是否只返回相关文档。True=只返回相关文档，False=返回所有文档
        Returns:
            文档内容列表
        """
        try:
            result = self.retrieval(
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
                for idx, chunk in enumerate(chunks, 1):
                    # 获取内容(优先使用带权重的内容)
                    content = chunk.get('content_with_weight') or chunk.get('content_ltks', '')
                    if content:
                        # 如果需要相关性检测
                        if relevant:
                            try:
                                # 调用LLM进行相关性评估
                                relevance_result = self.retrieval_grader.invoke({
                                    "question": query,
                                    "context": content
                                })
                                # 检查相关性评分
                                is_relevant = relevance_result.get("relevance", "no").lower() == "yes"
                                if is_relevant:
                                    docs.append(content)
                                    print(f"✅ 文档块 {idx} 相关性检测通过： {is_relevant}")
                                else:
                                    print(f"❌ 文档块 {idx} 相关性检测未通过： {is_relevant}")
                            except Exception as e:
                                print(f"⚠️ 文档块 {idx} 相关性检测失败: {e}，默认保留")
                                docs.append(content)  # 检测失败时保留文档
                        else:
                            # 不需要相关性检测，直接添加
                            docs.append(content)
            print(f"检索结果: 总共 {len(chunks)} 个文档块，返回 {len(docs)} 个文档块")
            return docs
        except Exception as e:
            print(f"❌ RAGFlow retrieval failed: {e}")
        return []


def demo_retrieve_docs(query):
    """文档检索测试"""
    print("=" * 60)
    print(f"问题: {query}")
    # 配置客户端
    client = RAGFlowRetrievalClient(
        base_url="http://192.168.8.231:9380/v1/api/",  # 修改为您的实际URL
        api_token="ragflow-ZjN2M5MTY2NWJjMzExZjA5Yjg0OTNlMz"  # 修改为您的实际Token，这个token是ragflow的token
    )
    # 执行文档检索
    result_docs = client.retrieve_docs(
        query=query,
        relevant=True
    )
    print(f"Retrieved {len(result_docs)} relevant documents.")

    print("=" * 60)


if __name__ == "__main__":
    """
    主测试函数

    使用前请修改：
    1. base_url: 您的API服务地址
    2. api_token: 您的有效API Token
    3. kb_id: 您的实际知识库ID
    """
    print("=" * 60)

    # 运行测试
    try:
        # 测试1: 基础检索
        demo_retrieve_docs("雕蜡与铸造工艺基本原理")
        demo_retrieve_docs("北京的天气怎么样")
        demo_retrieve_docs("简单介绍一下人工只能")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
