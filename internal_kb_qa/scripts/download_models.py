"""下载/复制所需模型到 internal_kb_qa/models 对应目录。

优先级（可用 --source 覆盖）：
1. 参考项目已有模型 -> 直接复制
2. ModelScope（国内推荐，默认优先）
3. HuggingFace（读环境变量 HF_ENDPOINT，如 https://hf-mirror.com）

用法：
    # 推荐（国内服务器）
    uv run python -m internal_kb_qa.scripts.download_models bge-m3 --force
    uv run python -m internal_kb_qa.scripts.download_models all --source modelscope --force

    export HF_ENDPOINT=https://hf-mirror.com
    uv run python -m internal_kb_qa.scripts.download_models bge-m3 --source hf --force
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

MODELS = {
    "bge-reranker-v2-m3": {
        "repo_id": "BAAI/bge-reranker-v2-m3",
        # 权重文件任选其一即可（新仓库多为 safetensors）
        "required": ("config.json", "tokenizer.json", "sentencepiece.bpe.model"),
        "weight_any_of": ("model.safetensors", "pytorch_model.bin"),
    },
    "bge-m3": {
        "repo_id": "BAAI/bge-m3",
        "required": ("config.json", "sentencepiece.bpe.model"),
        "weight_any_of": ("pytorch_model.bin", "model.safetensors", "onnx/model.onnx"),
    },
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
REFERENCE_MODELS_DIR = Path("E:/study_project/Itcast_qa_system/rag_qa/models")


def copy_from_reference(name: str, target: Path) -> bool:
    source = REFERENCE_MODELS_DIR / name
    if not source.exists():
        return False
    if not _is_complete(name, source):
        return False

    shutil.copytree(source, target, dirs_exist_ok=True)
    print(f"[OK] 已从参考项目复制模型: {source} -> {target}")
    return True


def download_from_modelscope(name: str, target: Path) -> bool:
    try:
        from modelscope import snapshot_download
    except ImportError:
        print(
            "[WARN] 未安装 modelscope。请执行: uv pip install modelscope",
            file=sys.stderr,
        )
        return False

    try:
        snapshot_download(
            model_id=MODELS[name]["repo_id"],
            local_dir=str(target),
        )
        print(f"[OK] 已从 ModelScope 下载模型: {MODELS[name]['repo_id']} -> {target}")
        return True
    except Exception as exc:
        print(f"[WARN] ModelScope 下载失败: {exc}", file=sys.stderr)
        return False


def download_from_huggingface(name: str, target: Path) -> bool:
    endpoint = os.getenv("HF_ENDPOINT", "").rstrip("/")
    if endpoint:
        print(f"[INFO] 使用 HF_ENDPOINT={endpoint}")
    else:
        print(
            "[WARN] 未设置 HF_ENDPOINT，国内直连 huggingface.co 通常极慢。"
            "建议: export HF_ENDPOINT=https://hf-mirror.com",
            file=sys.stderr,
        )

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[WARN] 未安装 huggingface_hub", file=sys.stderr)
        return False

    try:
        kwargs = {
            "repo_id": MODELS[name]["repo_id"],
            "local_dir": str(target),
        }
        # 新版忽略该参数，旧版需要；兼容传参
        try:
            snapshot_download(**kwargs, local_dir_use_symlinks=False)
        except TypeError:
            snapshot_download(**kwargs)
        print(f"[OK] 已从 HuggingFace 下载模型: {MODELS[name]['repo_id']} -> {target}")
        return True
    except Exception as exc:
        print(f"[WARN] HuggingFace 下载失败: {exc}", file=sys.stderr)
        return False


def _is_complete(name: str, target: Path) -> bool:
    meta = MODELS[name]
    if not all((target / filename).exists() for filename in meta["required"]):
        return False
    weight_opts = meta.get("weight_any_of") or ()
    if weight_opts and not any((target / filename).exists() for filename in weight_opts):
        return False
    return True


def check_model(name: str, target: Path) -> bool:
    meta = MODELS[name]
    missing = [f for f in meta["required"] if not (target / f).exists()]
    weight_opts = meta.get("weight_any_of") or ()
    if weight_opts and not any((target / filename).exists() for filename in weight_opts):
        missing.append(f"权重文件({' 或 '.join(weight_opts)})")
    if missing:
        print(f"[FAIL] 模型文件不完整: {target}\n缺少: {missing}", file=sys.stderr)
        return False
    print(f"[OK] 模型就绪: {target}")
    return True


def _reset_target(target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
        print(f"[INFO] 已清理不完整目录: {target}")
    target.mkdir(parents=True, exist_ok=True)


def download_one(name: str, *, source: str = "auto", force: bool = False) -> bool:
    if name not in MODELS:
        print(f"未知模型: {name}，可选值: {list(MODELS)}", file=sys.stderr)
        return False

    target = MODELS_DIR / name
    target.mkdir(parents=True, exist_ok=True)

    if force:
        _reset_target(target)
    elif check_model(name, target):
        return True
    else:
        # 半截下载会导致 HF 反复 “local file already exists” 而不重下大文件
        print(
            "[INFO] 检测到不完整模型，将清理后重新下载。"
            "若要跳过清理请不要使用半截目录。",
            file=sys.stderr,
        )
        _reset_target(target)

    if copy_from_reference(name, target) and check_model(name, target):
        return True

    order: list[str]
    if source == "modelscope":
        order = ["modelscope"]
    elif source == "hf":
        order = ["hf"]
    else:
        # 国内默认优先 ModelScope，避免 HF 镜像证书/回源问题
        order = ["modelscope", "hf"]

    for src in order:
        ok = (
            download_from_modelscope(name, target)
            if src == "modelscope"
            else download_from_huggingface(name, target)
        )
        if ok and check_model(name, target):
            return True
        # 当前源失败或不完整时清掉，避免污染下一源
        if target.exists() and not _is_complete(name, target):
            _reset_target(target)

    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="下载或复制 RAG 所需模型")
    parser.add_argument(
        "models",
        nargs="*",
        default=["bge-reranker-v2-m3"],
        help="模型名，如 bge-m3；填 all 表示全部",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "modelscope", "hf"),
        default="auto",
        help="下载源：auto=先 ModelScope 再 HF；modelscope / hf 指定单一源",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制删除已有目录后重新下载（半截文件必加）",
    )
    args = parser.parse_args()

    if args.models == ["all"]:
        names = list(MODELS)
    else:
        names = args.models

    failed = [
        name
        for name in names
        if not download_one(name, source=args.source, force=args.force)
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
