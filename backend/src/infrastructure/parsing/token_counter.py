"""基于 tiktoken (cl100k_base) 的分块 Token 计数器。"""

from __future__ import annotations

import tiktoken


class TiktokenTokenCounter:
    """使用预加载的编码表统计文本 Token 数量。"""

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        """计算给定文本在 cl100k_base 下的 Token 数量。"""
        return len(self._encoding.encode(text))
