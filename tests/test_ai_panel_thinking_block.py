"""AI 面板思考块：两级折叠——第一层按顺序排思考文字与工具调用节点。"""

from __future__ import annotations

import html

from app.views.panels.ai_panel import AiPanel, _ThinkingBlock, _ToolNode


def _layout_widgets(block: _ThinkingBlock) -> list:
    """第一层正文容器的子控件（按排列顺序）。"""
    layout = block._content_layout
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def _block_with_content() -> _ThinkingBlock:
    """一块按真实时序累积的内容：思考文字》工具节点》思考文字》工具节点。"""
    block = _ThinkingBlock("思考过程")
    block.start_thinking()
    block.set_stream_text("第一轮思考文字")
    node1 = block.append_tool_node("调用工具 查询单位工程…")
    node1.set_arguments('{"unit_name": "一号楼"}')
    block.rotate_stream_label()
    block.set_stream_text("第二轮思考文字")
    node2 = block.append_tool_node("调用工具 查询管段…")
    node2.set_arguments('{"diameter": 300}')
    return block


def test_outer_title_dots_animate_while_thinking(qapp) -> None:
    """第一层标题思考中带动态省略号，完成后回到纯标题。"""
    block = _ThinkingBlock("思考过程")
    block.start_thinking()
    assert block._toggle.text() == "思考过程."
    block._on_thinking_tick()
    assert block._toggle.text() == "思考过程.."
    block._on_thinking_tick()
    block._on_thinking_tick()  # 三个点后从头循环
    assert block._toggle.text() == "思考过程."
    block.stop_thinking()
    assert block._toggle.text() == "思考过程"


def test_first_level_shows_content_and_tool_nodes_in_order(qapp) -> None:
    block = _block_with_content()
    # 默认整块收起（第一层维持原样）
    assert not block._toggle.isChecked()
    assert block._content.isHidden()
    # 第一层展开：思考文字与工具节点按 思考文字》工具调用》思考文字》工具调用 排列
    block._toggle.setChecked(True)
    widgets = _layout_widgets(block)
    nodes = [w for w in widgets if isinstance(w, _ToolNode)]
    assert len(nodes) == 2
    assert [n._toggle.text() for n in nodes] == [
        "🔧 调用工具 查询单位工程…",
        "🔧 调用工具 查询管段…",
    ]
    stream_labels = [
        w for w in widgets if isinstance(w, type(block._stream_label)) and w is not block._status_label
    ]
    assert len(stream_labels) == 2
    assert widgets.index(stream_labels[0]) < widgets.index(nodes[0])
    assert widgets.index(nodes[0]) < widgets.index(stream_labels[1])
    assert widgets.index(stream_labels[1]) < widgets.index(nodes[1])
    # 工具节点各自默认收起
    assert all(n._content.isHidden() for n in nodes)


def test_tool_node_expand_shows_args_and_result(qapp) -> None:
    node = _ToolNode("调用工具 查询单位工程…")
    node.set_arguments('{"unit_name": "一号楼"}')
    node.set_result('{"id": 3}')
    # 第二层默认收起，点开才显示参数/结果
    assert node._content.isHidden()
    node._toggle.setChecked(True)
    assert not node._content.isHidden()
    # text() 返回富文本原文（HTML 转义），还原成显示文本再断言
    args_text = html.unescape(node._args_label.text())
    result_text = html.unescape(node._result_label.text())
    assert "参数" in args_text
    assert '"unit_name": "一号楼"' in args_text  # JSON 已缩进美化
    assert "结果" in result_text
    assert '"id": 3' in result_text


def test_error_line_stays_plain_in_first_level(qapp) -> None:
    """错误行不属于工具调用：直接排第一层正文，不进任何工具节点。"""
    block = _block_with_content()
    block.append_html('<p style="color:red;">[错误] 401</p>')
    widgets = _layout_widgets(block)
    assert not isinstance(widgets[-1], _ToolNode)
    assert len([w for w in widgets if isinstance(w, _ToolNode)]) == 2


