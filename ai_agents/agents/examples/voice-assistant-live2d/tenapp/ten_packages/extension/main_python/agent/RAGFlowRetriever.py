from typing import List, Dict, Any, Optional
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
import requests
import json
from pydantic import Field


class RAGFlowRetriever(BaseRetriever):
    """基于 RAGFlow API 的自定义检索器"""
    
    # 关键修复：将普通属性定义为 Pydantic 模型字段
    base_url: str = Field(..., description="RAGFlow API 基础地址")
    api_token: str = Field(..., description="访问 RAGFlow 的 API 令牌")
    kb_id: List[str] = Field(..., description="知识库 ID 列表")
    k: int = Field(5, description="默认返回结果数量")  # 默认返回结果数量
    client: Optional['RAGFlowRetrievalClient'] = Field(None, description="RAGFlow 检索客户端实例")
    
    def __init__(
        self, 
        base_url: str,
        api_token: str, 
        kb_id: List[str],
        k: int = 5,** kwargs
    ):
        super().__init__(
            base_url=base_url,
            api_token=api_token,
            kb_id=kb_id,
            k=k,
            **kwargs
        )  # 显式传递参数给父类
        
        # 初始化客户端
        self.client = RAGFlowRetrievalClient(
            base_url=self.base_url,
            api_token=self.api_token
        )
    
    
    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        """执行检索并返回相关文档"""
        try:
            # 调用 RAGFlow 检索 API
            result = self.client.retrieval(
                kb_id=self.kb_id,
                question=query,
                k=self.k
            )
            
            # 解析响应并转换为 Document 对象
            documents = []
            
            if result.get("code") == 0 and "data" in result:
                chunks = result["data"].get("chunks", [])
                
                for chunk in chunks:
                    # 创建 Document 对象
                    doc = Document(
                        page_content=chunk.get("content_with_weight", ""),
                        metadata={
                            "chunk_id": chunk.get("chunk_id"),
                            "doc_id": chunk.get("doc_id"),
                            "doc_name": chunk.get("docnm_kwd", ""),
                            "kb_id": chunk.get("kb_id"),
                            "similarity": chunk.get("similarity", 0.0),
                            "term_similarity": chunk.get("term_similarity", 0.0),
                            "vector_similarity": chunk.get("vector_similarity", 0.0),
                            "source": "RAGFlow"
                        }
                    )
                    documents.append(doc)
            
            return documents
            
        except Exception as e:
            run_manager.on_retriever_error(e)
            return []


class RAGFlowRetrievalClient:
    """RAGFlow 检索客户端"""
    
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def retrieval(
        self, 
        kb_id: List[str], 
        question: str,
        k: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """执行检索请求"""
        url = f"{self.base_url}/retrieval"
        
        payload = {
            "kb_id": kb_id,
            "question": question,
            "k": k,
            **kwargs
        }
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"RAGFlow API 请求失败: {str(e)}")
        except json.JSONDecodeError as e:
            raise Exception(f"RAGFlow API 响应解析失败: {str(e)}")


# 使用示例
def create_ragflow_retriever():
    """创建 RAGFlow 检索器实例"""
    retriever = RAGFlowRetriever(
        base_url="http://192.168.8.231:9380/v1/api/",
        api_token="ragflow-ZjN2M5MTY2NWJjMzExZjA5Yjg0OTNlMz",
        kb_id=["02a723a85bc411f09b8493e33f5c065d"],
        k=5  # 返回前5个相关结果
    )
    return retriever

# 测试检索器
if __name__ == "__main__":
    retriever = create_ragflow_retriever()
    
    # 测试检索
    query = "制造工程体验讲座是谁主讲的？"
    docs = retriever.invoke(query)
    
    print(f"查询: {query}")
    print(f"找到 {len(docs)} 个相关文档:")
    
    for i, doc in enumerate(docs, 1):
        print(f"\n--- 文档 {i} ---")
        print(f"内容: {doc.page_content[:500]}...")
        print(f"相似度: {doc.metadata.get('similarity', 0.0):.4f}")
        print(f"文档名: {doc.metadata.get('doc_name', 'Unknown')}")