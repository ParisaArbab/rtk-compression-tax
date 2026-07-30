#!/usr/bin/env python3

"""
Run the same terminal command in two conditions:

1. Raw condition:
   pytest pilot_example/test_example.py -vv

2. RTK condition:
   rtk pytest pilot_example/test_example.py -vv

The script saves:
- raw terminal output
- RTK terminal output
- output diff
- experiment metrics
- command information
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Compare raw terminal output with RTK-compressed output."
    )

    parser.add_argument(
        "--name",
        default="experiment",
        help="A short name for this experiment.",
    )

    parser.add_argument(
        "--working-directory",
        type=Path,
        default=Path.cwd(),
        help="Directory where the tested command should run.",
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("results/captures"),
        help="Directory where experiment results should be saved.",
    )

    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run. Place it after --.",
    )

    args = parser.parse_args()

    # argparse keeps the separator in some situations.
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]

    if not args.command:
        parser.error(
            "No command was provided. Example:\n"
            "python scripts/run_output_capture.py "
            "--name pilot -- pytest pilot_example/test_example.py -vv"
        )

    return args


def approximate_tokens(text: str) -> float:
    """
    Estimate token count using bytes / 4.

    This follows RTK's simple approximation.
    It is not an exact model tokenizer count.
    """

    byte_count = len(text.encode("utf-8"))
    return round(byte_count / 4, 2)


def safe_reduction(original: float, compressed: float) -> float:
    """Calculate percentage reduction without dividing by zero."""

    if original == 0:
        return 0.0

    return round((1 - compressed / original) * 100, 2)


def run_command(
    command: list[str],
    working_directory: Path,
) -> dict[str, Any]:
    """
    Run one command and capture combined stdout and stderr.

    A failing test normally returns exit code 1. That is not treated as
    a Python exception because failed tests are expected in this research.
    """

    start_time = time.perf_counter()

    try:
        completed_process = subprocess.run(
            command,
            cwd=working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
            check=False,
        )

        output = completed_process.stdout or ""
        execution_error = None
        exit_code = completed_process.returncode

    except FileNotFoundError as error:
        output = f"Command could not be started: {error}\n"
        execution_error = str(error)
        exit_code = 127

    except OSError as error:
        output = f"Operating system error: {error}\n"
        execution_error = str(error)
        exit_code = 126

    elapsed_seconds = time.perf_counter() - start_time

    encoded_output = output.encode("utf-8")

    return {
        "command": command,
        "command_text": shlex.join(command),
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "output": output,
        "character_count": len(output),
        "line_count": len(output.splitlines()),
        "byte_count": len(encoded_output),
        "approximate_tokens": approximate_tokens(output),
        "execution_error": execution_error,
    }


def create_output_directory(
    base_directory: Path,
    experiment_name: str,
) -> Path:
    """Create a unique directory for the current experiment."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in experiment_name
    )

    experiment_directory = base_directory / f"{timestamp}_{safe_name}"
    experiment_directory.mkdir(parents=True, exist_ok=False)

    return experiment_directory


def write_text(path: Path, content: str) -> None:
    """Write UTF-8 text to a file."""

    path.write_text(content, encoding="utf-8")


def create_diff(raw_output: str, rtk_output: str) -> str:
    """Create a unified line-by-line comparison."""

    raw_lines = raw_output.splitlines(keepends=True)
    rtk_lines = rtk_output.splitlines(keepends=True)

    diff_lines = difflib.unified_diff(
        raw_lines,
        rtk_lines,
        fromfile="raw_output.txt",
        tofile="rtk_output.txt",
        lineterm="",
    )

    return "\n".join(diff_lines)


