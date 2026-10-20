"""Agent 循环治理机制单测（与具体循环实现无关）。"""

from __future__ import annotations

from app.agent import governance


def test_budget_rounds_and_grace() -> None:
    budget = governance.Budget()
    budget.rounds = governance.BUDGET_ROUNDS + 1
    assert budget.exceeded()
    assert budget.should_wrap_up()
    # 宽限轮内继续，超过后强制停止
    for _ in range(governance.GRACE_ROUNDS):
        assert budget.should_wrap_up()
    assert budget.should_wrap_up() is False
    assert budget.force_stop()


def test_budget_chars() -> None:
    budget = governance.Budget()
    budget.consume("x" * (governance.BUDGET_CHARS + 1))
    assert budget.exceeded()


def test_stagnation_detector() -> None:
    detector = governance.StagnationDetector()
    hits = [detector.observe("list_elements", "{}") for _ in range(3)]
    assert hits[-1] is True
    # 纠偏后窗口清空，需再累计 3 次才触发第二次（最多两次）
    assert detector.observe("list_elements", "{}") is False
    assert detector.observe("list_elements", "{}") is False
    assert detector.observe("list_elements", "{}") is True
    for _ in range(3):
        assert detector.observe("list_elements", "{}") is False


def test_premature_final_detection() -> None:
    assert governance.looks_premature_final("让我先查询一下工程量。")
    assert governance.looks_premature_final("接下来我会计算回填量。")
    assert not governance.looks_premature_final("开挖工程量为 1799.074 m³。")


def test_truncate_tool_result() -> None:
    text = "a" * (governance.TOOL_RESULT_LIMIT + 10)
    truncated = governance.truncate_tool_result(text)
    assert len(truncated) > governance.TOOL_RESULT_LIMIT
    assert "已截断" in truncated
    assert governance.truncate_tool_result("short") == "short"


def test_retry_delay() -> None:
    assert governance.retry_delay(0, "HTTP 429 Too Many Requests") == 3
    assert governance.retry_delay(1, "HTTP 503") == 6
    assert governance.retry_delay(0, "Retry-After: 7 HTTP 429") == 7
    assert governance.retry_delay(0, "HTTP 400 bad request") is None
    assert governance.retry_delay(4, "HTTP 500") is None


def test_extract_tool_call_tag_and_json() -> None:
    tagged = '<<tool_call>>{"name":"list_elements","arguments":{"unit_id":1}}<</tool_call>>'
    assert governance.extract_tool_call(tagged) == {
        "name": "list_elements",
        "arguments": {"unit_id": 1},
    }
    plain = '{"name": "compute_unit", "arguments": {"unit_id": 2}}'
    assert governance.extract_tool_call(plain)["arguments"] == {"unit_id": 2}
    assert governance.extract_tool_call("普通文本") is None
