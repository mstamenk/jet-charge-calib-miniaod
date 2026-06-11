#!/usr/bin/env python3
"""Count Condor job outcomes from .log files, split by data vs MC."""

import argparse
import re
from pathlib import Path
import csv
from typing import Optional


RETURN_VALUE_RE = re.compile(r"\(return value\s+(-?\d+)\)")


def classify_sample(sample_dir_name: str) -> str:
    if sample_dir_name.startswith("data__"):
        return "data"
    if sample_dir_name.startswith("mc__"):
        return "mc"
    return "unknown"


def empty_counts() -> dict:
    return {
        "total": 0,
        "ok": 0,
        "failed": 0,
        "running_or_unfinished": 0,
        "unknown_terminated_no_rv": 0,
        "held": 0,
        "aborted": 0,
    }


def update_counts(counts: dict, text: str) -> None:
    counts["total"] += 1

    terminated = "Job terminated." in text
    held = "Job was held." in text
    aborted = "Job was aborted by the user." in text
    if held:
        counts["held"] += 1
    if aborted:
        counts["aborted"] += 1

    matches = [int(m.group(1)) for m in RETURN_VALUE_RE.finditer(text)]
    return_value = matches[-1] if matches else None

    if terminated and return_value is not None:
        if return_value == 0:
            counts["ok"] += 1
        else:
            counts["failed"] += 1
        return

    if terminated and return_value is None:
        counts["unknown_terminated_no_rv"] += 1
        return

    if held or aborted:
        counts["failed"] += 1
        return

    counts["running_or_unfinished"] += 1


def classify_failure(text: str) -> Optional[dict]:
    terminated = "Job terminated." in text
    held = "Job was held." in text
    aborted = "Job was aborted by the user." in text
    matches = [int(m.group(1)) for m in RETURN_VALUE_RE.finditer(text)]
    return_value = matches[-1] if matches else None

    if terminated and return_value is not None and return_value != 0:
        return {"reason": "nonzero_exit", "return_value": return_value}
    if (not terminated) and held:
        return {"reason": "held", "return_value": ""}
    if (not terminated) and aborted:
        return {"reason": "aborted", "return_value": ""}
    return None


def print_counts(label: str, counts: dict) -> None:
    print(
        f"{label}: total={counts['total']} ok={counts['ok']} failed={counts['failed']} "
        f"running_or_unfinished={counts['running_or_unfinished']} "
        f"unknown_terminated_no_rv={counts['unknown_terminated_no_rv']} "
        f"held={counts['held']} aborted={counts['aborted']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Count condor job failures from .log files.")
    parser.add_argument("--log-dir", required=True, help="Top-level condor log directory (contains sample subdirs).")
    parser.add_argument(
        "--dump-failed",
        default="",
        help="Optional CSV output path with failed jobs (category,sample,job_log,reason,return_value).",
    )
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.is_dir():
        raise SystemExit(f"Missing log directory: {log_dir}")

    log_files = sorted(log_dir.rglob("*.log"))
    if not log_files:
        raise SystemExit(f"No .log files found under: {log_dir}")

    summary = {
        "all": empty_counts(),
        "data": empty_counts(),
        "mc": empty_counts(),
        "unknown": empty_counts(),
    }
    failed_rows = []

    for log_path in log_files:
        # The first path segment under log_dir is the sample directory.
        rel_parts = log_path.relative_to(log_dir).parts
        sample_dir = rel_parts[0] if rel_parts else ""
        category = classify_sample(sample_dir)

        text = log_path.read_text(encoding="utf-8", errors="ignore")
        update_counts(summary["all"], text)
        update_counts(summary[category], text)
        failure = classify_failure(text)
        if failure is not None:
            failed_rows.append(
                {
                    "category": category,
                    "sample": sample_dir,
                    "job_log": str(log_path),
                    "reason": failure["reason"],
                    "return_value": failure["return_value"],
                }
            )

    print_counts("all", summary["all"])
    print_counts("data", summary["data"])
    print_counts("mc", summary["mc"])
    if summary["unknown"]["total"] > 0:
        print_counts("unknown", summary["unknown"])

    if args.dump_failed:
        out_path = Path(args.dump_failed)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["category", "sample", "job_log", "reason", "return_value"]
            )
            writer.writeheader()
            writer.writerows(failed_rows)
        print(f"wrote_failed_csv={out_path} rows={len(failed_rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
