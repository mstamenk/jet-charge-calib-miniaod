#!/usr/bin/env python3
import argparse
import glob
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


def _chunk(items, n):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _stable_keep(item, fraction, seed):
    if fraction >= 1.0:
        return True
    key = f"{seed}:{item}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    u = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
    return u < fraction


def _split_filelist(filelist, out_base, files_per_job, fraction, fraction_seed, fraction_sample_pattern):
    sample = os.path.splitext(os.path.basename(filelist))[0]
    with open(filelist, "r", encoding="utf-8") as handle:
        files = [line.strip() for line in handle if line.strip()]
    n_before = len(files)

    apply_fraction = (
        fraction_sample_pattern
        and fraction > 0.0
        and fraction < 1.0
        and fraction_sample_pattern in sample
    )
    if apply_fraction:
        kept_files = [f for f in files if _stable_keep(f, fraction, fraction_seed)]
        if not kept_files and files:
            kept_files = [files[0]]
        files = kept_files

    sample_dir = os.path.join(out_base, sample)
    os.makedirs(sample_dir, exist_ok=True)
    for stale in glob.glob(os.path.join(sample_dir, "job_*.txt")):
        os.remove(stale)

    for idx, chunk in enumerate(_chunk(files, files_per_job), start=1):
        out_path = os.path.join(sample_dir, f"job_{idx:04d}.txt")
        with open(out_path, "w", encoding="utf-8") as out:
            out.write("\n".join(chunk) + "\n")
    return sample, n_before, len(files), sample_dir, apply_fraction


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="Input tag under filelists/")
    parser.add_argument("--files-per-job", type=int, default=100)
    parser.add_argument("--workers", type=int, default=16, help="Number of parallel split workers")
    parser.add_argument(
        "--fraction-sample-pattern",
        default="",
        help="Apply file-level downsampling only to sample names containing this substring.",
    )
    parser.add_argument(
        "--fraction",
        type=float,
        default=1.0,
        help="Keep fraction in [0,1] for matching samples (default: 1.0).",
    )
    parser.add_argument(
        "--fraction-seed",
        type=int,
        default=12345,
        help="Seed for deterministic file downsampling (default: 12345).",
    )
    args = parser.parse_args()
    if args.fraction <= 0.0 or args.fraction > 1.0:
        raise RuntimeError("--fraction must be in (0,1].")

    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "filelists", args.tag)
    out_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "filelists_split", args.tag)
    os.makedirs(out_base, exist_ok=True)

    filelists = sorted(glob.glob(os.path.join(base, "*.txt")))
    if not filelists:
        print(f"No filelists found under {base}")
        return

    workers = max(1, args.workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_filelist = {
            executor.submit(
                _split_filelist,
                filelist,
                out_base,
                args.files_per_job,
                args.fraction,
                args.fraction_seed,
                args.fraction_sample_pattern,
            ): filelist
            for filelist in filelists
        }
        for future in as_completed(future_to_filelist):
            filelist = future_to_filelist[future]
            try:
                sample, count_before, count_after, sample_dir, applied = future.result()
            except Exception as exc:
                print(f"Split failed for {filelist}: {exc}")
                continue
            msg = f"Split {sample}: {count_after} files -> {sample_dir}"
            if applied:
                msg += f" (downsampled from {count_before} with fraction={args.fraction})"
            print(msg)


if __name__ == "__main__":
    main()
