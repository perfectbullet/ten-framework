"""
Text intent validator for semantic validation.

This module validates ASR (Automatic Speech Recognition) text by:
Detecting whether the text represents a meaningful question or just noise.

Uses OpenAI Chat Completions API with the same prompt and return format as
classify_queries.py.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI


def _get_api_key() -> str:
    """Get API key from OPENAI_API_KEY environment variable."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is not set. "
            "Please configure it in .env file."
        )
    return api_key


def _get_base_url() -> str:
    """Get base URL from OPENAI_BASE_URL environment variable."""
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")


def _get_model() -> str:
    """Get model name from OPENAI_MODEL environment variable."""
    model = os.environ.get("OPENAI_MODEL")
    if not model:
        raise ValueError(
            "OPENAI_MODEL environment variable is not set. "
            "Please configure it in .env file."
        )
    return model


# Module constants
DEFAULT_API_KEY = _get_api_key()
DEFAULT_BASE_URL = _get_base_url()
DEFAULT_MODEL = _get_model()
DEFAULT_TIMEOUT = 5.0

# Copied from classify_queries.py — same prompt and return format
SYSTEM_PROMPT = """你是一个语音助手 query 分类器。你的任务是对每条用户输入进行分类。

分类标准：

**real_question（真实问题）**：用户有明确意图获取信息、求解问题或请求讲解的内容。包括但不限于：
- 知识问答（如"什么是等差数列？"、"什么是失蜡铸造"）
- 数学求解（如"求不等式 x²-5x+6<0 的解"、"二项式定理的公式是什么？"）
- 请求讲解（如"帮我讲解一下集合的概念"）
- 天气查询（如"北京今天天气怎么样？"）
- 常识问题（如"一加一等于几？"、"中国的十大开国元帅有哪些人？"）
- 英语问题（如英文提问的语法、知识类问题）
- 有明确学科或知识领域的完整提问

**noise（噪声）**：不构成有效提问的内容。包括但不限于：
- 旁人对话（如"对，就是那个，或者边的那俩"、"你看那个歪点那个活跃时间"）
- ASR 碎片/不完整句子（如"函数，我们20"、"等一下公式"）
- 重复填充词（如"我知道了"重复多遍、"你你你你你"重复多遍）
- 跟别人说话（如"打断一下，我拿一下"、"等开会的时候再说吧"）
- 设备/技术调试对话（如"唤醒后几秒后提问才有效"、"这个还是得去求一下"）
- 纯感叹或情绪表达（如"真的假的?"、"你是不是有病啊?"）
- 无明确问题意图的短语（如"查看一下"、"麻烦一下"、"挑战一下"）

请对输入的 query 进行分类，返回 `real_question` 或 `noise`，不要返回其他内容。
"""

# Common noise words that can be filtered without LLM call
COMMON_NOISE_WORDS = {
    "um",
    "uh",
    "ah",
    "er",
    "hm",
    "hmm",
    "mm",
    "嗯",
    "啊",
    "呃",
    "唔",
    "对",
    "好",
}


