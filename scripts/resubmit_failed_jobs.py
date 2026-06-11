#!/usr/bin/env python3
"""Prepare and optionally resubmit failed Condor jobs from a CSV report."""

import argparse
import csv
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read failed jobs CSV (from scripts/count_condor_failures.py --dump-failed), "
            "write a unique JDL list, and optionally condor_submit each JDL."
        )
    )
    parser.add_argument(
        "--csv",
        default="run/local_dilep_emu_os/prod_v1_failed_jobs.csv",
        help="Input failed-jobs CSV path.",
    )
    parser.add_argument(
        "--out-jdls",
        default="run/local_dilep_emu_os/prod_v1_failed_jdls.txt",
        help="Output text file with one JDL path per line.",
    )
    parser.add_argument(
        "--category",
        choices=["all", "data", "mc"],
        default="all",
        help="Only include selected category from CSV.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of JDLs to include (0 = no limit).",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="If set, run condor_submit for each selected JDL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)
    out_path = Path(args.out_jdls)

    if not csv_path.is_file():
        raise SystemExit(f"Missing CSV file: {csv_path}")

    jdls = []
    missing = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required_cols = {"category", "job_log"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            raise SystemExit(f"CSV is missing required columns: {sorted(required_cols)}")
        for row in reader:
            row_cat = row.get("category", "").strip()
            if args.category != "all" and row_cat != args.category:
                continue
            job_log = row.get("job_log", "").strip()
            if not job_log:
                continue
            jdl_path = Path(job_log).with_suffix(".jdl")
            if jdl_path.is_file():
                jdls.append(str(jdl_path))
            else:
                missing.append(str(jdl_path))

    # de-duplicate while preserving order
    unique = []
    seen = set()
    for jdl in jdls:
        if jdl in seen:
            continue
        seen.add(jdl)
        unique.append(jdl)

    if args.limit > 0:
        unique = unique[: args.limit]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(unique) + ("\n" if unique else ""), encoding="utf-8")

    print(f"input_csv={csv_path}")
    print(f"category={args.category}")
    print(f"jdls_written={len(unique)}")
    print(f"out_jdls={out_path}")
    print(f"missing_jdls={len(missing)}")

    if missing:
        print("missing_examples:")
        for path in missing[:10]:
            print(path)

    if not args.submit:
        print("dry_run_only=1 (use --submit to actually resubmit)")
        return 0

    submitted = 0
    failed_submit = 0
    for jdl in unique:
        proc = subprocess.run(["condor_submit", jdl], check=False)
        if proc.returncode == 0:
            submitted += 1
        else:
            failed_submit += 1

    print(f"submitted_ok={submitted}")
    print(f"submit_failures={failed_submit}")
    return 0 if failed_submit == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
