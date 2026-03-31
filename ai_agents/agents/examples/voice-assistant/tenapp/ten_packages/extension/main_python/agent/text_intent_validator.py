"""
Text intent validator for semantic validation and text correction.

This module validates ASR (Automatic Speech Recognition) text by:
1. Detecting whether the text represents a meaningful question or just noise
2. Correcting common ASR errors (typos, word concatenation, etc.)

The validation uses a two-stage approach:
- Stage 1: Fast noise detection (minimal tokens needed)
- Stage 2: Text correction (only if text is meaningful)

This design optimizes for both speed and accuracy, avoiding the cost
of running correction on text that would be filtered out anyway.
"""
import asyncio
import time
from typing import Optional

import httpx


# Module constants
DEFAULT_BASE_URL = "http://192.168.8.233:11434"
DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_TIMEOUT = 5.0

# Common noise words that can be filtered without LLM call
COMMON_NOISE_WORDS = {
    "um", "uh", "ah", "er", "hm", "hmm", "mm",
    "嗯", "啊", "呃", "唔", "对", "好"
}


class TextIntentValidator:
    """
    Text intent validator using Ollama LLM for semantic validation.

    Uses two-stage validation for efficiency:
    1. Noise check (fast, minimal output)
    2. Correction (only if text is meaningful)

    This approach avoids expensive correction on text that would be
    filtered as noise anyway.
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
        """Get or create lazy-initialized HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client and clean up resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_check_prompt(self, text: str) -> str:
        """
        Build prompt for stage 1: noise detection.

        Returns YES/NO based on whether text is meaningful. This prompt
        is designed for fast evaluation with minimal token output.

        Args:
            text: The text to evaluate

        Returns:
            A prompt string for the LLM to evaluate noise
        """
        return f"""你是一个ASR文本验证助手。请判断给定文本是否有意义。

回答 "NO" 的条件（满足任一即为噪音）：
1. 单词重复：同一词语连续重复，如"这个这个"、"那个那个"、"然后然后"、"对对对"、"就是就是"、"嗯嗯"、"啊啊"
2. 纯填充词/迟疑声："um", "uh", "嗯", "啊", "呃", "唔", "er", "ah"
3. 单独的简单问候（仅一个词）："hello", "你好", "hi", "hey"
4. 无意义短句："你说", "我问", "我之前", "之前不是", "应该是", "对", "对吧", "你在一", "开始", "就是", "以后"
5. 说话停顿/继续："然后呢", "所以呢", "就是说", "以后呢", "就是说这个", "那个呢"
6. 表达确认但不完整："对对对", "可以可以", "是的是的", "应该会", "好的好的"
7. 表达状态或感受："我觉得应该是", "我之前用过", "你看看", "你也行", "你觉得", "我感觉"
8. 说话中断/不完整："开始的勇气", "然后我以后", "那最后最后", "开始", "就是", "以后"
9. 闲聊短句："你说什么", "我问你", "我知道", "以后呢，在这个广告吗？"
10. 单独的粘连单词："yourname"（只有一个词）

回答 "YES" 的条件（满足以下任一标准即可）：
1. 完整的问题：有明确的疑问语气或问号，如"今天天气怎么样?"、"讲个笑话"、"What's the weather like?"
2. 明确的请求：有明确的请求意图，如"你能帮我吗?"、"我想听音乐"、"Play some music"、"Help me"
3. 具体的命令：有明确的命令意图，如"把一元二次方程讲一下"
4. 问候+完整内容：问候后面有完整的问题或请求，如"你好，今天天气怎么样?"、"Hello, how are you?"
5. 包含实际内容的英文粘连词："what'syourname"、"howareyou"、"hello， how areyou"
6. 包含ASR错误但有明确意图："¥12次方程"、"2次方程"（虽然识别错误，但语义明确）
7. 用怎么样开头的，如： 如"怎么样xxx", 如"怎么样xxx，不犯法",
判断原则：
- 如果文本包含明确的语义意图（即使有ASR错误），回答 "YES"
- 英文粘连词如果有实际含义，回答 "YES"；单独一个无意义词回答 "NO"
- 优先识别真正的噪音（重复、填充词、不完整表达），不要误判有实际内容的文本

请只回答 "YES" 或 "NO"，不要添加任何其他文字。

待分析文本: "{text}"

回答: """

    def _build_correction_prompt(self, text: str) -> str:
        """
        Build prompt for stage 2: text correction.

        Corrects ASR errors in meaningful text. This prompt is more
        expensive but only runs for text that passed the noise check.

        Args:
            text: The text to correct

        Returns:
            A prompt string for the LLM to correct the text
        """
        return f"""你是一个ASR文本纠错助手。你的任务是纠正文本中的ASR识别错误。

纠错规则:
1. 中文错别字识别：
   - "¥12" → "一元二次"
   - "2次方程" → "二次方程"
   - "12次方程" → "二次方程"（注意：¥符号可能被误识别为1）
   - "12次方程组" → "二次方程组" 或 "一元二次方程组"

2. 英文单词粘连：
   - "what'syourname" → "what's your name"
   - "yourname" → "your name"（即使是单独一个粘连词也要纠正）
   - "howareyou" → "how are you"

3. 英文标点修正：
   - "hello， how areyou" → "hello, how are you"（中文逗号改为英文逗号，粘连分开）
   - 将中文标点（，。、）改为对应的英文标点（,.?）

4. 语言保持：
   - 纠正时要保持文本的原语言类型
   - 英文文本纠正后仍应是英文
   - 中文文本纠正后仍应是中文

5. 纠错原则：
   - 如果文本没有明显错误，请原样返回文本
   - 保持原意不变，只纠正明显的ASR错误
   - 纠正后的文本应该语法正确、标点规范
   - 对于粘连的英文单词，务必正确分割

待纠错文本: "{text}"

请直接输出纠正后的文本，不要添加任何解释、引号或额外说明: """

    async def is_meaningful(self, text: str) -> tuple[bool, float, str, Optional[str]]:
        """
        Check if text is meaningful or noise, with optional text correction.

        Uses two-stage validation for efficiency:
        1. Fast noise check (YES/NO, minimal tokens)
        2. Correction only if text is meaningful (more expensive)

        Error handling strategy: On any error, return True (meaningful) to
        avoid filtering valid user input. This is safer than defaulting to
        filtering as noise, which would frustrate users.

        Args:
            text: The text to validate and correct

        Returns:
            A tuple containing:
                - is_meaningful: Whether the text passed the noise check
                - elapsed_time: Total time spent on validation (seconds)
                - raw_response: The raw LLM response for stage 1 (for debugging)
                - corrected_text: The corrected text, or None if uncorrected
        """
        # Handle empty or whitespace-only input
        if not text or len(text.strip()) == 0:
            return False, 0.0, "", None

        # Fast path: filter common noise words without LLM call
        text_lower = text.strip().lower()
        if text_lower in COMMON_NOISE_WORDS:
            return False, 0.0, "FAST_PATH_NOISE", None

        # 短文本被过滤掉
        if len(text_lower) <= 2:
            return False, 0.0, "FAST_PATH_NOISE", None

        # 短文本被过滤掉
        if '打断一下' in text_lower:
            return True, 0.0, "FAST_PATH_NOISE", text_lower

        total_elapsed = 0.0

        # Stage 1: Noise detection
        start_time = time.time()
        try:
            client = await self._get_client()
            prompt = self._build_check_prompt(text)

            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 2,  # Minimal tokens for YES/NO
                        "temperature": 0.1,
                    },
                },
            )

            total_elapsed = time.time() - start_time

            # Process stage 1 response
            if response.status_code != 200:
                return True, total_elapsed, "ERROR_DEFAULT_YES", None

            result = response.json()
            response_text = result.get("response", "").strip().upper()
            is_meaningful = response_text.startswith("YES")

            # Stage 2: Text correction (only if meaningful)
            corrected_text = None
            if is_meaningful:
                corrected_text = await self._correct_text(client, text)
                total_elapsed += self._last_correction_elapsed

            return is_meaningful, total_elapsed, response_text, corrected_text

        except asyncio.TimeoutError:
            return True, total_elapsed, "TIMEOUT_DEFAULT_YES", None
        except Exception as e:
            return True, total_elapsed, f"ERROR: {e}", None

    # Track elapsed time for correction stage
    _last_correction_elapsed: float = 0.0

    async def _correct_text(
        self,
        client: httpx.AsyncClient,
        text: str,
    ) -> Optional[str]:
        """
        Correct ASR errors in meaningful text.

        Args:
            client: The HTTP client to use
            text: The text to correct

        Returns:
            Corrected text, or None if no correction was needed
        """
        start_time = time.time()
        correction_prompt = self._build_correction_prompt(text)

        response = await client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": correction_prompt,
                "stream": False,
                "options": {
                    "num_predict": 25,
                    "temperature": 0.1,
                },
            },
        )

        self._last_correction_elapsed = time.time() - start_time

        if response.status_code != 200:
            return None

        result = response.json()
        corrected_text = result.get("response", "").strip()

        # Return None if no correction was needed (text unchanged)
        return None if corrected_text == text else corrected_text