class TextIntentValidator:
    """
    Text intent validator using OpenAI Chat Completions API.

    Uses the same prompt and return format as classify_queries.py.
    """

    def __init__(
        self,
        api_key: str = DEFAULT_API_KEY,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize TextIntentValidator.

        Args:
            api_key: OpenAI API key
            base_url: OpenAI API base URL
            model: Model name to use for validation
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: Optional[AsyncOpenAI] = None

    async def _get_client(self) -> AsyncOpenAI:
        """Get or create lazy-initialized AsyncOpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close OpenAI client and clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None

    async def is_meaningful(self, text: str) -> tuple[bool, float, str]:
        """
        Check if text is meaningful or noise.

        Calls OpenAI Chat Completions API with the same prompt as
        classify_queries.py, parses the JSON result, and returns whether
        the label is "real_question".

        Error handling strategy: On any error, return True (meaningful) to
        avoid filtering valid user input.

        Args:
            text: The text to validate

        Returns:
            A tuple containing:
                - is_meaningful: Whether the text is a real question
                - elapsed_time: Total time spent on validation (seconds)
                - raw_response: The raw LLM response (for debugging)
        """
        # Handle empty or whitespace-only input
        if not text or len(text.strip()) == 0:
            return False, 0.0, "empty"

        # Fast path: filter common noise words without LLM call
        text_lower = text.strip().lower()
        if text_lower in COMMON_NOISE_WORDS:
            return False, 0.0, "FAST_PATH_NOISE"

        # Short text filter
        if len(text_lower) <= 2:
            return False, 0.0, "FAST_PATH_NOISE"

        # "打断一下" fast path
        if "打断一下" in text_lower:
            return True, 0.0, "FAST_PATH_YES"

        start_time = time.time()
        try:
            client = await self._get_client()

            user_message = f"请对以下 query 分类：\n\n{text}"

            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                num_predict=10,
            )  # type: ignore

            total_elapsed = (time.time() - start_time) * 1000

            # Parse the JSON result — same format as classify_queries.py
            content = response.choices[0].message.content.strip()
            print(content)
            # Extract JSON (may be wrapped in markdown code block)
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            results = json.loads(content)
            label = results[0]["label"]
            is_meaningful = label == "real_question"

            return is_meaningful, total_elapsed, content

        except asyncio.TimeoutError:
            total_elapsed = time.time() - start_time
            return True, total_elapsed, "TIMEOUT_DEFAULT_YES"
        except Exception as e:
            total_elapsed = time.time() - start_time
            return True, total_elapsed, f"ERROR: {e}"


# Test function for standalone testing
async def test_text_intent_validator():
    """
    Test the TextIntentValidator with sample inputs (English + Chinese).

    Run this module directly to test:
        python -m agent.text_intent_validator
    """
    validator = TextIntentValidator()

    # Load test cases from classification_results.json
    script_dir = Path(__file__).parent
    results_file = script_dir / "classification_results.json"
    with open(results_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build test cases: (query, expected_is_meaningful)
    test_cases = []
    for item in data["results"]:
        expected = item["label"] == "real_question"
        test_cases.append((item["query"], expected))

    print("=" * 70)
    print(
        f"Testing TextIntentValidator - {len(test_cases)} cases from classification_results.json"
    )
    print("=" * 70)

    results = []
    for text, expected_meaningful in test_cases:
        is_meaningful, elapsed, raw_response = await validator.is_meaningful(text)

        # Check if result matches expectation
        status = "✓" if is_meaningful == expected_meaningful else "✗"

        results.append(
            {
                "text": text,
                "is_meaningful": is_meaningful,
                "expected": expected_meaningful,
                "elapsed": elapsed,
                "raw_response": raw_response,
                "status": status,
            }
        )

        # Print result
        print(f"{status} '{text[:40]}' -> {is_meaningful} ({elapsed:.3f}s)")

    # Print summary statistics
    print("=" * 70)
    _print_summary_stats(results)
    print("=" * 70)

    await validator.close()


def _print_summary_stats(results: list[dict]) -> None:
    """
    Print summary statistics for test results.

    Args:
        results: List of test result dictionaries
    """
    correct = sum(1 for r in results if r["status"] == "✓")
    total = len(results)
    accuracy = correct / total * 100
    avg_time = sum(r["elapsed"] for r in results) / total

    print(f"Accuracy: {correct}/{total} ({accuracy:.1f}%)")
    print(f"Average response time: {avg_time:.3f}s")

    # Separate statistics for noise vs meaningful text
    noise_times = [r["elapsed"] for r in results if not r["is_meaningful"]]
    meaningful_times = [r["elapsed"] for r in results if r["is_meaningful"]]

    if noise_times:
        noise_avg = sum(noise_times) / len(noise_times)
        print(f"Noise avg time: {noise_avg:.3f}s")
    if meaningful_times:
        meaningful_avg = sum(meaningful_times) / len(meaningful_times)
        print(f"Meaningful avg time: {meaningful_avg:.3f}s")


if __name__ == "__main__":
    asyncio.run(test_text_intent_validator())
