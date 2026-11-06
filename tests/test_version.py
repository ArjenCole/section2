"""版本号规则：语义化版本 ↔ 旧版兼容的四段纯数字。

四段数字用于 `.stn` 文件头和 EXE 文件属性，必须是纯数字；显示版本带
预发布后缀。两者都由 ``version.py`` 的 ``APP_VERSION`` 推导，这里锁住映射。
"""

import pytest

from app.core.version import (
    APP_VERSION,
    IS_PRERELEASE,
    STN_HEADER_VERSION,
    numeric_version,
)


def test_current_version_maps_to_numeric_header():
    assert STN_HEADER_VERSION == numeric_version(APP_VERSION)
    assert len(STN_HEADER_VERSION.split(".")) == 4
    assert STN_HEADER_VERSION.replace(".", "").isdigit()


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2.0.0-alpha.1", "2.0.0.1"),
        ("2.0.0-alpha.6", "2.0.0.6"),
        ("2.0.0-beta.7", "2.0.0.7"),  # 接 alpha.6 的序号，不重新计数
        ("2.0.0-rc.9", "2.0.0.9"),
        ("2.0.0.10", "2.0.0.10"),  # 正式版：第 4 段接着累加
        ("2.0.0.0", "2.0.0.0"),  # 已是四段，原样返回
        ("1.2.2.171220", "1.2.2.171220"),
    ],
)
def test_numeric_version(version, expected):
    assert numeric_version(version) == expected


@pytest.mark.parametrize("version", ["2.0.0", "2.0.0-alpha", "两个点.0.0"])
def test_numeric_version_rejects_ambiguous_versions(version):
    """正式版必须写成四段：否则会悄悄退回 .0，EXE 版本号反而变小。"""
    with pytest.raises(ValueError):
        numeric_version(version)


def test_release_continues_after_rc():
    """rc.9 之后正式版写 2.0.0.10，数字版本必须继续变大而不是回退。"""
    rc = tuple(int(part) for part in numeric_version("2.0.0-rc.9").split("."))
    release = tuple(int(part) for part in numeric_version("2.0.0.10").split("."))
    assert release > rc


def test_prerelease_counter_is_monotonic_across_channels():
    """alpha.6 → beta.7 → rc.8 的四段数字必须一路变大。"""
    quads = [
        tuple(int(part) for part in numeric_version(v).split("."))
        for v in ("2.0.0-alpha.6", "2.0.0-beta.7", "2.0.0-rc.8")
    ]
    assert quads == sorted(quads)
    assert len(set(quads)) == 3


def test_prerelease_flag_matches_version_suffix():
    assert IS_PRERELEASE == ("-" in APP_VERSION)