# Test function for standalone testing
async def test_text_intent_validator():
    """
    Test the TextIntentValidator with sample inputs (English + Chinese).

    Run this module directly to test:
        python -m agent.text_intent_validator
    """
    validator = TextIntentValidator()

    # Test cases: (text, expected_is_meaningful, expected_correction)
    test_cases = [
        # Meaningful questions - Complete questions
        ("今天天气怎么样?", True, None),
        ("讲个笑话", True, None),
        ("What's the weather like?", True, None),

        # Meaningful questions - Request type
        ("你能帮我吗?", True, None),
        ("我想听音乐", True, None),
        ("Play some music", True, None),

        # Meaningful questions - Command/learning related
        ("¥12次方程的解法", True, "一元二次方程的解法"),
        ("什么是¥12次方程组", True, "什么是一元二次方程组"),
        ("把一元二次方程讲一下", True, None),

        # Meaningful questions - Greeting + question
        ("你好，今天天气怎么样?", True, None),
        ("Hello, how are you?", True, None),

        # Correction tests
        ("what'syourname", True, "what's your name"),
        ("hello， how areyou", True, "hello， how are you"),
        ("yourname", False, "your name"),  # Single word concatenation, not meaningful

        # Noise cases from actual logs
        ("然后我以后就是就是我现在我现在想", False, None),
        ("然后呢，就是那个会议室有一点", False, None),
        ("开始的勇气。对我就是", False, None),
        ("我说我就不要了", False, None),
        ("你在一", False, None),
        ("之前不是已经已经那个了，就是说", False, None),
        ("然后呢", False, None),

        # Common noise
        ("你好", False, None),  # Standalone greeting
        ("嗯", False, None),
        ("ah", False, None),
        ("嗯嗯", False, None),
        ("然后然后", False, None),
        ("我知道", False, None),
        ("你看看", False, None),
        ("你觉得", False, None),
        ("开始", False, None),
        ("就是", False, None),
    ]

    print("=" * 70)
    print("Testing TextIntentValidator - Two Stage Validation")
    print("=" * 70)

    results = []
    for text, expected_meaningful, expected_correction in test_cases:
        is_meaningful, elapsed, raw_response, corrected_text = await validator.is_meaningful(text)

        # Check if result matches expectation
        status = "✓" if is_meaningful == expected_meaningful else "✗"
        if expected_correction is not None:
            correction_status = "✓" if corrected_text == expected_correction else "✗"
        else:
            correction_status = "-"

        results.append(
            {
                "text": text,
                "is_meaningful": is_meaningful,
                "expected": expected_meaningful,
                "elapsed": elapsed,
                "raw_response": raw_response,
                "status": status,
                "corrected_text": corrected_text,
                "correction_status": correction_status,
            }
        )

        # Print result
        print(f"{status} '{text}' -> {is_meaningful} ({elapsed:.3f}s)")
        if corrected_text and corrected_text != text:
            print(f"  Correction: '{text}' -> '{corrected_text}' {correction_status}")
        elif expected_correction is not None:
            print(f"  Correction: (no change) {correction_status}")

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
