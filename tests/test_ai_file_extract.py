"""AI 助手上传文件的本地文本提取（services.ai.file_extract）。

覆盖：xlsx 逐表展开、GBK 文本回退、docx 正文与表格、二进制 / 缺文件拒绝、
超长截断。纯文件操作，不需要 Qt。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.ai import file_extract
from app.services.ai.file_extract import FileExtractError, extract_text


def test_extract_xlsx_tables(tmp_path: Path) -> None:
    path = tmp_path / "管道.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "管道表"
    ws.append(["构件名称", "管径mm", "埋深"])
    ws.append(["雨DN600", 600, "2.5"])
    ws.append([])  # 空行不输出
    ws.append(["污DN800", 800, 3.0])
    wb.save(path)
    text = extract_text(str(path))
    assert "【工作表：管道表】" in text
    assert "构件名称\t管径mm\t埋深" in text
    assert "雨DN600\t600\t2.5" in text
    assert "污DN800\t800\t3" in text


def test_extract_gbk_text(tmp_path: Path) -> None:
    path = tmp_path / "说明.txt"
    path.write_bytes("埋深2.5米，管径600".encode("gbk"))
    assert extract_text(str(path)) == "埋深2.5米，管径600"


def _make_docx(path: Path) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>工程说明：雨水管道</w:t></w:r></w:p>"
        "<w:tbl>"
        "<w:tr><w:tc><w:p><w:r><w:t>名称</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>管径</w:t></w:r></w:p></w:tc></w:tr>"
        "<w:tr><w:tc><w:p><w:r><w:t>雨水管</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>DN600</w:t></w:r></w:p></w:tc></w:tr>"
        "</w:tbl>"
        "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def test_extract_docx_paragraphs_and_tables(tmp_path: Path) -> None:
    path = tmp_path / "说明.docx"
    _make_docx(path)
    text = extract_text(str(path))
    assert "工程说明：雨水管道" in text
    assert "名称\t管径" in text
    assert "雨水管\tDN600" in text


def test_binary_file_rejected(tmp_path: Path) -> None:
    path = tmp_path / "程序.exe"
    path.write_bytes(b"MZ\x00\x00" + b"\x00" * 128)
    with pytest.raises(FileExtractError, match="二进制"):
        extract_text(str(path))


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileExtractError, match="不存在"):
        extract_text(str(tmp_path / "没有.txt"))


def test_empty_text_rejected(tmp_path: Path) -> None:
    path = tmp_path / "空.txt"
    path.write_text("   \n  ")
    with pytest.raises(FileExtractError, match="没有可提取"):
        extract_text(str(path))


def test_long_text_truncated(tmp_path: Path) -> None:
    path = tmp_path / "长.txt"
    path.write_text("字" * (file_extract.MAX_CHARS + 100))
    text = extract_text(str(path))
    assert "已截断" in text
    assert len(text) < file_extract.MAX_CHARS + 200