def build_metrics(
    experiment_name: str,
    working_directory: Path,
    raw_result: dict[str, Any],
    rtk_result: dict[str, Any],
) -> dict[str, Any]:
    """Build the final experiment measurements."""

    raw_bytes = raw_result["byte_count"]
    rtk_bytes = rtk_result["byte_count"]

    raw_tokens = raw_result["approximate_tokens"]
    rtk_tokens = rtk_result["approximate_tokens"]

    return {
        "experiment": {
            "name": experiment_name,
            "created_at": datetime.now().astimezone().isoformat(),
            "working_directory": str(working_directory.resolve()),
        },
        "environment": {
            "operating_system": platform.platform(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "rtk_path": shutil.which("rtk"),
        },
        "raw": {
            key: value
            for key, value in raw_result.items()
            if key != "output"
        },
        "rtk": {
            key: value
            for key, value in rtk_result.items()
            if key != "output"
        },
        "comparison": {
            "same_exit_code": (
                raw_result["exit_code"] == rtk_result["exit_code"]
            ),
            "raw_exit_code": raw_result["exit_code"],
            "rtk_exit_code": rtk_result["exit_code"],
            "raw_byte_count": raw_bytes,
            "rtk_byte_count": rtk_bytes,
            "bytes_removed": raw_bytes - rtk_bytes,
            "byte_reduction_percent": safe_reduction(
                raw_bytes,
                rtk_bytes,
            ),
            "raw_approximate_tokens": raw_tokens,
            "rtk_approximate_tokens": rtk_tokens,
            "approximate_tokens_removed": round(
                raw_tokens - rtk_tokens,
                2,
            ),
            "approximate_token_reduction_percent": safe_reduction(
                raw_tokens,
                rtk_tokens,
            ),
            "raw_line_count": raw_result["line_count"],
            "rtk_line_count": rtk_result["line_count"],
            "lines_removed": (
                raw_result["line_count"] - rtk_result["line_count"]
            ),
            "raw_elapsed_seconds": raw_result["elapsed_seconds"],
            "rtk_elapsed_seconds": rtk_result["elapsed_seconds"],
            "outputs_are_identical": (
                raw_result["output"] == rtk_result["output"]
            ),
        },
    }


def print_summary(
    experiment_directory: Path,
    metrics: dict[str, Any],
) -> None:
    """Print a short experiment summary."""

    comparison = metrics["comparison"]

    print("\nExperiment completed")
    print("=" * 60)
    print(f"Results directory: {experiment_directory}")
    print(
        f"Raw exit code:      {comparison['raw_exit_code']}"
    )
    print(
        f"RTK exit code:      {comparison['rtk_exit_code']}"
    )
    print(
        f"Raw lines:          {comparison['raw_line_count']}"
    )
    print(
        f"RTK lines:          {comparison['rtk_line_count']}"
    )
    print(
        f"Raw approx. tokens: {comparison['raw_approximate_tokens']}"
    )
    print(
        f"RTK approx. tokens: {comparison['rtk_approximate_tokens']}"
    )
    print(
        "Token reduction:    "
        f"{comparison['approximate_token_reduction_percent']}%"
    )
    print(
        f"Raw time:           {comparison['raw_elapsed_seconds']} seconds"
    )
    print(
        f"RTK time:           {comparison['rtk_elapsed_seconds']} seconds"
    )
    print("=" * 60)


def main() -> int:
    """Main program."""

    args = parse_arguments()

    working_directory = args.working_directory.expanduser().resolve()
    output_directory = args.output_directory.expanduser().resolve()

    if not working_directory.exists():
        print(
            f"Error: working directory does not exist: "
            f"{working_directory}",
            file=sys.stderr,
        )
        return 2

    if shutil.which("rtk") is None:
        print(
            "Error: RTK was not found in PATH. Run `rtk --version` "
            "to check the installation.",
            file=sys.stderr,
        )
        return 2

    experiment_directory = create_output_directory(
        output_directory,
        args.name,
    )

    raw_command = list(args.command)
    rtk_command = ["rtk", *raw_command]

    print(f"Working directory: {working_directory}")
    print(f"Raw command:       {shlex.join(raw_command)}")
    print(f"RTK command:       {shlex.join(rtk_command)}")

    print("\nRunning raw condition...")
    raw_result = run_command(
        raw_command,
        working_directory,
    )

    print("Running RTK condition...")
    rtk_result = run_command(
        rtk_command,
        working_directory,
    )

    raw_output_path = experiment_directory / "raw_output.txt"
    rtk_output_path = experiment_directory / "rtk_output.txt"
    diff_path = experiment_directory / "output_diff.txt"
    metrics_path = experiment_directory / "metrics.json"
    commands_path = experiment_directory / "commands.txt"

    write_text(raw_output_path, raw_result["output"])
    write_text(rtk_output_path, rtk_result["output"])

    diff_content = create_diff(
        raw_result["output"],
        rtk_result["output"],
    )
    write_text(diff_path, diff_content)

    command_information = (
        f"Working directory:\n{working_directory}\n\n"
        f"Raw command:\n{raw_result['command_text']}\n\n"
        f"RTK command:\n{rtk_result['command_text']}\n"
    )
    write_text(commands_path, command_information)

    metrics = build_metrics(
        experiment_name=args.name,
        working_directory=working_directory,
        raw_result=raw_result,
        rtk_result=rtk_result,
    )

    metrics_path.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )

    print_summary(experiment_directory, metrics)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())