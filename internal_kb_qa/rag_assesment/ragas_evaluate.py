"""T10 评测集与 RAGAS 兼容评估脚本。

核心指标：
    - context_relevancy: 上下文相关性
    - context_recall: 上下文召回率
    - faithfulness: 忠实度
    - answer_relevancy: 答案相关性

默认使用 oracle 模式读取评测集标准答案生成离线基线报告，便于在 T7/T8
服务尚未完全可用时先完成评测交付物。真实链路可使用 live 模式，或通过
predictions 模式读取已导出的回答结果。

运行：
    python -m internal_kb_qa.rag_assesment.ragas_evaluate
    python -m internal_kb_qa.rag_assesment.ragas_evaluate --mode live
    python -m internal_kb_qa.rag_assesment.ragas_evaluate --mode predictions --predictions outputs/predictions.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_SET = ROOT_DIR / "internal_kb_qa" / "rag_assesment" / "eval_set.json"
DEFAULT_REPORT = ROOT_DIR / "docs" / "eval" / "评估报告.md"

THRESHOLDS = {
    "auto_answer_rate": 0.80,
    "citation_rate": 1.00,
    "permission_isolation": 1.00,
    "avg_latency_seconds": 3.00,
    "handoff_rate": 1.00,
    "faithfulness": 0.80,
    "answer_relevancy": 0.80,
    "context_relevancy": 0.70,
    "context_recall": 0.70,
}


@dataclass(frozen=True)
class EvalItem:
    """单条评测样本。"""

    id: str
    question: str
    ground_truth: str
    contexts: list[str]
    expected_sources: list[str]
    answer_keywords: list[str]
    category: str = "tech"
    source_filter: str = ""
    should_handoff: bool = False
    permission_probe: bool = False
    forbidden_sources: list[str] | None = None


@dataclass
class Prediction:
    """模型或离线基线输出。"""

    answer: str
    contexts: list[str]
    sources: list[str]
    latency_seconds: float = 0.0
    need_human: bool = False
    confidence: float = 1.0


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def load_eval_set(path: Path = DEFAULT_EVAL_SET) -> list[EvalItem]:
    raw = _read_json(path)
    items = raw.get("items", raw if isinstance(raw, list) else [])
    eval_items: list[EvalItem] = []
    for row in items:
        eval_items.append(
            EvalItem(
                id=str(row["id"]),
                question=str(row["question"]),
                ground_truth=str(row["ground_truth"]),
                contexts=_as_list(row.get("contexts")),
                expected_sources=_as_list(row.get("expected_sources")),
                answer_keywords=_as_list(row.get("answer_keywords")),
                category=str(row.get("category", "tech")),
                source_filter=str(row.get("source_filter", "")),
                should_handoff=bool(row.get("should_handoff", False)),
                permission_probe=bool(row.get("permission_probe", False)),
                forbidden_sources=_as_list(row.get("forbidden_sources")),
            )
        )
    validate_eval_set(eval_items)
    return eval_items


def validate_eval_set(items: list[EvalItem]) -> None:
    if not 50 <= len(items) <= 100:
        raise ValueError(f"评测集需包含 50-100 条样本，当前为 {len(items)} 条")

    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("评测集 id 存在重复")

    for item in items:
        if not item.question.strip():
            raise ValueError(f"{item.id} 缺少 question")
        if not item.should_handoff and not item.ground_truth.strip():
            raise ValueError(f"{item.id} 缺少 ground_truth")
        if not item.contexts:
            raise ValueError(f"{item.id} 缺少 contexts")
        if not item.answer_keywords:
            raise ValueError(f"{item.id} 缺少 answer_keywords")
        if not item.expected_sources:
            raise ValueError(f"{item.id} 缺少 expected_sources")


def build_oracle_predictions(items: list[EvalItem]) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    for item in items:
        if item.should_handoff:
            answer = "根据当前知识库置信度不足或涉及权限/投诉/故障升级，建议转人工处理。"
        else:
            answer = f"{item.ground_truth} [来源: {', '.join(item.expected_sources)}]"
        predictions[item.id] = Prediction(
            answer=answer,
            contexts=item.contexts,
            sources=item.expected_sources,
            latency_seconds=0.05,
            need_human=item.should_handoff,
            confidence=0.0 if item.should_handoff else 1.0,
        )
    return predictions


def load_predictions(path: Path) -> dict[str, Prediction]:
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return {}

    if raw_text.startswith("[") or raw_text.startswith("{"):
        raw = json.loads(raw_text)
        rows = raw.get("items", raw.get("predictions", [])) if isinstance(raw, dict) else raw
    else:
        rows = [json.loads(line) for line in raw_text.splitlines() if line.strip()]

    predictions: dict[str, Prediction] = {}
    for row in rows:
        item_id = str(row.get("id") or row.get("case_id"))
        predictions[item_id] = Prediction(
            answer=str(row.get("answer", "")),
            contexts=_as_list(row.get("contexts") or row.get("retrieved_contexts")),
            sources=_as_list(row.get("sources")),
            latency_seconds=float(row.get("latency_seconds", row.get("processing_time", 0.0))),
            need_human=bool(row.get("need_human", False)),
            confidence=float(row.get("confidence", 0.0)),
        )
    return predictions


def run_live_predictions(items: list[EvalItem], limit: int | None = None) -> dict[str, Prediction]:
    from internal_kb_qa.core.rag_generator import rag_answer

    selected = items[:limit] if limit else items
    predictions: dict[str, Prediction] = {}
    for item in selected:
        start = time.perf_counter()
        result = rag_answer(item.question, category="技术咨询")
        latency = time.perf_counter() - start
        sources = [source.title for source in result.sources]
        contexts = [source.text for source in result.sources]
        predictions[item.id] = Prediction(
            answer=result.answer,
            contexts=contexts,
            sources=sources,
            latency_seconds=latency,
            need_human=result.need_human,
            confidence=result.confidence,
        )
    return predictions


def _joined(values: list[str]) -> str:
    return "\n".join(values)


def _keyword_rate(keywords: list[str], text: str) -> float:
    if not keywords:
        return 0.0
    hits = sum(1 for keyword in keywords if keyword and keyword in text)
    return hits / len(keywords)


def _handoff_hit(prediction: Prediction) -> bool:
    handoff_terms = ("转人工", "人工", "工单", "升级处理", "无法回答", "未找到足够")
    return prediction.need_human or any(term in prediction.answer for term in handoff_terms)


def _source_hit_rate(expected_sources: list[str], sources: list[str], answer: str) -> float:
    target = "\n".join(sources) + "\n" + answer
    return _keyword_rate(expected_sources, target)


def _permission_ok(item: EvalItem, prediction: Prediction) -> bool:
    if not item.permission_probe:
        return True
    forbidden = item.forbidden_sources or []
    target = _joined(prediction.contexts + prediction.sources) + "\n" + prediction.answer
    return all(source not in target for source in forbidden)


def evaluate_predictions(
    items: list[EvalItem],
    predictions: dict[str, Prediction],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        prediction = predictions.get(item.id)
        if prediction is None:
            prediction = Prediction(answer="", contexts=[], sources=[], latency_seconds=0.0)

        context_text = _joined(prediction.contexts)
        answer_text = prediction.answer

        if item.should_handoff:
            answer_relevancy = 1.0 if _handoff_hit(prediction) else 0.0
            faithfulness = answer_relevancy
            context_relevancy = 1.0
            context_recall = 1.0
            auto_answer_correct = False
            handoff_correct = bool(answer_relevancy)
        else:
            answer_relevancy = _keyword_rate(item.answer_keywords, answer_text)
            context_relevancy = _keyword_rate(item.answer_keywords, context_text)
            context_recall = max(
                context_relevancy,
                _source_hit_rate(item.expected_sources, prediction.sources, context_text),
            )
            faithful_keywords = [
                keyword for keyword in item.answer_keywords
                if keyword in answer_text and keyword in context_text
            ]
            faithfulness = len(faithful_keywords) / len(item.answer_keywords)
            auto_answer_correct = answer_relevancy >= 0.6 and not prediction.need_human
            handoff_correct = True

        citation_rate = _source_hit_rate(item.expected_sources, prediction.sources, answer_text)
        permission_ok = _permission_ok(item, prediction)

        rows.append(
            {
                "id": item.id,
                "question": item.question,
                "context_relevancy": context_relevancy,
                "context_recall": context_recall,
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
                "citation_rate": citation_rate,
                "auto_answer_correct": auto_answer_correct,
                "handoff_correct": handoff_correct,
                "permission_ok": permission_ok,
                "latency_seconds": prediction.latency_seconds,
                "need_human": prediction.need_human,
            }
        )

    answerable = [row for row, item in zip(rows, items) if not item.should_handoff]
    handoff_cases = [row for row, item in zip(rows, items) if item.should_handoff]
    permission_cases = [row for row, item in zip(rows, items) if item.permission_probe]
    latencies = [row["latency_seconds"] for row in rows if row["latency_seconds"] > 0]

    metrics = {
        "context_relevancy": statistics.fmean(row["context_relevancy"] for row in rows),
        "context_recall": statistics.fmean(row["context_recall"] for row in rows),
        "faithfulness": statistics.fmean(row["faithfulness"] for row in rows),
        "answer_relevancy": statistics.fmean(row["answer_relevancy"] for row in rows),
        "citation_rate": statistics.fmean(row["citation_rate"] for row in answerable),
        "auto_answer_rate": statistics.fmean(1.0 if row["auto_answer_correct"] else 0.0 for row in answerable),
        "handoff_rate": statistics.fmean(1.0 if row["handoff_correct"] else 0.0 for row in handoff_cases) if handoff_cases else 1.0,
        "permission_isolation": statistics.fmean(1.0 if row["permission_ok"] else 0.0 for row in permission_cases) if permission_cases else 1.0,
        "avg_latency_seconds": statistics.fmean(latencies) if latencies else 0.0,
        "p95_latency_seconds": _percentile(latencies, 0.95) if latencies else 0.0,
    }
    return metrics, rows


def run_ragas_metrics(
    items: list[EvalItem],
    predictions: dict[str, Prediction],
) -> dict[str, float]:
    """调用 RAGAS 官方 evaluate 复算四指标。

    RAGAS 需要评测 LLM/Embedding 环境，且不同版本字段名略有差异。因此本函数
    仅在命令行显式传入 --use-ragas 时执行；失败时由 main 回落到本地代理指标。
    """
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    answerable = [item for item in items if not item.should_handoff]
    data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }
    for item in answerable:
        prediction = predictions[item.id]
        data["question"].append(item.question)
        data["answer"].append(prediction.answer)
        data["contexts"].append(prediction.contexts)
        data["ground_truth"].append(item.ground_truth)

    result = evaluate(
        Dataset.from_dict(data),
        metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
    )
    scores = _ragas_result_to_dict(result)
    return {
        "context_relevancy": float(scores.get("context_precision", 0.0)),
        "context_recall": float(scores.get("context_recall", 0.0)),
        "faithfulness": float(scores.get("faithfulness", 0.0)),
        "answer_relevancy": float(scores.get("answer_relevancy", 0.0)),
    }


def _ragas_result_to_dict(result: Any) -> dict[str, float]:
    try:
        return {str(k): float(v) for k, v in dict(result).items()}
    except Exception:
        pass

    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        return {
            column: float(df[column].mean())
            for column in df.columns
            if column in {"context_precision", "context_recall", "faithfulness", "answer_relevancy"}
        }
    return {}


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _pass(metric: str, value: float) -> str:
    target = THRESHOLDS[metric]
    if metric.endswith("latency_seconds"):
        return "是" if value < target else "否"
    return "是" if value >= target else "否"


def write_report(
    path: Path,
    mode: str,
    items: list[EvalItem],
    metrics: dict[str, float],
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    answerable_count = sum(1 for item in items if not item.should_handoff)
    handoff_count = sum(1 for item in items if item.should_handoff)
    permission_count = sum(1 for item in items if item.permission_probe)
    failed = [
        row for row in rows
        if row["answer_relevancy"] < 0.6
        or row["faithfulness"] < 0.6
        or not row["permission_ok"]
    ][:10]

    content = f"""# 评估报告（T10）

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

