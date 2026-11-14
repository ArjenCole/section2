"""AI 面板思考块：两级折叠——第一层思考/流式正文，第二层收工具调用。"""

from __future__ import annotations

from app.views.panels.ai_panel import AiPanel, _ThinkingBlock


def _block_with_content() -> _ThinkingBlock:
    """一块已含思考文字 + 两条工具调用行的思考块（未展开）。"""
    block = _ThinkingBlock("思考过程")
    block.start_thinking()
    block.set_stream_text("这是思考的文字内容")
    block.append_tool_html("🔧 调用工具 查询单位工程…")
    block.append_tool_html("🔧 调用工具 查询管段…")
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


def test_collapsed_by_default_and_first_level_hides_tools(qapp) -> None:
    block = _block_with_content()
    # 默认整块收起（第一层维持原样）
    assert not block._toggle.isChecked()
    assert block._content.isHidden()
    # 第一层展开：只露思考文字，工具调用仍收在第二层
    block._toggle.setChecked(True)
    assert not block._content.isHidden()
    assert block._stream_label.isVisibleTo(block._content)
    assert block._tools_toggle is not None
    assert block._tools_toggle.text() == "工具调用（2）"
    assert block._tools_content.isHidden()


def test_second_level_expand_shows_tool_lines(qapp) -> None:
    block = _block_with_content()
    block._toggle.setChecked(True)
    # 第二层默认收起，点开才显示 🔧 行
    block._tools_toggle.setChecked(True)
    assert not block._tools_content.isHidden()
    assert block._tools_layout.count() == 2


def test_new_stream_label_keeps_above_tools_section(qapp) -> None:
    """工具调用之后再流式出正文：新标签要插在"工具调用"折叠区之前。"""
    block = _block_with_content()
    block.rotate_stream_label()
    block.set_stream_text("下一轮回复正文")
    layout = block._content_layout
    assert layout.indexOf(block._stream_label) < layout.indexOf(block._tools_toggle)


def test_error_line_stays_in_first_level(qapp) -> None:
    """错误行不属于工具调用：直接放第一层，不进第二层折叠区。"""
    block = _block_with_content()
    block.append_html('<p style="color:red;">[错误] 401</p>')
    assert block._tools_count == 2  # 计数不含错误行
    layout = block._content_layout
    assert layout.indexOf(block._tools_toggle) < layout.count() - 1  # 错误行在最末


def test_panel_status_routes_to_tools_section(qapp) -> None:
    """面板的 🔧 工具回调走第二层；错误回调仍走第一层。"""
    panel = AiPanel()
    block = _ThinkingBlock("思考过程")
    panel._thinking_block = block
    panel._on_status("调用工具 查询单位工程…")
    assert block._tools_toggle.text() == "工具调用（1）"
    block.append_html("<p>[错误] 测试</p>")
    assert block._tools_layout.count() == 1  # 错误行没进工具区
    panel._clear()
