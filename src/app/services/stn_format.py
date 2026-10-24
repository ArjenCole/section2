"""`.stn` 文件信封：1.0 风格 XML 头 + CDATA 包裹的 JSON 数据体。

文件整体是一个合法 XML 文档，前半部分沿用旧版 1.0 的格式：

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<Root>
  <Assembly>
    <Version>2.0.0.0</Version>
  </Assembly>
  <mcBasicInfo>
    <ProjectName>…</ProjectName>
    <ProjectIndex>…</ProjectIndex>
    <Author>…</Author>
    <AtlasName>…</AtlasName>
  </mcBasicInfo>
  <Section2><![CDATA[{ …JSON… }]]></Section2>
</Root>
```

这样做的唯一目的：旧 1.0 软件（C# 版，`mscXML.ReadXml` → `mcDataCarrier` →
`versionCtrl`）误打开 2.0 保存的文件时，能正常解析整个文档、读出
`Assembly/Version` 并按字符串比较弹“正在打开的是高版本文件”提醒，而不是
抛异常崩溃。`mcBasicInfo` 必须带上 `ProjectName` / `ProjectIndex`（1.0 的
`mcBasicInfo` 构造函数对这两个元素不做判空），工程名等基本信息恰好也顺带
可见；`Section2` 是 1.0 不认识的元素，会被它忽略。

JSON 数据体是 2.0 的正式数据（见 :mod:`app.services.stn_codec`），只在本
模块里校验 `format` 标识与 `file_version` 结构版本，不关心具体业务字段。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from app.core.version import APP_VERSION, STN_FILE_VERSION
from app.core.models.base import (
    NotAProjectFileError,
    ProjectFileError,
    SchemaTooNewError,
)

#: JSON 数据体的格式标识（load 时校验，防止拿错数据）
FORMAT_NAME = "Section2"
#: 头部 `<Assembly><Version>` 固定写当前程序版本，供 1.0 比较大小
HEADER_VERSION = APP_VERSION
#: JSON 数据体所在元素名
_BODY_TAG = "Section2"

_XML_DECLARATION = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>'


@dataclass
class StnDocument:
    """一个 `.stn` 文件的解析结果。"""

    #: 头部 `<Assembly><Version>`（保存程序的应用版本号）
    header_version: str
    #: JSON 数据体（业务字段见 stn_codec）
    data: dict


def write_stn(path: str | Path, data: dict, *, header_version: str = HEADER_VERSION) -> Path:
    """把 JSON 数据体按 2.0 文件格式写入 path，返回 path。

    ``data`` 里需带 ``basic_info``（工程名等镜像到 1.0 风格的头部）。
    信封手工拼装：ElementTree 不支持 CDATA，且头部形状固定，拼接比
    逐节点构建再序列化更直观。
    """
    body = json.dumps(data, ensure_ascii=False, indent=2)
    # CDATA 里不允许出现 "]]>"：JSON 里 > 只可能出现在字符串字面量内，把 > 转成
    # \u003e 转义（解码后仍是 >），保证信封是合法 XML
    body = body.replace("]]>", "]]\\u003e")
    info = data.get("basic_info") or {}
    text = (
        f"{_XML_DECLARATION}\n"
        f"<Root>\n"
        f"  <Assembly>\n"
        f"    <Version>{_xml_escape(header_version)}</Version>\n"
        f"  </Assembly>\n"
        f"  <mcBasicInfo>\n"
        f"    <ProjectName>{_xml_escape(str(info.get('project_name', '')))}</ProjectName>\n"
        f"    <ProjectIndex>{_xml_escape(str(info.get('project_index', '')))}</ProjectIndex>\n"
        f"    <Author>{_xml_escape(str(info.get('author', '')))}</Author>\n"
        f"    <AtlasName>{_xml_escape(str(info.get('atlas_name', '')))}</AtlasName>\n"
        f"  </mcBasicInfo>\n"
        f"  <{_BODY_TAG}><![CDATA[{body}]]></{_BODY_TAG}>\n"
        f"</Root>\n"
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def load_stn(path: str | Path) -> StnDocument:
    """读取并解析 `.stn` 文件，返回头版本与 JSON 数据体。

    * 不是合法 XML / 缺头 / JSON 坏了 → :class:`NotAProjectFileError`；
    * JSON ``file_version`` 高于本程序 → :class:`SchemaTooNewError`
      （文件由更新版本的程序保存）；
    * ``file_version`` 低于本程序 → :class:`ProjectFileError`
      （出自未发布的旧预览版，不提供迁移）。
    """
    source = Path(path)
    try:
        root = ET.parse(source).getroot()
    except (ET.ParseError, OSError, ValueError) as error:
        raise NotAProjectFileError(f"不是有效的工程文件（无法按 XML 解析）：{source}\n{error}") from error

    assembly = root.find("Assembly")
    version_node = assembly.find("Version") if assembly is not None else None
    header_version = (version_node.text or "").strip() if version_node is not None else ""
    if not header_version:
        raise NotAProjectFileError(f"不是有效的工程文件（缺少 Assembly/Version 头）：{source}")

    body_node = root.find(_BODY_TAG)
    if body_node is None or not (body_node.text or "").strip():
        if root.tag == "Root" and header_version and not header_version.startswith("2"):
            raise NotAProjectFileError(
                f"这是 1.0 旧版程序保存的工程文件（版本 {header_version}），"
                "请用「文件 → 导入旧版工程(.stn)…」迁移后打开。"
            )
        raise NotAProjectFileError(f"不是有效的工程文件（缺少 JSON 数据体）：{source}")
    try:
        data = json.loads(body_node.text)
    except json.JSONDecodeError as error:
        raise NotAProjectFileError(f"工程文件的数据体不是有效 JSON：{source}\n{error}") from error
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise NotAProjectFileError(f"工程文件的数据体不是 {FORMAT_NAME} 格式：{source}")
    _check_file_version(data.get("file_version"), source)
    return StnDocument(header_version=header_version, data=data)


def _check_file_version(file_version, source: Path) -> None:
    if not isinstance(file_version, int):
        raise NotAProjectFileError(f"工程文件缺少结构版本号（file_version）：{source}")
    if file_version > STN_FILE_VERSION:
        raise SchemaTooNewError(
            f"工程文件数据结构版本为 {file_version}，本程序支持到 {STN_FILE_VERSION}；"
            "文件由更新版本的 Section 保存，请升级程序后再打开。"
        )
    if file_version < STN_FILE_VERSION:
        raise ProjectFileError(
            f"工程文件数据结构版本为 {file_version}，低于本程序支持的 {STN_FILE_VERSION}；"
            "该文件出自内部预览版，请用保存它的版本打开。"
        )


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
