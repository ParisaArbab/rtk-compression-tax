#!/usr/bin/env python3
"""
Download and save the metadata for one SWE-bench Lite instance.

This script does not run the tests yet. It only prepares the information
needed for the experiment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from datasets import load_dataset

DEFAULT_DATASET = "princeton-nlp/SWE-bench_Lite"


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments."""

    parser = argparse.ArgumentParser(description="Prepare one SWE-bench Lite instance.")

    parser.add_argument(
        "--instance-id",
        required=True,
        help="SWE-bench instance ID, for example sympy__sympy-20590.",
    )

    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help="Hugging Face SWE-bench dataset name.",
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("workspaces"),
        help="Directory where instance information will be saved.",
    )

    return parser.parse_args()


def parse_possible_json(value: Any) -> Any:
    """
    Convert JSON strings into Python objects.

    Some SWE-bench fields, such as FAIL_TO_PASS, may be stored as JSON text.
    """

    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def find_instance(
    dataset: Any,
    instance_id: str,
) -> dict[str, Any]:
    """Find one instance by its instance ID."""

    for record in dataset:
        if record["instance_id"] == instance_id:
            return dict(record)

    raise ValueError(f"Instance was not found in the dataset: {instance_id}")


def write_text_file(
    path: Path,
    content: Any,
) -> None:
    """Write content to a UTF-8 text file."""

    if content is None:
        content = ""

    path.write_text(str(content), encoding="utf-8")


def main() -> int:
    """Prepare one SWE-bench instance."""

    args = parse_arguments()

    print(f"Loading dataset: {args.dataset}")

    dataset = load_dataset(
        args.dataset,
        split="test",
    )

    print(f"Searching for instance: {args.instance_id}")

    instance = find_instance(
        dataset=dataset,
        instance_id=args.instance_id,
    )

    instance_directory = args.output_directory.expanduser().resolve() / args.instance_id

    instance_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    normalized_instance = {
        key: parse_possible_json(value) for key, value in instance.items()
    }

    metadata_path = instance_directory / "metadata.json"
    problem_path = instance_directory / "problem_statement.md"
    patch_path = instance_directory / "gold_patch.diff"
    test_patch_path = instance_directory / "test_patch.diff"
    fail_to_pass_path = instance_directory / "fail_to_pass.json"
    pass_to_pass_path = instance_directory / "pass_to_pass.json"

    metadata_path.write_text(
        json.dumps(
            normalized_instance,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    write_text_file(
        problem_path,
        normalized_instance.get("problem_statement", ""),
    )

    write_text_file(
        patch_path,
        normalized_instance.get("patch", ""),
    )

    write_text_file(
        test_patch_path,
        normalized_instance.get("test_patch", ""),
    )

    fail_to_pass_path.write_text(
        json.dumps(
            normalized_instance.get("FAIL_TO_PASS", []),
            indent=2,
        ),
        encoding="utf-8",
    )

    pass_to_pass_path.write_text(
        json.dumps(
            normalized_instance.get("PASS_TO_PASS", []),
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nInstance prepared successfully")
    print("=" * 60)
    print(f"Instance ID:   {normalized_instance['instance_id']}")
    print(f"Repository:    {normalized_instance['repo']}")
    print(f"Base commit:   {normalized_instance['base_commit']}")
    print(f"Output folder: {instance_directory}")
    print("=" * 60)

    print("\nFAIL_TO_PASS tests:")

    fail_to_pass = normalized_instance.get("FAIL_TO_PASS", [])

    if fail_to_pass:
        for test_name in fail_to_pass:
            print(f"  - {test_name}")
    else:
        print("  No FAIL_TO_PASS tests were listed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
