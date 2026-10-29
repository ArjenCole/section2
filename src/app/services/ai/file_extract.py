"""AI 助手上传文件的文本提取（给模型的纯文本原料）。

用户把文件拖进 AI 助手后，先在本地把文件内容转成文本，再交给模型按提示词
提炼数据——模型只看文本，不在客户端里跑解析之外的任何逻辑：

* ``.xlsx/.xlsm/.xltx`` —— openpyxl 逐工作表展开成制表符表格（读缓存值，
  单元格显示什么就取什么）；
* ``.docx`` —— zipfile + XML 逐段抽取正文与表格（不引第三方依赖）；
* 其余按文本读（UTF-8 失败回退 GBK，再失败报错），含 ``.stn`` 工程文件、
  CSV / JSON / XML / Markdown 等；
* ``.pdf`` 需要可选依赖 pypdf，未安装时给出明确提示。

超长文件按字符截断（附截断说明），避免一次性挤爆模型上下文。
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

#: 单文件提取文本的字符上限（约 5 万汉字）：截断而不是拒绝，模型拿到的
#: 前半部分仍然可用
MAX_CHARS = 100_000

#: Excel / Word 单表 / 单文档的行列保险上限（防异常超大文件卡 UI 线程）
_MAX_SHEET_ROWS = 5000
_MAX_SHEET_COLS = 64
_MAX_DOCX_PARAGRAPHS = 8000

_TEXT_SUFFIXES = {
    ".csv", ".txt", ".json", ".xml", ".md", ".stn", ".log", ".ini",
    ".toml", ".yaml", ".yml", ".py", ".sql", ".htm", ".html",
}
_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx"}

#: 文件选择对话框的过滤器（与 extract_text 支持范围一致）
FILE_DIALOG_FILTER = (
    "所有支持的文件 (*.xlsx *.xlsm *.xltx *.docx *.csv *.txt *.json *.xml *.md *.stn *.log *.py);;"
    "Excel 工作簿 (*.xlsx *.xlsm *.xltx);;"
    "Word 文档 (*.docx);;"
    "文本/数据文件 (*.csv *.txt *.json *.xml *.md *.stn *.log *.py);;"
    "全部文件 (*.*)"
)


class FileExtractError(ValueError):
    """文件无法提取为文本（格式不支持 / 编码不可识别 / 内容为空）。"""


def extract_text(path: str) -> str:
    """把上传文件转成给模型的文本；失败抛 :class:`FileExtractError`。"""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileExtractError(f"文件不存在：{path}")
    suffix = file_path.suffix.lower()
    try:
        if suffix in _EXCEL_SUFFIXES:
            text = _excel_text(file_path)
        elif suffix == ".docx":
            text = _docx_text(file_path)
        elif suffix == ".pdf":
            text = _pdf_text(file_path)
        elif suffix in _TEXT_SUFFIXES:
            text = _plain_text(file_path)
        else:
            # 未识别的扩展名按文本尝试：文本读不出来（二进制）再报不支持
            text = _plain_text(file_path)
    except FileExtractError:
        raise
    except Exception as error:  # openpyxl / zipfile 的各类解析异常统一收口
        raise FileExtractError(f"无法读取文件「{file_path.name}」：{error}") from error
    if not text.strip():
        raise FileExtractError(f"文件「{file_path.name}」没有可提取的文本内容。")
    if len(text) > MAX_CHARS:
        text = (
            text[:MAX_CHARS]
            + f"\n\n[文件过长已截断：仅包含前 {MAX_CHARS} 字符，原文件共 {len(text)} 字符]"
        )
    return text


# --------------------------------------------------------------------------- #
# 各格式的实现
# --------------------------------------------------------------------------- #
def _plain_text(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        raise FileExtractError(
            f"暂不支持该文件类型（{path.suffix or '未知扩展名'}，疑似二进制）。"
            "请改传 Excel / Word / CSV / 文本文件。"
        )
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileExtractError(f"文件「{path.name}」不是 UTF-8 / GBK 文本，无法识别。")


def _excel_text(path: Path) -> str:
    from openpyxl import load_workbook

    # data_only=True：读公式单元格的缓存结果（显示值）；没有缓存时取公式原文
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        blocks: list[str] = []
        for sheet in workbook.worksheets:
            lines = [f"【工作表：{sheet.title}】"]
            row_count = 0
            for row in sheet.iter_rows(max_row=_MAX_SHEET_ROWS, max_col=_MAX_SHEET_COLS):
                cells = ["" if cell.value is None else str(cell.value) for cell in row]
                if not any(cells):
                    continue  # 整行空（行尾大量空列时压缩输出）
                lines.append("\t".join(cells).rstrip("\t"))
                row_count += 1
            if row_count:
                blocks.append("\n".join(lines))
            elif len(workbook.worksheets) == 1:
                blocks.append(f"【工作表：{sheet.title}】（空表）")
        return "\n\n".join(blocks)
    finally:
        workbook.close()


def _docx_text(path: Path) -> str:
    """Word 正文 + 表格（w:body 按出现顺序，表格不与正文段落重复）。"""
    _W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    body = root.find(f"{_W}body")
    if body is None:
        return ""

    def paragraph_text(paragraph: ET.Element) -> str:
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        return "".join(parts)

    def table_text(table: ET.Element) -> list[str]:
        rows: list[str] = []
        for tr in table.findall(f"{_W}tr"):
            cells: list[str] = []
            for tc in tr.findall(f"{_W}tc"):
                cell_lines = [
                    paragraph_text(p) for p in tc.iter(f"{_W}p")
                ]
                cells.append(" ".join(line for line in cell_lines if line))
            rows.append("\t".join(cells))
        return rows

    lines: list[str] = []
    for child in body:
        if child.tag == f"{_W}p":
            text = paragraph_text(child)
            if text.strip():
                lines.append(text)
        elif child.tag == f"{_W}tbl":
            lines.extend(table_text(child))
        if len(lines) >= _MAX_DOCX_PARAGRAPHS:
            lines.append("[文档过长，已截断]")
            break
    return "\n".join(lines)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise FileExtractError(
            "暂不支持 PDF（缺少可选依赖 pypdf）。请把 PDF 另存为 Word / Excel / 文本后再上传。"
        )
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(
        f"【第 {index} 页】\n{text}" for index, text in enumerate(pages, start=1) if text.strip()
    )
