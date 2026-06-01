#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


DEFAULT_MODELS = (
    "Qwen/Qwen2.5-3B",
    "gpt2",
)

DEFAULT_DATASETS = (
    "tatsu-lab/alpaca",
    "cais/mmlu:all",
    "Rowan/hellaswag",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prewarm shared Hugging Face model/tokenizer/dataset caches.",
    )
    parser.add_argument(
        "--cache-root",
        default="/data2/lyc/researchclaw_cache",
        help="Shared cache root used by experiment.docker.shared_cache_root",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        default=[],
        help="Model repo id to prewarm. May be repeated.",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        dest="datasets",
        default=[],
        help="Dataset spec to prewarm. Format: repo or repo:config. May be repeated.",
    )
    parser.add_argument(
        "--skip-models",
        action="store_true",
        help="Skip model/tokenizer prewarming.",
    )
    parser.add_argument(
        "--skip-datasets",
        action="store_true",
        help="Skip dataset prewarming.",
    )
    return parser.parse_args()


def _ensure_env(cache_root: Path) -> tuple[Path, Path]:
    hf_root = cache_root / "huggingface"
    datasets_root = cache_root / "datasets"
    torch_root = cache_root / "torch"
    for path in (hf_root, datasets_root, torch_root):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(hf_root)
    os.environ["HF_HUB_CACHE"] = str(hf_root / "hub")
    os.environ["HF_ASSETS_CACHE"] = str(hf_root / "assets")
    os.environ["TRANSFORMERS_CACHE"] = str(hf_root / "transformers")
    os.environ["HF_DATASETS_CACHE"] = str(datasets_root)
    os.environ["TORCH_HOME"] = str(torch_root)
    return hf_root, datasets_root


def _prewarm_models(models: list[str]) -> list[dict[str, str]]:
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer

    results: list[dict[str, str]] = []
    for model_id in models:
        snapshot_path = snapshot_download(
            repo_id=model_id,
            local_files_only=False,
            resume_download=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        results.append(
            {
                "model": model_id,
                "snapshot_path": str(snapshot_path),
                "tokenizer_class": tokenizer.__class__.__name__,
            }
        )
    return results


def _prewarm_datasets(dataset_specs: list[str], datasets_root: Path) -> list[dict[str, str]]:
    from datasets import load_dataset

    results: list[dict[str, str]] = []
    for spec in dataset_specs:
        if ":" in spec:
            dataset_name, config_name = spec.split(":", 1)
        else:
            dataset_name, config_name = spec, None
        ds = load_dataset(
            dataset_name,
            config_name,
            cache_dir=str(datasets_root),
        )
        keys = list(ds.keys()) if hasattr(ds, "keys") else []
        results.append(
            {
                "dataset": dataset_name,
                "config": config_name or "",
                "splits": ",".join(keys),
            }
        )
    return results


def main() -> int:
    args = _parse_args()
    cache_root = Path(args.cache_root).expanduser().resolve()
    hf_root, datasets_root = _ensure_env(cache_root)

    models = args.models or list(DEFAULT_MODELS)
    dataset_specs = args.datasets or list(DEFAULT_DATASETS)

    payload: dict[str, object] = {
        "cache_root": str(cache_root),
        "hf_root": str(hf_root),
        "datasets_root": str(datasets_root),
        "models": [],
        "datasets": [],
    }

    if not args.skip_models:
        payload["models"] = _prewarm_models(models)
    if not args.skip_datasets:
        payload["datasets"] = _prewarm_datasets(dataset_specs, datasets_root)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
