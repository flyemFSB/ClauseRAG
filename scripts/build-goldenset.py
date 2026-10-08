"""构建并校验 ClauseRAG CUAD 黄金基准集（Goldenset）。

规范契约参见：``docs/goldenset-construction.md``。

黄金集是 ``datasets/cuad/CUAD_v1/CUAD_v1.json`` 人工标注的无损、可复现投影：
每个抽样的 (contract, clause category) 槽位生成一行，仅记录原始标注事实。
不夹带任何 chunk_id、行号、解析产物或检索分数，使基准集与解析器、切片器和检索器解耦。
通过贪心覆盖与固定随机种子（410 槽位 / 100 合同子集），确保稀有条款覆盖率与百分之百确定性重现。

用法：
    uv run python scripts/build-goldenset.py            # 构建、校验并写入产物
    uv run python scripts/build-goldenset.py --verify   # 重算校验和与字段完整性（不写文件）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "datasets" / "cuad" / "CUAD_v1" / "CUAD_v1.json"
DATASET_MANIFEST_PATH = REPO_ROOT / "datasets" / "cuad" / "MANIFEST.json"
GOLDENSET_DIR = REPO_ROOT / "evals" / "cuad"
CATEGORIES_PATH = GOLDENSET_DIR / "categories.json"
CORPUS_PATH = GOLDENSET_DIR / "corpus.json"
GOLDEN_PATH = GOLDENSET_DIR / "golden.jsonl"
REPORT_PATH = GOLDENSET_DIR / "build-report.json"
ROUTING_PATH = REPO_ROOT / "evals" / "routing" / "contrast.jsonl"

#: 抽样随机种子：固定种子确保 410 行基准集完全确定性重现
DEFAULT_SEED = 20261006
PER_CATEGORY = 10
EMPTY_EVIDENCE_PER_CATEGORY = 5

#: 评测语料库配置：种子与抽样种子隔离，避免重抽样导致基础语料偏移
CORPUS_SIZE = 100
CORPUS_SEED = 20261006
#: 语料库每个类别在随机填充前必须预留的目标合同数
CORPUS_POSITIVE_TARGET = PER_CATEGORY
CORPUS_EMPTY_TARGET = EMPTY_EVIDENCE_PER_CATEGORY

#: 样本字段契约定义
GOLDEN_FIELDS = {"id", "document_key", "category", "question", "evidence"}
ROUTING_FIELDS = {"id", "intent", "question", "context", "note"}
ROUTING_INTENTS = {"retrieval", "direct_response", "ask_clarification"}
ROUTING_CONTEXTS = {"empty_session", "document_selected"}

#: CUAD 问答模板定义
QUESTION_TEMPLATE = (
    'Highlight the parts (if any) of this contract related to "{category}" '
    "that should be reviewed by a lawyer. Details: {description}"
)
QUESTION_PATTERN = re.compile(
    r'^Highlight the parts \(if any\) of this contract related to "(?P<category>[^"]+)" '
    r"that should be reviewed by a lawyer\. Details: (?P<description>.+)$"
)
GOLDEN_ID_PATTERN = re.compile(r"^cuad-\d{6}$")

#: 匹配脱敏或占位符文本（SEC 商业合同中常见的保密处理占位符）
REDACTION_PATTERN = re.compile(
    r"\*{2,}|(?<![A-Za-z0-9])_{2,}(?![A-Za-z0-9])|\[\s*\]|omitted", re.IGNORECASE
)


class GoldensetError(Exception):
    """黄金集构建或校验约束违例。"""


@dataclass(frozen=True)
class Category:
    """CUAD 条款类别及其模板描述。"""

    name: str
    description: str


@dataclass(frozen=True)
class Slot:
    """CUAD 原始标注槽位（合同文档与条款类别）。"""

    document_key: str
    category: str
    description: str
    question: str
    evidence: tuple[str, ...]
    answer_starts: tuple[int, ...]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 强制 LF 换行，确保跨平台生成的文件哈希完全一致
    path.write_text(text, encoding="utf-8", newline="\n")


def dump_json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def dump_jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def render_question(category: Category) -> str:
    return QUESTION_TEMPLATE.format(category=category.name, description=category.description)


def parse_slots(raw: Any) -> list[Slot]:
    """解析原始标注槽位，校验模板是否精确还原问题文本并校验答案一致性。"""
    slots: list[Slot] = []
    for contract in raw["data"]:
        document_key = contract["title"]
        paragraphs = contract["paragraphs"]
        if len(paragraphs) != 1:
            raise GoldensetError(f"{document_key}: 预期包含 1 个段落，实际发现 {len(paragraphs)}")
        for qa in paragraphs[0]["qas"]:
            match = QUESTION_PATTERN.match(qa["question"])
            if match is None:
                raise GoldensetError(
                    f"{document_key}: 问题格式不符合 CUAD 模板: {qa['question'][:80]!r}"
                )
            category = Category(match["category"], match["description"])
            if render_question(category) != qa["question"]:
                raise GoldensetError(f"{document_key}/{category.name}: 模板无法完全还原问题文本")
            evidence = tuple(answer["text"] for answer in qa["answers"])
            if bool(qa["is_impossible"]) != (not evidence):
                raise GoldensetError(
                    f"{document_key}/{category.name}: is_impossible 状态与 answers 不一致"
                )
            slots.append(
                Slot(
                    document_key=document_key,
                    category=category.name,
                    description=category.description,
                    question=qa["question"],
                    evidence=evidence,
                    answer_starts=tuple(answer["answer_start"] for answer in qa["answers"]),
                )
            )
    return slots


def categories_of(slots: list[Slot]) -> list[Category]:
    """按 CUAD 原始出现顺序提取唯一条款类别。"""
    ordered: dict[str, str] = {}
    for slot in slots:
        known = ordered.setdefault(slot.category, slot.description)
        if known != slot.description:
            raise GoldensetError(f"类别 {slot.category!r} 存在两个不同的描述")
    return [Category(name, description) for name, description in ordered.items()]


def categories_document(categories: list[Category]) -> dict[str, object]:
    return {
        "question_template": QUESTION_TEMPLATE,
        # 41 个条款类别统一归属于 retrieval 路由意图
        "routing_intent": "retrieval",
        "categories": [{"name": item.name, "description": item.description} for item in categories],
    }


def category_names(categories: list[Category]) -> list[str]:
    return [item.name for item in categories]


def as_string_list(value: object) -> list[str] | None:
    """类型安全守卫：若非字符串列表则返回 None。"""
    if not isinstance(value, list):
        return None
    entries = cast("list[object]", value)
    if not all(isinstance(entry, str) for entry in entries):
        return None
    return cast("list[str]", entries)


def as_category_entries(value: object) -> list[dict[str, str]] | None:
    """类型守卫：将输入解析为由 {name, description} 组成的字典列表。"""
    if not isinstance(value, list):
        return None
    entries: list[dict[str, str]] = []
    for raw in cast("list[object]", value):
        if not isinstance(raw, dict):
            return None
        item = cast("dict[str, object]", raw)
        name, description = item.get("name"), item.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            return None
        entries.append({"name": name, "description": description})
    return entries


def ensure_categories_file(categories: list[Category]) -> str:
    """维护 categories.json 文件：不存在则写入，存在则校验与源数据的一致性。"""
    if not CATEGORIES_PATH.exists():
        write_text(CATEGORIES_PATH, dump_json(categories_document(categories)))
        return "generated"
    on_disk: Any = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    if on_disk.get("question_template") != QUESTION_TEMPLATE:
        raise GoldensetError(f"{CATEGORIES_PATH.name}: question_template 与 CUAD 源数据不一致")
    if on_disk.get("routing_intent") != "retrieval":
        raise GoldensetError(f"{CATEGORIES_PATH.name}: routing_intent 必须为 'retrieval'")
    entries = as_category_entries(on_disk.get("categories"))
    if entries is None:
        raise GoldensetError(
            f"{CATEGORIES_PATH.name}: categories 必须为包含 name/description 的数组"
        )
    stored = {item["name"]: item["description"] for item in entries}
    wanted = {item.name: item.description for item in categories}
    if missing := sorted(set(wanted) - set(stored)):
        raise GoldensetError(f"{CATEGORIES_PATH.name}: 缺失类别 {missing}")
    if extra := sorted(set(stored) - set(wanted)):
        raise GoldensetError(f"{CATEGORIES_PATH.name}: 未知类别 {extra}")
    if drifted := sorted(name for name in wanted if wanted[name] != stored[name]):
        raise GoldensetError(f"{CATEGORIES_PATH.name}: 类别描述与源数据不一致: {drifted}")
    if [item["name"] for item in entries] != category_names(categories):
        raise GoldensetError(f"{CATEGORIES_PATH.name}: 类别顺序与 CUAD 原始顺序不一致")
    return "verified"


def contracts_by_side(
    slots: list[Slot], categories: list[Category]
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """按类别统计含有证据与无证据的合同 key 集合。"""
    positive: dict[str, set[str]] = {category.name: set() for category in categories}
    empty: dict[str, set[str]] = {category.name: set() for category in categories}
    for slot in slots:
        (positive if slot.evidence else empty)[slot.category].add(slot.document_key)
    return positive, empty


def select_corpus(slots: list[Slot], categories: list[Category], size: int, seed: int) -> list[str]:
    """选择评测语料库：优先贪心覆盖稀缺类别合同，剩余配额基于随机种子填充。"""
    positive, empty = contracts_by_side(slots, categories)
    needed_positive = {
        name: min(CORPUS_POSITIVE_TARGET, len(keys)) for name, keys in positive.items()
    }
    needed_empty = {name: min(CORPUS_EMPTY_TARGET, len(keys)) for name, keys in empty.items()}
    candidates = sorted({slot.document_key for slot in slots})
    chosen: list[str] = []
    while (any(needed_positive.values()) or any(needed_empty.values())) and len(chosen) < size:
        taken = set(chosen)
        scores = {
            key: 3
            * sum(1 for name, keys in positive.items() if needed_positive[name] and key in keys)
            + sum(1 for name, keys in empty.items() if needed_empty[name] and key in keys)
            for key in candidates
            if key not in taken
        }
        # 候选集已预先排序，max 保持首个极值，平局时按文档 key 稳定决胜
        best = max(scores, key=lambda key: scores[key])
        if scores[best] == 0:
            break
        chosen.append(best)
        for name, keys in positive.items():
            if needed_positive[name] and best in keys:
                needed_positive[name] -= 1
        for name, keys in empty.items():
            if needed_empty[name] and best in keys:
                needed_empty[name] -= 1
    remaining = [key for key in candidates if key not in set(chosen)]
    fill = random.Random(seed).sample(remaining, min(size - len(chosen), len(remaining)))
    return sorted(chosen + fill)


def corpus_document(corpus: list[str], source_meta: dict[str, object]) -> dict[str, Any]:
    return {
        "role": (
            "the ingested CUAD evaluation corpus; ingestion takes this list as its document set"
        ),
        "size": len(corpus),
        "seed": CORPUS_SEED,
        "selection": "coverage-greedy for scarce clause categories, then a seeded random fill",
        "targets": {
            "contracts_with_evidence_per_category": CORPUS_POSITIVE_TARGET,
            "contracts_without_evidence_per_category": CORPUS_EMPTY_TARGET,
        },
        "source": {"path": source_meta["path"], "sha256": source_meta["sha256"]},
        "documents": corpus,
    }


def ensure_corpus_file(corpus: list[str], source_meta: dict[str, object]) -> str:
    """维护 corpus.json 文件：不存在则写入，若与最新推导不一致则抛出异常阻断。"""
    if not CORPUS_PATH.exists():
        write_text(CORPUS_PATH, dump_json(corpus_document(corpus, source_meta)))
        return "generated"
    on_disk: Any = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    if as_string_list(on_disk.get("documents")) != corpus:
        raise GoldensetError(
            f"{CORPUS_PATH.name}: 与新推导结果不一致。若确需变更请删除旧文件后重新执行解析导入。"
        )
    return "verified"


def sample_slots(
    slots: list[Slot], categories: list[Category], corpus: set[str], seed: int
) -> list[Slot]:
    """从评测语料中分层抽样：每个类别优先抽取空证据负样本，不足配额从证据样本补齐。"""
    rng = random.Random(seed)
    pools: dict[str, list[Slot]] = {category.name: [] for category in categories}
    for slot in slots:
        if slot.document_key in corpus:
            pools[slot.category].append(slot)
    selected: list[Slot] = []
    for category in categories:
        pool = pools[category.name]
        empty = sorted(
            (slot for slot in pool if not slot.evidence), key=lambda slot: slot.document_key
        )
        with_evidence = sorted(
            (slot for slot in pool if slot.evidence), key=lambda slot: slot.document_key
        )
        empty_take = min(EMPTY_EVIDENCE_PER_CATEGORY, len(empty))
        selected.extend(rng.sample(empty, empty_take))
        selected.extend(
            rng.sample(with_evidence, min(PER_CATEGORY - empty_take, len(with_evidence)))
        )
    rank = {category.name: index for index, category in enumerate(categories)}
    return sorted(selected, key=lambda slot: (rank[slot.category], slot.document_key))


def golden_rows(selected: list[Slot]) -> list[dict[str, Any]]:
    """按 (类别, 文档 key) 排序编号生成黄金集条目。"""
    return [
        {
            "id": f"cuad-{index:06d}",
            "document_key": slot.document_key,
            "category": slot.category,
            "question": slot.question,
            "evidence": list(slot.evidence),
        }
        for index, slot in enumerate(selected, start=1)
    ]


def count_pools(slots: list[Slot], categories: list[Category]) -> dict[str, tuple[int, int]]:
    tallies: dict[str, tuple[int, int]] = {category.name: (0, 0) for category in categories}
    for slot in slots:
        with_evidence, empty = tallies[slot.category]
        tallies[slot.category] = (
            (with_evidence + 1, empty) if slot.evidence else (with_evidence, empty + 1)
        )
    return tallies


def relative(path: Path) -> str:
    """生成相对于仓库根目录的 posix 路径，保证跨平台校验一致性。"""
    return path.relative_to(REPO_ROOT).as_posix()


def routing_summary() -> dict[str, object]:
    if not ROUTING_PATH.exists():
        return {"path": relative(ROUTING_PATH), "samples": 0}
    lines = [line for line in ROUTING_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {"path": relative(ROUTING_PATH), "samples": len(lines)}


def build_report(
    *,
    seed: int,
    source_meta: dict[str, object],
    slots: list[Slot],
    corpus: list[str],
    corpus_state: str,
    categories: list[Category],
    selected: list[Slot],
    rows: list[dict[str, Any]],
    categories_state: str,
) -> dict[str, Any]:
    in_corpus = [slot for slot in slots if slot.document_key in set(corpus)]
    source_available = count_pools(slots, categories)
    corpus_available = count_pools(in_corpus, categories)
    sampled = count_pools(selected, categories)
    redacted = sum(
        1 for slot in selected for text in slot.evidence if REDACTION_PATTERN.search(text)
    )
    non_document_order = sum(
        1 for slot in selected if list(slot.answer_starts) != sorted(slot.answer_starts)
    )
    return {
        "generated_by": "scripts/build-goldenset.py",
        "goldenset": "CUAD v1 stratified sample",
        "seed": seed,
        "source": source_meta,
        "sampling": {
            "per_category": PER_CATEGORY,
            "empty_evidence_per_category": EMPTY_EVIDENCE_PER_CATEGORY,
            "order": "empty-evidence pool first, then evidence pool, each sorted by "
            "document_key and drawn with random.Random(seed)",
            "id_assignment": "(category order, document_key) order numbered cuad-000001..",
        },
        "totals": {
            "samples": len(rows),
            "with_evidence": sum(1 for slot in selected if slot.evidence),
            "empty_evidence": sum(1 for slot in selected if not slot.evidence),
            "document_keys": len({slot.document_key for slot in selected}),
            "categories": len(categories),
        },
        "corpus": {
            "path": "evals/cuad/corpus.json",
            "state": corpus_state,
            "sha256": hashlib.sha256(
                dump_json(corpus_document(corpus, source_meta)).encode("utf-8")
            ).hexdigest(),
            "contracts": len(corpus),
            "requested": CORPUS_SIZE,
            "seed": CORPUS_SEED,
            "question_slots": len(in_corpus),
        },
        "categories": [
            {
                "name": category.name,
                "corpus": {
                    "with_evidence": corpus_available[category.name][0],
                    "empty_evidence": corpus_available[category.name][1],
                },
                "source": {
                    "with_evidence": source_available[category.name][0],
                    "empty_evidence": source_available[category.name][1],
                },
                "sampled": {
                    "with_evidence": sampled[category.name][0],
                    "empty_evidence": sampled[category.name][1],
                },
                "deviation": (
                    None
                    if sampled[category.name][1] == EMPTY_EVIDENCE_PER_CATEGORY
                    else (
                        f"the corpus holds {corpus_available[category.name][1]} empty-evidence "
                        f"slots of {EMPTY_EVIDENCE_PER_CATEGORY}; filled the remaining quota "
                        "from with_evidence"
                    )
                ),
            }
            for category in categories
        ],
        # 构建契约要求记录：证明校验项已执行且通过
        "checks": {"duplicate_ids": 0, "duplicate_keys": 0, "unmapped_document_keys": []},
        "outputs": {
            "path": "evals/cuad/golden.jsonl",
            "sha256": hashlib.sha256(dump_jsonl(rows).encode("utf-8")).hexdigest(),
            "lines": len(rows),
        },
        "categories_file": {
            "path": "evals/cuad/categories.json",
            "state": categories_state,
            "sha256": hashlib.sha256(
                dump_json(categories_document(categories)).encode("utf-8")
            ).hexdigest(),
        },
        "routing_contrast": routing_summary(),
        "warnings": [
            (
                f"{redacted} evidence spans here carry masked or omitted text (*, _, [], "
                "'omitted'), so they annotate placeholders rather than recoverable source "
                "text and will not project verbatim onto any parse of the source PDF."
            ),
            (
                f"{non_document_order} rows keep evidence in CUAD's annotation order, which is "
                "not document order (answers[].answer_start is not monotonic). The evaluator "
                "must order projected spans by its own line numbers."
            ),
            (
                "CUAD is an out-of-domain baseline rather than a product corpus, and its "
                "answers[].answer_start offsets belong to CUAD's own TXT extraction: they are "
                "never platform coordinates (datasets/cuad/MANIFEST.json)."
            ),
            (
                f"evals/cuad/corpus.json is the ingested set ({len(corpus)} of "
                f"{len({slot.document_key for slot in slots})} contracts). Changing it — a "
                "different source, a different selection rule, a different CORPUS_SEED — "
                "requires ingesting again and invalidates every measurement taken against "
                "the previous corpus."
            ),
        ],
    }


def validate_golden(
    rows: list[dict[str, Any]],
    *,
    source_slots: dict[tuple[str, str], Slot],
    document_keys: set[str],
    corpus: set[str],
    categories: list[Category],
    report: dict[str, Any],
) -> list[str]:
    """统一收集并校验 docs/goldenset-construction.md § 构建校验中定义的所有违例项。"""
    errors: list[str] = []
    names = set(category_names(categories))
    reported = {item["name"]: item for item in report["categories"]}
    seen_ids: set[str] = set()
    seen_keys: set[tuple[str, str]] = set()
    per_category: dict[str, int] = dict.fromkeys(names, 0)
    for index, row in enumerate(rows, start=1):
        where = f"line {index}"
        if set(row) != GOLDEN_FIELDS:
            errors.append(
                f"{where}: fields must be exactly {sorted(GOLDEN_FIELDS)}, found {sorted(row)}"
            )
            continue
        sample_id = row["id"]
        document_key = row["document_key"]
        category = row["category"]
        question = row["question"]
        where = str(sample_id)
        if not isinstance(sample_id, str) or not GOLDEN_ID_PATTERN.match(sample_id):
            errors.append(f"{where}: id must match cuad-NNNNNN")
        elif sample_id in seen_ids:
            errors.append(f"{where}: duplicate id")
        else:
            seen_ids.add(sample_id)
        if not isinstance(document_key, str) or not document_key.strip():
            errors.append(f"{where}: document_key is empty")
        elif document_key not in document_keys:
            errors.append(f"{where}: document_key maps to no CUAD contract")
        elif document_key not in corpus:
            errors.append(f"{where}: document_key is outside the evaluation corpus")
        if not isinstance(category, str) or category not in names:
            errors.append(f"{where}: category {category!r} is not in categories.json")
            continue
        per_category[category] += 1
        if (document_key, category) in seen_keys:
            errors.append(f"{where}: duplicate (document_key, category)")
        else:
            seen_keys.add((document_key, category))
        if not isinstance(question, str) or not question.strip():
            errors.append(f"{where}: question is empty")
        evidence = as_string_list(row["evidence"])
        if evidence is None:
            errors.append(f"{where}: evidence must be an array of strings")
            continue
        if any(not item.strip() for item in evidence):
            errors.append(f"{where}: evidence contains an empty string")
        slot = source_slots.get((document_key, category))
        if slot is None:
            errors.append(f"{where}: (document_key, category) does not exist in the CUAD source")
            continue
        if question != slot.question:
            errors.append(
                f"{where}: question differs from the CUAD source, not this document version"
            )
        if tuple(evidence) != slot.evidence:
            errors.append(f"{where}: evidence differs from the CUAD source (order included)")
    for name in sorted(names):
        count = per_category[name]
        if count != PER_CATEGORY and reported[name]["deviation"] is None:
            errors.append(
                f"category {name!r}: {count} rows sampled, deviation not in the build report"
            )
        elif not 0 < count <= PER_CATEGORY:
            errors.append(f"category {name!r}: {count} rows sampled")
    if len(rows) != report["totals"]["samples"]:
        errors.append(f"row count {len(rows)} differs from the build report")
    return errors


def validate_corpus(
    corpus: list[str],
    *,
    slots: list[Slot],
    categories: list[Category],
) -> list[str]:
    """校验评测语料库完整性：确保包含黄金集所需条目且满足各类别覆盖指标。"""
    errors: list[str] = []
    if len(corpus) != CORPUS_SIZE:
        errors.append(f"corpus holds {len(corpus)} contracts, expected {CORPUS_SIZE}")
    if len(set(corpus)) != len(corpus):
        errors.append("corpus contains duplicate document_key values")
    if any(not key.strip() for key in corpus):
        errors.append("corpus contains an empty document_key")
    known = {slot.document_key for slot in slots}
    if unknown := sorted(set(corpus) - known):
        errors.append(
            f"corpus holds document_key values that map to no CUAD contract: {unknown[:3]}"
        )
    source_available = count_pools(slots, categories)
    corpus_available = count_pools(
        [slot for slot in slots if slot.document_key in set(corpus)], categories
    )
    for category in categories:
        for side, target, label in (
            (0, CORPUS_POSITIVE_TARGET, "evidence"),
            (1, CORPUS_EMPTY_TARGET, "empty"),
        ):
            required = min(target, source_available[category.name][side])
            held = corpus_available[category.name][side]
            if held < required:
                errors.append(
                    f"category {category.name!r}: corpus holds {held} {label} contracts but "
                    f"{required} were both required and available in the source"
                )
    return errors


def validate_routing() -> list[str]:
    """校验路由对比样本。

    除 retrieval 外，必须具备 direct_response 与 ask_clarification 对比样本。
    """
    errors: list[str] = []
    if not ROUTING_PATH.exists():
        return [f"{relative(ROUTING_PATH)}: missing routing contrast samples"]
    seen: set[str] = set()
    intents: set[str] = set()
    for index, line in enumerate(ROUTING_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{ROUTING_PATH.name} line {index}"
        row: Any = json.loads(line)
        if set(row) != ROUTING_FIELDS:
            errors.append(
                f"{where}: fields must be exactly {sorted(ROUTING_FIELDS)}, found {sorted(row)}"
            )
            continue
        if row["id"] in seen:
            errors.append(f"{where}: duplicate id {row['id']!r}")
        seen.add(str(row["id"]))
        if row["intent"] not in ROUTING_INTENTS:
            errors.append(f"{where}: unknown intent {row['intent']!r}")
        intents.add(str(row["intent"]))
        if row["context"] not in ROUTING_CONTEXTS:
            errors.append(f"{where}: unknown context {row['context']!r}")
        for field in ("question", "note"):
            if not str(row[field]).strip():
                errors.append(f"{where}: {field} is empty")
    for required in sorted(ROUTING_INTENTS - {"retrieval"}):
        if required not in intents:
            errors.append(f"{ROUTING_PATH.name}: no {required} contrast sample")
    return errors


def source_metadata(slots: list[Slot]) -> dict[str, object]:
    digest = sha256_of(SOURCE_PATH)
    manifest: Any = (
        json.loads(DATASET_MANIFEST_PATH.read_text(encoding="utf-8"))
        if DATASET_MANIFEST_PATH.exists()
        else {}
    )
    declared = next(
        (
            artifact["sha256"]
            for artifact in manifest.get("artifacts", [])
            if artifact["path"] == "datasets/cuad/CUAD_v1/CUAD_v1.json"
        ),
        None,
    )
    if declared is not None and declared != digest:
        raise GoldensetError(
            f"{SOURCE_PATH.name}: sha256 {digest} does not match the dataset manifest ({declared})"
        )
    return {
        "path": relative(SOURCE_PATH),
        "sha256": digest,
        "size_bytes": SOURCE_PATH.stat().st_size,
        "manifest_sha256": declared,
        "contracts": len({slot.document_key for slot in slots}),
        "question_slots": len(slots),
        "categories": len({slot.category for slot in slots}),
    }


def fail(errors: list[str]) -> None:
    if errors:
        raise GoldensetError(f"{len(errors)} goldenset violation(s):\n  " + "\n  ".join(errors))


def command_build(seed: int) -> int:
    slots = parse_slots(json.loads(SOURCE_PATH.read_text(encoding="utf-8")))
    categories = categories_of(slots)
    source_meta = source_metadata(slots)
    categories_state = ensure_categories_file(categories)
    corpus = select_corpus(slots, categories, CORPUS_SIZE, CORPUS_SEED)
    corpus_state = ensure_corpus_file(corpus, source_meta)
    selected = sample_slots(slots, categories, set(corpus), seed)
    rows = golden_rows(selected)
    report = build_report(
        seed=seed,
        source_meta=source_meta,
        slots=slots,
        corpus=corpus,
        corpus_state=corpus_state,
        categories=categories,
        selected=selected,
        rows=rows,
        categories_state=categories_state,
    )
    fail(
        validate_corpus(corpus, slots=slots, categories=categories)
        + validate_golden(
            rows,
            source_slots={(slot.document_key, slot.category): slot for slot in slots},
            document_keys={slot.document_key for slot in slots},
            corpus=set(corpus),
            categories=categories,
            report=report,
        )
        + validate_routing()
    )
    write_text(GOLDEN_PATH, dump_jsonl(rows))
    write_text(REPORT_PATH, dump_json(report))
    totals = report["totals"]
    print(f"built {totals['samples']} rows from {SOURCE_PATH.name} (sample seed {seed})")
    print(f"  {totals['with_evidence']} with evidence / {totals['empty_evidence']} empty evidence")
    print(f"  {totals['document_keys']} contracts, {totals['categories']} categories")
    print(f"  corpus {report['corpus']['contracts']} contracts (seed {CORPUS_SEED})")
    print(f"  {report['outputs']['path']} sha256 {report['outputs']['sha256']}")
    return 0


def command_verify() -> int:
    if not REPORT_PATH.exists():
        raise GoldensetError(f"{relative(REPORT_PATH)}: missing; run the builder first")
    report: Any = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    slots = parse_slots(json.loads(SOURCE_PATH.read_text(encoding="utf-8")))
    categories = categories_of(slots)
    if ensure_categories_file(categories) != "verified":
        raise GoldensetError(f"{CATEGORIES_PATH.name}: was regenerated; re-run the builder")
    source_meta = source_metadata(slots)
    for key in ("sha256", "question_slots", "contracts", "categories"):
        if source_meta[key] != report["source"][key]:
            raise GoldensetError(f"source {key} differs from the build report")
    corpus = select_corpus(slots, categories, CORPUS_SIZE, CORPUS_SEED)
    if ensure_corpus_file(corpus, source_meta) != "verified":
        raise GoldensetError(f"{CORPUS_PATH.name}: was regenerated; re-run the builder")
    observed = GOLDEN_PATH.read_text(encoding="utf-8")
    stored: list[dict[str, Any]] = [
        json.loads(line) for line in observed.splitlines() if line.strip()
    ]
    # 产物加载后优先执行语义校验，以便在被篡改时精准定位违规业务规则，而非仅报错字节不匹配
    fail(
        validate_corpus(corpus, slots=slots, categories=categories)
        + validate_golden(
            stored,
            source_slots={(slot.document_key, slot.category): slot for slot in slots},
            document_keys={slot.document_key for slot in slots},
            corpus=set(corpus),
            categories=categories,
            report=report,
        )
        + validate_routing()
    )
    derived = golden_rows(sample_slots(slots, categories, set(corpus), report["seed"]))
    if dump_jsonl(derived) != observed:
        raise GoldensetError(f"{GOLDEN_PATH.name} is not reproducible from seed {report['seed']}")
    print(f"verified {len(stored)} rows over {len(corpus)} corpus contracts")
    print(f"  reproduce from sample seed {report['seed']}, corpus seed {CORPUS_SEED}")
    print(f"  sha256 {hashlib.sha256(observed.encode('utf-8')).hexdigest()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建并校验 ClauseRAG CUAD 黄金基准集。")
    parser.add_argument("--verify", action="store_true", help="根据固定种子重算比对，不写盘")
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"抽样随机种子；语料库种子固定（默认 {DEFAULT_SEED}）",
    )
    args = parser.parse_args(argv)
    try:
        return command_verify() if args.verify else command_build(args.seed)
    except GoldensetError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
