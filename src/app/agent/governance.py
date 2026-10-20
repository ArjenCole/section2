"""Agent 循环治理（与具体循环实现无关，可单独测试）。

对齐 Quotor `langgraph_loop.py` 的五类治理，数值取其验证过的配置：

1. 预算软着陆：时间 / 字符 / 轮数超限 → 注入收尾指令，宽限若干轮后强制结束；
2. 停滞检测：滑动窗口内同签名工具调用重复出现 → 注入纠偏提示；
3. 提前收尾抢救：计划句（“让我…/接下来…”）被当作终答 → 注入纠偏继续；
4. 空 content 重试 + 超长工具结果截断；
5. 瞬时错误退避（429/5xx，尊重 Retry-After）。

另提供从纯文本解析工具调用的兜底（部分端点把 tool_call 内容放进
reasoning_content / content 文本流）。
"""

from __future__ import annotations

import json
import re
import time
from collections import deque

#: 预算：软着陆触发条件（与 Quotor 一致）
BUDGET_SECONDS = 600.0
BUDGET_CHARS = 250_000
BUDGET_ROUNDS = 40
GRACE_ROUNDS = 8

#: 硬保险丝
MAX_ITERATIONS = 50

#: 停滞检测窗口与阈值
STAGNATION_WINDOW = 5
STAGNATION_HITS = 3
STAGNATION_MAX_NUDGES = 2

#: 工具结果超过该长度时截断（防止上下文爆掉）
TOOL_RESULT_LIMIT = 25_000

#: 空 content 重试次数
EMPTY_RETRY_LIMIT = 2

#: 提前收尾抢救次数
PREMATURE_MAX_NUDGES = 3

WRAP_UP_PROMPT = (
    "【预算提醒】本轮对话已接近长度/时间限制。请立即停止新的查询，基于已有工具结果"
    "给出最终回答；如仍有未完成项，在回答里明确列出未完成内容与下一步建议。"
)
REPEAT_NUDGE_PROMPT = (
    "【重复检测】你刚才连续用相同参数调用了同一个工具，结果不会变化。"
    "请换一种做法：检查参数、改用其它查询工具，或基于已有结果直接回答。"
)
PREMATURE_NUDGE_PROMPT = (
    "【继续执行】你还没有给出最终结果。请继续调用所需工具完成任务，"
    "不要只说“接下来会…”。"
)
CANCELLED_PROMPT = (
    "用户取消了该操作。不要重试同一工具；请向用户说明当前状态并询问下一步。"
)
EMPTY_RETRY_PROMPT = "请继续。"

_PREMATURE_FINAL_RE = re.compile(
    r"(让我|接下来|下一步|稍后|我将会|我将|再(搜索|查询|查一下|计算|确认)|"
    r"first,? i will|let me (now )?(search|check|calculate|query))",
    re.IGNORECASE,
)

_TOOL_CALL_TAG_RE = re.compile(r"<<tool_call>>(.*?)<</tool_call>>", re.DOTALL)


class Budget:
    """一轮对话的预算（时间 / 累计字符 / 轮数）。"""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.chars = 0
        self.rounds = 0
        self.wrapped = False
        self.grace = 0

    def consume(self, text: str) -> None:
        self.chars += len(text or "")

    def next_round(self) -> None:
        self.rounds += 1

    def exceeded(self) -> bool:
        return (
            time.monotonic() - self.started > BUDGET_SECONDS
            or self.chars > BUDGET_CHARS
            or self.rounds > BUDGET_ROUNDS
        )

    def should_wrap_up(self) -> bool:
        """超限时返回 True；已提醒过则只在宽限轮内继续。"""
        if not self.wrapped:
            if self.exceeded():
                self.wrapped = True
                self.grace = 0
                return True
            return False
        self.grace += 1
        return self.grace <= GRACE_ROUNDS

    def force_stop(self) -> bool:
        return self.wrapped and self.grace > GRACE_ROUNDS


class StagnationDetector:
    """同一工具 + 同一参数的重复调用检测。"""

    def __init__(self) -> None:
        self._signatures: deque[str] = deque(maxlen=STAGNATION_WINDOW)
        self.nudges = 0

    def observe(self, name: str, arguments: str) -> bool:
        """记录一次调用；返回是否应注入纠偏提示（最多 STAGNATION_MAX_NUDGES 次）。"""
        signature = f"{name}:{arguments}"
        self._signatures.append(signature)
        hits = sum(1 for item in self._signatures if item == signature)
        if hits >= STAGNATION_HITS and self.nudges < STAGNATION_MAX_NUDGES:
            self.nudges += 1
            self._signatures.clear()
            return True
        return False

    def reset(self) -> None:
        self._signatures.clear()


def looks_premature_final(text: str) -> bool:
    """终答文本是否像“计划句”而非结果。"""
    text = (text or "").strip()
    if not text:
        return False
    return bool(_PREMATURE_FINAL_RE.search(text))


def truncate_tool_result(text: str, limit: int = TOOL_RESULT_LIMIT) -> str:
    """工具结果截断（保留头部，注明截断）。"""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（结果过长已截断，原文 {len(text)} 字符）"


def retry_delay(attempt: int, error_text: str) -> float | None:
    """瞬时错误退避秒数；不可重试返回 None。

    attempt 从 0 开始；429/5xx 按 3/6/12/24s。若错误文本里带 Retry-After: N
    则优先用它（上限 60s）。
    """
    text = str(error_text or "")
    transient = any(code in text for code in ("429", "500", "502", "503", "504"))
    if "timeout" in text.lower() or "timed out" in text.lower():
        transient = True
    if not transient:
        return None
    if attempt >= 4:
        return None
    match = re.search(r"retry-after[:=]\s*(\d+)", text, re.IGNORECASE)
    if match:
        return min(60.0, float(match.group(1)))
    return (3, 6, 12, 24)[attempt]


def extract_tool_call(text: str) -> dict | None:
    """从纯文本里兜底解析工具调用。

    支持两种形式：
    - ``<<tool_call>>{"name":"...","arguments":{...}}<</tool_call>>``（标签协议）
    - 独立 JSON 对象且含 name + arguments 键（部分端点的 reasoning 流）
    """
    text = text or ""
    match = _TOOL_CALL_TAG_RE.search(text)
    candidates: list[str] = [match.group(1)] if match else []
    candidates.append(text)
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict) and "name" in payload:
            arguments = payload.get("arguments") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            return {"name": str(payload["name"]), "arguments": arguments}
    return None
