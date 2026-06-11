#!/usr/bin/env python3
"""Find and optionally delete corrupted ROOT files in a production directory."""

import argparse
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional

BAD_PATTERNS = (
    "has no keys",
    "probably not closed",
    "trying to recover",
    "is a zombie",
    "readbuffer",
    "error in <tfile::",
)


def check_root_file(path: Path, rootls_bin: str) -> Optional[Dict]:
    if not path.exists():
        return {"file": str(path), "reason": "missing"}
    if path.stat().st_size == 0:
        return {"file": str(path), "reason": "empty_file"}
    proc = subprocess.run(
        [rootls_bin, "-1", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    combined = "\n".join(x for x in (stdout, stderr) if x).strip()
    combined_lower = combined.lower()
    if proc.returncode != 0:
        return {
            "file": str(path),
            "reason": "rootls_failed",
            "stdout": stdout[:500],
            "stderr": stderr[:500],
        }
    key_lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if len(key_lines) == 0:
        return {
            "file": str(path),
            "reason": "no_keys",
            "stdout": stdout[:500],
            "stderr": stderr[:500],
        }
    for pat in BAD_PATTERNS:
        if pat in combined_lower:
            return {
                "file": str(path),
                "reason": "root_warning",
                "pattern": pat,
                "stdout": stdout[:500],
                "stderr": stderr[:500],
            }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan production ROOT files, report corrupted ones, and optionally delete them."
    )
    parser.add_argument(
        "--prod-dir",
        required=True,
        help="Production directory containing sample subdirs with ntuple .root files.",
    )
    parser.add_argument(
        "--pattern",
        default="*.root",
        help="Glob pattern inside each sample dir (default: *.root).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Parallel file-check workers (default: 8).",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Print progress every N files (default: 50, set 0 to disable).",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Output JSON report path (default: <prod-dir>/corrupted_root_files.json).",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete corrupted files. Default is dry-run report only.",
    )
    args = parser.parse_args()

    rootls_bin = shutil.which("rootls")
    if not rootls_bin:
        raise RuntimeError("Could not find `rootls` in PATH. Run in a CMSSW/ROOT environment.")

    prod_dir = Path(args.prod_dir).resolve()
    if not prod_dir.is_dir():
        raise RuntimeError(f"Production directory not found: {prod_dir}")

    files: list[Path] = []
    for sample_dir in sorted(prod_dir.iterdir()):
        if not sample_dir.is_dir():
            continue
        files.extend(sorted(sample_dir.glob(args.pattern)))

    total = len(files)
    print(f"[cleanup] Scanning {total} files in {prod_dir}", flush=True)
    if total == 0:
        print("[cleanup] No files found.")
        return 0

    bad: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(check_root_file, f, rootls_bin): f for f in files}
        for fut in as_completed(futures):
            done += 1
            rec = fut.result()
            if rec is not None:
                bad.append(rec)
            if args.progress_every > 0 and (done % args.progress_every == 0 or done == total):
                print(f"[cleanup] Progress {done}/{total}, bad={len(bad)}", flush=True)

    report_path = Path(args.report) if args.report else (prod_dir / "corrupted_root_files.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(sorted(bad, key=lambda x: x["file"]), handle, indent=2, sort_keys=True)
    print(f"[cleanup] Wrote report: {report_path}", flush=True)

    if args.delete:
        deleted = 0
        for rec in bad:
            p = Path(rec["file"])
            if p.exists():
                p.unlink()
                deleted += 1
        print(f"[cleanup] Deleted {deleted} corrupted files.", flush=True)
    else:
        print("[cleanup] Dry run only. Re-run with --delete to remove corrupted files.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
