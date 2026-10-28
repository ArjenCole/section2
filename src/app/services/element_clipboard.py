"""构件剪贴板（brackets 同款技术路线：跨文件复制 / 粘贴 / 剪切）。

复制的内容是**数据快照**而不是行引用：序列化成 JSON 放进系统剪贴板
（自定义 MIME ``application/x-section2-elements``）。SECTION2 打开多个工程
文件时每个进程持有自己的工作库（工程文件有 .lock 防双开），进程内存剪贴板
跨不了进程，系统剪贴板可以——复制后切换到另一个工程（乃至另一个程序实例）
粘贴，内容依然可用，这正是 brackets 跨文件复制粘贴的做法。

剪贴板载荷结构::

    {"kind": "section2-elements", "items": [...]}

item 两种：``{"type": "element", "data": <element_snapshot>}`` 与
``{"type": "group", "data": {"name", "amount", "members": [<element_snapshot…>]}}``。

剪切 = 复制 + 立即删除原条目（brackets 同款），剪贴板内容保留、可反复粘贴。
粘贴前 :func:`remap_items` 对原则引用做重映射——目标工程没有同名原则时
回退默认（与计算引擎的引用失效回退一致），保证跨文件粘贴不会挂上悬空引用。
"""

from __future__ import annotations

import json

_MIME = "application/x-section2-elements"
_KIND = "section2-elements"
_PLAIN_PREFIX = "SECTION2 构件剪贴板\n"
#: 载荷也放一份纯文本，便于剪贴板查看器排查；读取只认 MIME
_PLAIN_TEXT_LIMIT = 2000


def write_items(items: list[dict]) -> bool:
    """把快照条目写入系统剪贴板；空列表返回 False 不动剪贴板。"""
    from PySide6.QtWidgets import QApplication

    if not items:
        return False
    payload = {"kind": _KIND, "items": items}
    text = json.dumps(payload, ensure_ascii=False)
    clipboard = QApplication.clipboard()
    from PySide6.QtCore import QMimeData

    mime = QMimeData()
    mime.setData(_MIME, text.encode("utf-8"))
    plain = _PLAIN_PREFIX + text
    mime.setText(plain[:_PLAIN_TEXT_LIMIT] + ("…" if len(plain) > _PLAIN_TEXT_LIMIT else ""))
    clipboard.setMimeData(mime)
    return True


def read_items() -> list[dict] | None:
    """读取系统剪贴板里的构件快照；不是本程序的载荷时返回 None。

    返回的是**全新副本**（每次 JSON 解析），调用方可以就地修改（重映射
    原则引用）而不会影响剪贴板里的原始内容。
    """
    from PySide6.QtWidgets import QApplication

    clipboard = QApplication.clipboard()
    mime = clipboard.mimeData()
    if mime is None or not mime.hasFormat(_MIME):
        return None
    raw = bytes(mime.data(_MIME))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != _KIND:
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    return [item for item in items if isinstance(item, dict) and item.get("type") in ("element", "group")]


def has_payload() -> bool:
    """剪贴板里是否有可粘贴的构件快照（粘贴菜单可用态用）。"""
    return bool(read_items())


def remap_items(items: list[dict]) -> list[dict]:
    """按**当前工程**重映射快照里的原则引用（就地修改，read_items 已是副本）。

    pe / pf / pp / pw 按名引用；目标工程没有同名原则时置 None（入库时自动
    取库中第一条，与构件库插入同口径），左右围护侧名置空（计算时按失效
    回退第一条）。
    """
    from app.services import project_io

    checks = (
        ("pe_name", project_io.enclosure_names),
        ("pf_name", project_io.foundation_names),
        ("pp_name", project_io.precipitation_names),
        ("pw_name", project_io.width_names),
    )

    def _remap_element(data: dict) -> None:
        from app.core.models.models import LR_PE_TEXT

        for field, names in checks:
            name = data.get(field)
            if name and name != LR_PE_TEXT and name not in names():
                data[field] = None
        for side in ("pe_left_name", "pe_right_name"):
            name = data.get(side)
            if name and name != LR_PE_TEXT and name not in project_io.enclosure_names():
                data[side] = ""

    for item in items:
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        if item.get("type") == "element":
            _remap_element(data)
        else:
            for member in data.get("members") or []:
                if isinstance(member, dict):
                    _remap_element(member)
    return items
