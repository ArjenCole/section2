# 计算基准（对拍工程.json）

`对拍工程.json` 是 `tests/test_calc_baseline.py` 的黄金文件：记录「对拍工程」算例
（在测试代码里用 `NewProjectSpec` 现场构建，fixtures 里没有对应 .stn2）的全部
工程量结果与算式，算法改动引起数值变化都会被 `test_baseline_file` 拦下。

- 首次运行时若文件不存在，测试会自动生成并 skip，人工确认数值后重跑即冻结；
- 若是有意修改算法，更新该文件并复核 diff 里的每一条变化。

文件结构：

```json
{
  "定额汇总": {"<定额键>": {"value": 0.0, "expression": "…"}},
  "清单": [{"name": "…", "category": 1, "spec": "…", "amount": 0.0,
            "error": "", "quantities": {"<定额键>": {"value": 0.0, "expression": "…"}}}]
}
```

## 与旧版对拍

拿到旧版 C# 软件对同一算例的输出后，把旧版数值填进本文件并与新引擎结果对比
（`test_expression_matches_value` 里用同一 0.5% 相对误差约定）：同一工程各工程量
误差 < 0.5% 才算通过；简化算法导致对不上的条目，退回旧算法并在此注明。