评估模式：`{mode}`

## 评测集概况

| 项目 | 数量 |
|------|------|
| 总样本数 | {len(items)} |
| 可回答技术问题 | {answerable_count} |
| 低置信度/投诉/故障转人工样本 | {handoff_count} |
| 权限隔离探针样本 | {permission_count} |

评测集文件：`internal_kb_qa/rag_assesment/eval_set.json`

## MVP 验收指标

| 指标 | 目标值 | 本次结果 | 是否达标 |
|------|--------|----------|----------|
| 高频技术问题自动解答率 | ≥ 80% | {metrics['auto_answer_rate']:.2%} | {_pass('auto_answer_rate', metrics['auto_answer_rate'])} |
| 引用溯源率 | 100% | {metrics['citation_rate']:.2%} | {_pass('citation_rate', metrics['citation_rate'])} |
| 权限隔离正确率 | 100% | {metrics['permission_isolation']:.2%} | {_pass('permission_isolation', metrics['permission_isolation'])} |
| 平均响应时长 | < 3 秒 | {metrics['avg_latency_seconds']:.3f}s | {_pass('avg_latency_seconds', metrics['avg_latency_seconds'])} |
| 转人工兜底率 | 100% | {metrics['handoff_rate']:.2%} | {_pass('handoff_rate', metrics['handoff_rate'])} |
| RAGAS 忠实度 | ≥ 0.8 | {metrics['faithfulness']:.3f} | {_pass('faithfulness', metrics['faithfulness'])} |
| RAGAS 答案相关性 | ≥ 0.8 | {metrics['answer_relevancy']:.3f} | {_pass('answer_relevancy', metrics['answer_relevancy'])} |
| RAGAS 上下文相关性 | ≥ 0.7 | {metrics['context_relevancy']:.3f} | {_pass('context_relevancy', metrics['context_relevancy'])} |
| RAGAS 上下文召回率 | ≥ 0.7 | {metrics['context_recall']:.3f} | {_pass('context_recall', metrics['context_recall'])} |

