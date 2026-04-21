#!/usr/bin/env python3
import argparse
import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed


def _chunk(items, n):
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _split_filelist(filelist, out_base, files_per_job):
    sample = os.path.splitext(os.path.basename(filelist))[0]
    with open(filelist, "r", encoding="utf-8") as handle:
        files = [line.strip() for line in handle if line.strip()]
    sample_dir = os.path.join(out_base, sample)
    os.makedirs(sample_dir, exist_ok=True)

    for idx, chunk in enumerate(_chunk(files, files_per_job), start=1):
        out_path = os.path.join(sample_dir, f"job_{idx:04d}.txt")
        with open(out_path, "w", encoding="utf-8") as out:
            out.write("\n".join(chunk) + "\n")
    return sample, len(files), sample_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="Input tag under filelists/")
    parser.add_argument("--files-per-job", type=int, default=100)
    parser.add_argument("--workers", type=int, default=16, help="Number of parallel split workers")
    args = parser.parse_args()

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
            executor.submit(_split_filelist, filelist, out_base, args.files_per_job): filelist
            for filelist in filelists
        }
        for future in as_completed(future_to_filelist):
            filelist = future_to_filelist[future]
            try:
                sample, count, sample_dir = future.result()
            except Exception as exc:
                print(f"Split failed for {filelist}: {exc}")
                continue
            print(f"Split {sample}: {count} files -> {sample_dir}")


if __name__ == "__main__":
    main()
