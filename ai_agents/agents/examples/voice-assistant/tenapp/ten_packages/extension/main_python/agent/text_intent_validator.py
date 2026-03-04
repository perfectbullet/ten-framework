"""
Text intent validator for semantic validation.
Detects if ASR text is a meaningful question or just noise.
"""
import asyncio
import time
from typing import Optional

import httpx

# Module constants
DEFAULT_BASE_URL = "http://192.168.8.233:11434"
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_TIMEOUT = 5.0


class TextIntentValidator:
    """
    Text intent validator for semantic validation using Ollama LLM.
    Validates if text is a meaningful interaction or just noise.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize TextIntentValidator.

        Args:
            base_url: Ollama API endpoint URL
            model: Model name to use for validation
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_prompt(self, text: str) -> str:
        """
        Build prompt for semantic validation.

        The prompt asks the model to determine if the text is a meaningful
        question or just noise/meaningless sounds.
        """
        return f"""你是一个ASR文本验证助手。你的任务是判断给定文本是有意义的用户交互意图还是仅仅是噪音。

判断标准:
- 回答 "YES" 如果文本包含有意义的问题、请求、命令或完整的交互意图
- 回答 "NO" 如果文本只是噪音、填充词、简单的问候词或无意义的声音

噪音(NO)的例子:
- 纯填充词/迟疑声: "um", "uh", "ah", "er", "hmm", "嗯", "啊", "呃", "唔"
- Stuttering重复: "the the the", "I I I", "那个那个", "然后然后"
- 简单的问候词（单独使用）: "hello", "hi", "hey", "你好"
- 单个无意义的感叹词: "oh", "ah" 除非有上下文表明在交流

有意义(YES)的例子:

问题类 (QUESTIONS):
- "今天天气怎么样?", "What's the weather like?"
- "what's your name", "what's yourname" (ASR打字错误)
- "讲个笑话", "Tell me a joke"
- "你好吗?", "How are you?"

请求类 (REQUESTS/COMMANDS):
- "你能帮我吗?", "Can you help me?"
- "我想听音乐", "Play some music"

问候+问题组合类 (GREETING + QUESTION):
- "Hello, how are you?"
- "你好，今天天气怎么样?"
- "hello， what's yourname" (混合标点和打字错误，但包含问题)

注意:
- 单独的问候词（如"hello"、"你好"）应返回NO，除非它们是完整问候语的一部分
- 如果文本包含疑问词（what, how, why, when, where, who, 什么, 怎么, 为什么, 哪里），应倾向于YES
- ASR识别中的打字错误、混合标点不应影响判断，应识别其真实意图

待分析文本: "{text}"

回答 (YES/NO):"""

    async def is_meaningful(self, text: str) -> tuple[bool, float, str]:
        """
        Check if text is meaningful or noise.

        Args:
            text: The text to validate

        Returns:
            Tuple of (is_meaningful: bool, elapsed_time: float, raw_response: str)
        """
        if not text or len(text.strip()) == 0:
            return False, 0.0, ""

        # Fast path for very short common noise words (English and Chinese)
        text_lower = text.strip().lower()
        common_noise = {
            "um", "uh", "ah", "er", "hm", "hmm", "mm", "mhm", "uh-huh",
            "嗯", "啊", "呃", "唔", "嗯嗯", "啊啊",
        }
        if text_lower in common_noise:
            return False, 0.0, "FAST_PATH_NOISE"

        # Use Ollama for semantic validation
        start_time = time.time()
        try:
            client = await self._get_client()
            prompt = self._build_prompt(text)

            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 3,  # Only need a few tokens for YES/NO
                        "temperature": 0.1,  # Low temperature for consistent output
                    },
                },
            )

            elapsed = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "").strip().upper()
                # Check if response starts with YES
                is_meaningful = response_text.startswith("YES")
                return is_meaningful, elapsed, response_text
            else:
                # On error, assume meaningful to avoid filtering valid input
                return True, elapsed, "ERROR_DEFAULT_YES"

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            return True, elapsed, "TIMEOUT_DEFAULT_YES"
        except Exception as e:
            elapsed = time.time() - start_time
            # On error, assume meaningful to avoid filtering valid input
            return True, elapsed, f"ERROR_DEFAULT_YES: {e}"


# Test function for standalone testing
async def test_text_intent_validator():
    """
    Test the TextIntentValidator with sample inputs (English + Chinese).
    Run this module directly to test: python -m agent.text_intent_validator
    """
    validator = TextIntentValidator(
        base_url="http://192.168.8.233:11434",
        model="qwen2.5:7b",
        timeout=10.0,
    )

    test_cases = [
        # English test cases
        ("What's the weather like?", True),
        ("Tell me a joke", True),
        ("um", False),
        ("uh-huh", False),
        ("the the the", False),
        ("Hello, how are you?", True),
        ("Can you help me with something?", True),
        ("ah", False),
        ("hmm", False),
        # Chinese test cases
        ("今天天气怎么样?", True),
        ("讲个笑话", True),
        ("你好吗?", True),
        ("你能帮我吗?", True),
        ("嗯", False),
        ("啊", False),
        ("呃", False),
        ("那个那个那个", False),
        ("然后然后", False),
    ]

    print("=" * 70)
    print("Testing TextIntentValidator Semantic Validation (English + Chinese)")
    print("=" * 70)

    results = []
    for text, expected in test_cases:
        is_meaningful, elapsed, raw_response = await validator.is_meaningful(text)
        status = "✓" if is_meaningful == expected else "✗"
        results.append(
            {
                "text": text,
                "is_meaningful": is_meaningful,
                "expected": expected,
                "elapsed": elapsed,
                "raw_response": raw_response,
                "status": status,
            }
        )
        print(f"{status} '{text}' -> {is_meaningful} ({elapsed:.3f}s) [response: {raw_response}]")

    # Summary stats
    print("=" * 70)
    correct = sum(1 for r in results if r["status"] == "✓")
    total = len(results)
    accuracy = correct / total * 100
    avg_time = sum(r["elapsed"] for r in results) / total

    print(f"Accuracy: {correct}/{total} ({accuracy:.1f}%)")
    print(f"Average response time: {avg_time:.3f}s")
    print("=" * 70)

    await validator.close()


async def test_is_meaningful_detailed():
    """
    Detailed test for is_meaningful function.
    Shows raw response from Ollama for each test case.
    """
    validator = TextIntentValidator(
        base_url="http://192.168.8.233:11434",
        model="qwen2.5:7b",
        timeout=10.0,
    )

    print("\n" + "=" * 70)
    print("Detailed Test: is_meaningful() with raw responses")
    print("=" * 70)

    test_texts = [
        # Meaningful questions
        "今天天气怎么样?",
        "What's the weather like?",
        "你好",
        "Hello",
        "hello， what's yourname",
        "讲个笑话",
        # Noise/fillers
        "嗯",
        "啊",
        "呃",
        "um",
        "uh",
        # Edge cases
        "那个那个那个",
        "然后然后",
        "问你"
    ]

    for text in test_texts:
        is_meaningful, elapsed, raw_response = await validator.is_meaningful(text)
        result_str = "✓ 有意义" if is_meaningful else "✗ 噪音"
        print(f"\n文本: '{text}'")
        print(f"结果: {result_str}")
        print(f"耗时: {elapsed:.3f}s")
        print(f"原始回复: {raw_response}")

    print("\n" + "=" * 70)
    await validator.close()


if __name__ == "__main__":
    # Run both tests
    # asyncio.run(test_text_intent_validator())
    asyncio.run(test_is_meaningful_detailed())