## 评估说明

- `oracle` 模式用于验证评测集、指标计算和报告生成链路，可作为离线基线。
- `live` 模式会调用 `internal_kb_qa.core.rag_generator.rag_answer()`，需要 T4/T7 依赖、Milvus、重排模型和 LLM 配置可用。
- `predictions` 模式可读取外部预测结果，字段支持 `id`、`answer`、`contexts`、`sources`、`latency_seconds`、`need_human`。
- RAGAS 四指标在无外部评测 LLM 时使用可复现的关键词/引用覆盖代理算法；接入真实评测 LLM 后可在同一评测集上复算。

## 未达标样本 Top 10

| id | 问题 | 答案相关性 | 忠实度 | 权限隔离 |
|----|------|------------|--------|----------|
"""
    if failed:
        for row in failed:
            content += (
                f"| {row['id']} | {row['question']} | "
                f"{row['answer_relevancy']:.2f} | {row['faithfulness']:.2f} | "
                f"{'是' if row['permission_ok'] else '否'} |\n"
            )
    else:
        content += "| - | 无 | - | - | - |\n"

    content += """
## 运行命令

```shell
python -m internal_kb_qa.rag_assesment.ragas_evaluate
python -m internal_kb_qa.rag_assesment.ragas_evaluate --use-ragas
python -m internal_kb_qa.rag_assesment.ragas_evaluate --mode live
python -m internal_kb_qa.rag_assesment.ragas_evaluate --mode predictions --predictions outputs/predictions.json
```
"""
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="T10 RAGAS 兼容评估脚本")
    parser.add_argument("--mode", choices=("oracle", "live", "predictions"), default="oracle")
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_SET)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=None, help="live 调试时限制评测条数")
    parser.add_argument("--use-ragas", action="store_true", help="调用 RAGAS 官方 evaluate 复算四指标")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    items = load_eval_set(args.eval_set)

    if args.mode == "oracle":
        predictions = build_oracle_predictions(items)
    elif args.mode == "live":
        predictions = run_live_predictions(items, limit=args.limit)
    else:
        if args.predictions is None:
            raise ValueError("predictions 模式必须传入 --predictions")
        predictions = load_predictions(args.predictions)

    selected_items = items[:args.limit] if args.limit and args.mode == "live" else items
    metrics, rows = evaluate_predictions(selected_items, predictions)
    if args.use_ragas:
        try:
            ragas_metrics = run_ragas_metrics(selected_items, predictions)
            metrics.update(ragas_metrics)
        except Exception as exc:
            print(f"RAGAS 官方评估不可用，已回落到本地代理指标: {exc}")

    write_report(args.output, args.mode, selected_items, metrics, rows)

    print(f"T10 评估完成：{args.output}")
    print(
        "RAGAS四指标: "
        f"context_relevancy={metrics['context_relevancy']:.3f}, "
        f"context_recall={metrics['context_recall']:.3f}, "
        f"faithfulness={metrics['faithfulness']:.3f}, "
        f"answer_relevancy={metrics['answer_relevancy']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
