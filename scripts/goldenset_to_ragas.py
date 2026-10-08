"""校验 CUAD goldenset 能否投影到 RAGAS 的列，并说明当前数据集下哪些指标可用。

本脚本**不执行 RAGAS**，也不调用 judge 或 embedding：真正的执行在

    uv run --group eval python -m cli evaluate-ragas --mode smoke|trace|ragas

它只回答一个静态问题——goldenset 提供哪些列、哪些列必须由运行时 trace 补齐、因此哪些指标在当前
数据集上不可用。列契约的唯一权威是 ``infrastructure/evaluation/specs.py``，本脚本直接读它而不是复制
一份表，所以契约和这里的输出不会各自漂移。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from infrastructure.evaluation.specs import (
    UNAVAILABLE_METRICS,
    V1_METRICS,
    MetricSpec,
)

if TYPE_CHECKING:
    from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = REPO_ROOT / "evals" / "cuad" / "golden.jsonl"

#: goldenset 自己能提供的列。
GOLDENSET_COLUMNS = frozenset({"user_input", "reference_contexts"})
#: 只有运行时的 trace 能提供，goldenset 里永远没有。
TRACE_COLUMNS = frozenset({"response", "generator_contexts", "ranked_candidate_contexts"})


class ProjectionError(Exception):
    """goldenset 无法投影到 RAGAS 的列。"""


@dataclass(frozen=True)
class Sample:
    """一条 goldenset 记录投影后的两列，加上运行时结果用来关联的 ``id``。"""

    id: str
    user_input: str
    reference_contexts: list[str]

    @property
    def is_abstention_case(self) -> bool:
        """CUAD 标注该合同没有该类别的证据，因此系统必须弃答。"""
        return not self.reference_contexts


def load_samples(path: Path = GOLDEN_PATH) -> list[Sample]:
    """读取 ``golden.jsonl``，把 ``question``/``evidence`` 映射到 RAGAS 的两列。"""
    samples: list[Sample] = []
    seen: set[str] = set()
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row: Any = json.loads(line)
        raw: object = row["evidence"]
        if not isinstance(raw, list):
            raise ProjectionError(f"{path.name} 第 {index} 行: evidence 必须是数组")
        contexts = cast("list[object]", raw)
        if not all(isinstance(text, str) for text in contexts):
            raise ProjectionError(f"{path.name} 第 {index} 行: evidence 只能包含字符串")
        sample_id = str(row["id"])
        if sample_id in seen:
            raise ProjectionError(f"{path.name} 第 {index} 行: id 重复 {sample_id!r}")
        seen.add(sample_id)
        user_input = str(row["question"])
        if not user_input.strip():
            raise ProjectionError(f"{path.name} 第 {index} 行: question 为空")
        samples.append(
            Sample(
                id=sample_id,
                user_input=user_input,
                reference_contexts=cast("list[str]", contexts),
            )
        )
    if not samples:
        raise ProjectionError(f"{path.name}: 没有样本")
    return samples


def columns_of(spec: MetricSpec) -> tuple[str, ...]:
    """一个指标读的全部列。"""
    columns = ["user_input", "response"]
    if spec.contexts is not None:
        columns.append(spec.contexts)
    return tuple(columns)


def unsupplied_columns(spec: MetricSpec) -> tuple[str, ...]:
    """既不在 goldenset 也不在 trace 里的列；非空说明该指标在当下根本无法装配。"""
    return tuple(sorted(set(columns_of(spec)) - GOLDENSET_COLUMNS - TRACE_COLUMNS))


def force_utf8_stdout() -> None:
    """输出不跟着宿主代码页走。

    指标原因和本脚本的输出都是中文；重定向到 `.probe` / `dist/verify` 的日志必须是 UTF-8，
    否则同一份证据在不同平台上会被读成不同的东西。
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


def main() -> int:
    force_utf8_stdout()
    try:
        samples = load_samples()
    except ProjectionError as error:
        print(str(error), file=sys.stderr)
        return 1
    abstention = sum(1 for sample in samples if sample.is_abstention_case)
    print(f"{len(samples)} 条样本可投影到 RAGAS 的单轮列")
    print(
        f"  {len(samples) - abstention} 条有 reference_contexts / "
        f"{abstention} 条弃答样本（不进上下文指标）"
    )
    print(f"  goldenset 提供  {', '.join(sorted(GOLDENSET_COLUMNS))}")
    print(f"  trace 提供      {', '.join(sorted(TRACE_COLUMNS))}")
    print("  指标列需求:")
    unsupplied: list[str] = []
    for spec in V1_METRICS:
        missing = unsupplied_columns(spec)
        unsupplied.extend(missing)
        tier = "默认开启" if spec.default_enabled else "独立成本档"
        print(f"    {spec.name:38} {tier}  {', '.join(columns_of(spec))}")
    print("  当前不可用的指标:")
    for item in UNAVAILABLE_METRICS:
        print(f"    {item.name:38} 缺 {item.missing}: {item.reason}")
    if unsupplied:
        print(f"没有任何来源能提供这些列: {sorted(set(unsupplied))}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