def test_pretty_json_keeps_raw_text_on_invalid_json(qapp) -> None:
    from app.views.panels.ai_panel import _pretty_json

    assert _pretty_json('{"a": 1}') == '{\n  "a": 1\n}'
    assert _pretty_json("不是 JSON") == "不是 JSON"


def test_reasoning_stream_renders_complete_text(qapp) -> None:
    """思考流必须整段完整显示：中间片段和结尾都不能丢（原 bug 只留最后几个字）。"""
    panel = AiPanel()
    block = _ThinkingBlock("思考过程")
    panel._thinking_block = block
    block.start_thinking()
    chunks = [
        f"第{i}步，先核对第{i}号管段的埋深与管径数据是否一致，再决定分段原则。"
        for i in range(10)
    ]
    for chunk in chunks:
        panel._on_reasoning(chunk)  # 足量字符触发多次中间渲染
    panel._on_finished("最终回复")
    assert block._stream_label.text() == "（思考）" + "".join(chunks)


def test_reasoning_tail_flushed_even_below_throttle(qapp) -> None:
    """节流期内收尾：最后的短片段也要在结束时补渲染，不能永远留在缓冲里。"""
    panel = AiPanel()
    block = _ThinkingBlock("思考过程")
    panel._thinking_block = block
    block.start_thinking()
    panel._on_reasoning("第一段思考。")
    panel._on_reasoning("结尾补丁。")  # 两段加起来不到 40 字，中间不触发渲染
    panel._on_finished("最终回复")
    assert block._stream_label.text() == "（思考）第一段思考。结尾补丁。"


def test_reasoning_then_content_keeps_both_segments(qapp) -> None:
    """同一轮先思考后正文：思考文字换独立段落保留，不被正文覆盖。"""
    panel = AiPanel()
    block = _ThinkingBlock("思考过程")
    panel._thinking_block = block
    block.start_thinking()
    panel._on_reasoning("思考前半段。")
    reasoning_label = block._stream_label
    assert reasoning_label.text() == "（思考）思考前半段。"
    panel._on_content("正文第一句。")
    content_label = block._stream_label
    assert content_label is not reasoning_label
    assert content_label.text() == "正文第一句。"
    assert reasoning_label.text() == "（思考）思考前半段。"
    layout = block._content_layout
    assert layout.indexOf(reasoning_label) < layout.indexOf(content_label)


def test_panel_tool_flow_builds_ordered_nodes(qapp) -> None:
    """面板工具回调：开始建节点填参数、结果填同一节点、正文接在节点后。"""
    panel = AiPanel()
    block = _ThinkingBlock("思考过程")
    panel._thinking_block = block
    block.start_thinking()
    panel._on_content("第一轮正文")
    panel._on_tool_started("查询单位工程", '{"unit_name": "一号楼"}')
    node = panel._active_tool_node
    assert isinstance(node, _ToolNode)
    assert node._toggle.text() == "🔧 调用工具 查询单位工程…"
    panel._on_tool_result("查询单位工程", '{"id": 3}')
    assert panel._active_tool_node is None  # 结果已填，节点清手
    assert "结果" in node._result_label.text()
    # 之后的流式正文换新标签，排在工具节点之后
    panel._on_content("最终回复")
    widgets = _layout_widgets(block)
    assert widgets.index(block._stream_label) > widgets.index(node)
    # "调用工具 X…"状态行被跳过（节点已由 tool_started 建）；重试行仍显示
    count = block._content_layout.count()
    panel._on_status("调用工具 查询管段…")
    assert block._content_layout.count() == count
    panel._on_status("模型请求失败：超时；5s 后重试…")
    assert block._content_layout.count() == count + 1
    panel._clear()
    assert panel._active_tool_node is None
