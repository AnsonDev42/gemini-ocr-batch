from __future__ import annotations

import argparse
from pathlib import Path

from src.config import load_config
from src.env import load_env
from src.flow import orchestrate_gemini_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gemini-ocr-batch")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("command", choices=["run-once"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    project_root = args.project_root.resolve()
    load_env(project_root)
    config_result = load_config(args.config)

    if args.command == "run-once":
        orchestrate_gemini_batch(config=config_result.config)
        return 0

    raise AssertionError("unreachable")
