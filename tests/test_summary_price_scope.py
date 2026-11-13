"""单价联动口径：同类别同项目才算同一工程量。

单价 key 是 ``类别|项目|单位``。判断两条工程量是否同一工程量时不能只看
项目名——``垫层|中粗砂`` 与 ``回填|中粗砂`` 是两种工程量，价格不应联动；
同类别同项目（即使单位不同）才按同一单价处理。
"""

from __future__ import annotations

from app.services import summary


def test_price_scope_is_category_and_item(project) -> None:
    summary.set_price("回填|中粗砂|m3", 100)
    summary.set_price("垫层|中粗砂|m3", 200)

    by_key, by_scope = summary.price_maps()
    assert by_key["回填|中粗砂|m3"] == 100
    assert by_key["垫层|中粗砂|m3"] == 200
    assert by_scope[("回填", "中粗砂")] == 100
    assert by_scope[("垫层", "中粗砂")] == 200


def test_propagate_does_not_cross_categories(project) -> None:
    summary.set_price("回填|中粗砂|m3", 100)
    summary.set_price("垫层|中粗砂|m3", 200)
    summary.set_price("回填|中粗砂|t", 90)
    summary.set_price("回填|素土|m3", 30)

    summary.set_price_propagate("回填|中粗砂|m3", 150)

    prices = summary.prices()
    assert prices["回填|中粗砂|m3"] == 150
    assert prices["回填|中粗砂|t"] == 150  # 同类别同项目，单位不同也联动
    assert prices["垫层|中粗砂|m3"] == 200  # 项目名同、类别不同，不联动
    assert prices["回填|素土|m3"] == 30  # 同类别、项目名不同，不联动


def test_resolve_price_falls_back_within_category(project) -> None:
    summary.set_price("回填|中粗砂|m3", 100)
    by_key, by_scope = summary.price_maps()

    # 同类别同项目、单位不同：回落到该类别 + 项目的单价
    assert summary.resolve_price("回填|中粗砂|t", by_key, by_scope) == 100
    # 项目名相同但类别不同：没有记录就是 0，不借用回填的价
    assert summary.resolve_price("垫层|中粗砂|t", by_key, by_scope) == 0.0

    # 显式 key 记录优先于（类别, 项目）回落
    summary.set_price("回填|中粗砂|t", 80)
    by_key, by_scope = summary.price_maps()
    assert summary.resolve_price("回填|中粗砂|t", by_key, by_scope) == 80
