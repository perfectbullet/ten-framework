#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#

"""
句子缓冲区 - 用于流式文本的分句处理

独立于 TEN 运行时，可以在本地 Python 环境中测试。
用于处理 LLM 流式输出，按句末标点提取完整句子，实现边说边播的 TTS 效果。

支持三种分段策略：
1. 句末标点分段（优先级最高）- 在。！？.!? 处切分
2. 字符数限制分段 - 超过最大字符数时强制切分
3. 时间限制分段 - 超过最大等待时间时强制输出
"""

import time


class SentenceBuffer:
    """
    句子缓冲区，用于流式文本的分句处理

    用法:
        buffer = SentenceBuffer(max_length=60, max_time=0.8)

        # 流式输入文本
        sentences = buffer.feed("第一句。第二句")
        # sentences = ["第一句。"]

        more = buffer.feed("还在继续。")
        # more = ["第二句还在继续。"]

        # 获取剩余未完成的内容
        remaining = buffer.flush()

        # 检查超时（适用于定期检查的场景）
        timeout_sentences = buffer.check_timeout()
    """

    # 句末标点符号
    SENTENCE_ENDINGS = "。！？.!?"

    # 次要分隔符（用于强制分段时的优先切分点）
    SECONDARY_DELIMITERS = "，,、；;：:"

    def __init__(self, max_length: int = 300, max_time: float = 1.8):
        """
        初始化缓冲区

        Args:
            max_length: 最大字符数限制，超过此长度将强制分段（0=不限制）
            max_time: 最大等待时间（秒），超过此时间将强制输出（0=不限制）
        """
        self._buffer = []
        self._max_length = max_length
        self._max_time = max_time
        self._last_feed_time = None

    def feed(self, text: str) -> list[str]:
        """
        输入新文本，返回完整的句子列表

        Args:
            text: 新输入的文本片段

        Returns:
            完整句子列表（不包含未完成的部分）
        """
        return self.feed_with_time(text, time.time())

    def feed_with_time(self, text: str, current_time: float) -> list[str]:
        """
        输入新文本（带时间戳），返回完整的句子列表

        Args:
            text: 新输入的文本片段
            current_time: 当前时间戳（秒）

        Returns:
            完整句子列表（不包含未完成的部分）
        """
        if not text:
            return self._check_time_limit(current_time)

        # 记录时间
        if self._last_feed_time is None:
            self._last_feed_time = current_time

        self._buffer.append(text)
        full_text = "".join(self._buffer)

        # 策略0: 如果输入文本长度 >= 8，直接合并缓冲区和输入作为一个句子输出
        if len(text) >= 8:
            self._buffer = []
            self._last_feed_time = current_time
            return [full_text]

        # 策略1: 优先检查句末标点
        sentences, consumed_length = self._split_by_sentence_endings(full_text)
        if sentences:
            self._last_feed_time = current_time
            # 移除已输出的部分
            self._buffer = [full_text[consumed_length:]] if consumed_length < len(full_text) else []
            return sentences

        # 策略2: 检查字符数限制
        if self._max_length > 0 and len(full_text) >= self._max_length:
            result, consumed_length = self._force_split(full_text)
            if result:
                self._last_feed_time = current_time
                self._buffer = [full_text[consumed_length:]] if consumed_length < len(full_text) else []
                return result

        # 策略3: 检查时间限制
        if self._max_time > 0 and self._last_feed_time is not None:
            elapsed = current_time - self._last_feed_time
            if elapsed >= self._max_time and len(full_text) > 0:
                # 时间到了，强制输出所有内容
                self._buffer = []
                self._last_feed_time = current_time
                return [full_text]

        return []

    def _split_by_sentence_endings(self, full_text: str) -> tuple[list[str], int]:
        """
        按句末标点分割文本

        Returns:
            (句子列表, 消耗的字符长度)
        """
        if not full_text:
            return [], 0

        # 分割成多个句子
        sentences = []
        current = ""
        consumed_length = 0

        for char in full_text:
            current += char
            if char in self.SENTENCE_ENDINGS:
                if current.strip():
                    sentences.append(current)
                    consumed_length += len(current)
                current = ""

        # 更新缓冲区为剩余部分
        if consumed_length > 0:
            remain = full_text[consumed_length:]
            return sentences, consumed_length
        else:
            return [], 0

    def _force_split(self, full_text: str) -> tuple[list[str], int]:
        """
        强制分割文本（在次要分隔符处优先）

        Args:
            full_text: 完整文本

        Returns:
            (分割后的句子列表, 消耗的字符长度)
        """
        if not full_text:
            return [], 0

        # 优先在次要分隔符处切分
        best_split_pos = -1
        for i, char in enumerate(full_text):
            if char in self.SECONDARY_DELIMITERS:
                best_split_pos = i

        if best_split_pos > 0:
            # 在次要分隔符处切分
            sentence = full_text[:best_split_pos + 1]
            return [sentence] if sentence.strip() else [], best_split_pos + 1

        # 如果没有次要分隔符，直接在中间切分（避免太长）
        if len(full_text) > 20:
            mid = len(full_text) // 2
            # 尽量在空格处切分
            space_pos = full_text.rfind(" ", 0, mid + 10)
            if space_pos > 0:
                sentence = full_text[:space_pos + 1]
                return [sentence] if sentence.strip() else [], space_pos + 1

        # 实在没办法，全部输出
        return [full_text] if full_text.strip() else [], len(full_text)

    def _check_time_limit(self, current_time: float) -> list[str]:
        """检查时间限制，返回需要强制输出的内容"""
        if not self._max_time or self._last_feed_time is None:
            return []

        elapsed = current_time - self._last_feed_time
        if elapsed < self._max_time:
            return []

        # 时间超限，强制输出缓冲区内容
        full_text = "".join(self._buffer)
        if full_text:
            self._buffer = []
            self._last_feed_time = current_time
            return [full_text]
        return []

    def check_timeout(self, current_time: float | None = None) -> list[str]:
        """
        检查是否超时，用于定期检查（如在外部循环中调用）

        Args:
            current_time: 当前时间戳（秒），如果为 None 则使用 time.time()

        Returns:
            如果超时则返回缓冲内容，否则返回空列表
        """
        if current_time is None:
            current_time = time.time()
        return self._check_time_limit(current_time)

    def flush(self) -> str:
        """
        清空缓冲区，返回所有剩余内容

        Returns:
            缓冲区中剩余的文本
        """
        result = "".join(self._buffer)
        self._buffer = []
        self._last_feed_time = None
        return result

    def is_empty(self) -> bool:
        """
        检查缓冲区是否为空

        Returns:
            True 如果缓冲区为空，否则 False
        """
        return len(self._buffer) == 0 or all(not s for s in self._buffer)
