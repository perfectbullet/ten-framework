import requests
import json
from typing import List, Optional, Dict, Any


class RAGFlowRetrievalClient:
    """RAGFlow检索API客户端"""

    def __init__(self, base_url: str, api_token: str):
        """
        初始化客户端

        Args:
            base_url: API基础URL，例如 "http://localhost:5000"
            api_token: API Token (从APIToken表获取)
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }

    def retrieval(
            self,
            kb_id: List[str],
            question: str,
            doc_ids: Optional[List[str]] = None,
            page: int = 1,
            page_size: int = 10,
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
            print(f"📤 Request URL: {url}")
            print(f"📤 Request Headers: {json.dumps(self.headers, indent=2)}")
            print(f"📤 Request Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            print(f"\n📥 Response Status: {response.status_code}")

            # 解析响应
            result = response.json()
            print(f"📥 Response: {json.dumps(result, indent=2, ensure_ascii=False)}")

            return result

        except requests.exceptions.RequestException as e:
            print(f"❌ Request Error: {e}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            print(f"❌ JSON Decode Error: {e}")
            print(f"Response Text: {response.text}")
            return {"error": "Invalid JSON response"}


def test_basic_retrieval():
    """基础检索测试"""
    print("=" * 60)
    print("🧪 Test 1: Basic Retrieval")
    print("=" * 60)

    # 配置客户端
    client = RAGFlowRetrievalClient(
        base_url="http://192.168.8.231:9380/v1/api/",  # 修改为您的实际URL
        api_token="ragflow-ZjN2M5MTY2NWJjMzExZjA5Yjg0OTNlMz"  # 修改为您的实际Token
    )

    # 执行检索
    result = client.retrieval(
        kb_id=["02a723a85bc411f09b8493e33f5c065d"],  # 修改为实际的知识库ID
        question="制造工程体验讲座是哪个老师主讲"
    )

    return result


def parse_and_display_results(result: Dict[str, Any]):
    """解析并美化显示结果"""
    print("\n" + "=" * 80)
    print("📊 检索结果解析")
    print("=" * 80)

    # 检查响应状态
    if result.get("code") != 0:
        print(f"❌ 错误: {result.get('message', '未知错误')}")
        print(f"错误代码: {result.get('code', 'N/A')}")
        return

    # 解析数据
    data = result.get("data", {})
    chunks = data.get("chunks", [])
    doc_aggs = data.get("doc_aggs", [])
    total = data.get("total", 0)

    # 显示统计信息
    print(f"✅ 检索成功!")
    print(f"📄 总匹配数: {total}")
    print(f"📦 返回片段数: {len(chunks)}")
    print(f"📚 涉及文档数: {len(doc_aggs)}")

    # 显示文档统计
    if doc_aggs:
        print("\n" + "-" * 80)
        print("📚 文档分布:")
        for agg in doc_aggs:
            print(f"  • {agg.get('doc_name', 'N/A')}")
            print(f"    ├─ 文档ID: {agg.get('doc_id', 'N/A')}")
            print(f"    └─ 片段数: {agg.get('count', 0)}")

    # 显示详细片段信息
    if chunks:
        print("\n" + "-" * 80)
        print("🔍 Top 检索片段:")
        for idx, chunk in enumerate(chunks[:5], 1):  # 显示前5个
            print(f"\n【片段 {idx}】")
            print(f"├─ 文档名: {chunk.get('docnm_kwd', 'N/A')}")
            print(f"├─ 片段ID: {chunk.get('chunk_id', 'N/A')}")
            print(f"├─ 综合相似度: {chunk.get('similarity', 0):.4f}")
            print(f"├─ 向量相似度: {chunk.get('vector_similarity', 0):.4f}")
            print(f"├─ 关键词相似度: {chunk.get('term_similarity', 0):.4f}")

            # 显示内容(优先使用带权重的内容)
            content = chunk.get('content_with_weight') or chunk.get('content_ltks', '')
            if content:
                # 截取前200字符并清理格式
                display_content = content.replace('\n', ' ').strip()[:200]
                print(f"└─ 内容预览:")
                print(f"   {display_content}...")
            else:
                print(f"└─ 内容预览: (无内容)")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    """
    主测试函数

    使用前请修改：
    1. base_url: 您的API服务地址
    2. api_token: 您的有效API Token
    3. kb_id: 您的实际知识库ID
    """

    print("🚀 RAGFlow Retrieval API Test Client")
    print(f"📅 Current Date: 2025-11-18 10:26:43 UTC")
    print(f"👤 User: perfectbullet")
    print("=" * 60)

    # 运行测试
    try:
        # 测试1: 基础检索
        result1 = test_basic_retrieval()
        parse_and_display_results(result1)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
