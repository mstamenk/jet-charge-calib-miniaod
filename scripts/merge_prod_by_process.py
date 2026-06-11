#!/usr/bin/env python3
"""Merge one production into one ROOT file per physics-process group."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


DEFAULT_GROUPS = ("Egamma", "Muon", "qcd", "ttbar_dileptonic", "ttbar_semileptonic", "vjets")


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and isinstance(payload.get("samples"), dict):
        return payload["samples"]
    if isinstance(payload, dict):
        return payload
    return {}


def sample_to_group(sample_name: str) -> Optional[str]:
    parts = sample_name.split("__")
    if len(parts) < 3:
        return None
    sample_type = parts[0]
    process = parts[2]

    if sample_type == "data":
        if process == "EGamma":
            return "Egamma"
        if process == "Muon":
            return "Muon"
        return None
    if sample_type == "mc":
        if process in ("qcd", "ttbar_dileptonic", "ttbar_semileptonic", "vjets"):
            return process
        return None
    return None


def run_hadd(
    output_file: Path,
    input_files: list[Path],
    batch_size: int,
    jobs: int,
    force: bool,
    tmp_base_dir: Path,
) -> None:
    if not input_files:
        raise RuntimeError(f"No input files provided for output {output_file}")

    hadd_bin = shutil.which("hadd")
    if not hadd_bin:
        raise RuntimeError("Could not find `hadd` in PATH.")

    out_flag = "-f" if force else "-fk"

    def _call_hadd(target: Path, sources: list[Path]) -> None:
        cmd = [hadd_bin, out_flag, "-j", str(max(1, jobs)), str(target)] + [str(p) for p in sources]
        subprocess.run(cmd, check=True)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if len(input_files) <= batch_size:
        _call_hadd(output_file, input_files)
        return

    tmp_base_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="merge_prod_by_process_", dir=str(tmp_base_dir)) as tmpdir:
        tmpdir_path = Path(tmpdir)
        partials = []
        for i in range(0, len(input_files), batch_size):
            chunk = input_files[i : i + batch_size]
            partial = tmpdir_path / f"partial_{i // batch_size:04d}.root"
            _call_hadd(partial, chunk)
            partials.append(partial)
        _call_hadd(output_file, partials)


def validate_root_files(files: list[Path], group: str, progress_every: int) -> tuple[list[Path], list[dict]]:
    """Return (good_files, bad_file_records)."""
    rootls_bin = shutil.which("rootls")
    if not rootls_bin:
        raise RuntimeError("Could not find `rootls` in PATH. Please setup ROOT/CMSSW runtime first.")

    good: list[Path] = []
    bad: list[dict] = []
    total = len(files)
    for idx, f in enumerate(files, start=1):
        if not f.exists():
            bad.append({"file": str(f), "reason": "missing"})
            continue
        if f.stat().st_size == 0:
            bad.append({"file": str(f), "reason": "empty_file"})
            continue
        # rootls fails fast on unreadable/corrupted ROOT files.
        proc = subprocess.run(
            [rootls_bin, "-t", str(f)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            bad.append(
                {
                    "file": str(f),
                    "reason": "rootls_failed",
                    "stderr": (proc.stderr or "").strip()[:400],
                }
            )
            continue
        good.append(f)
        if progress_every > 0 and (idx % progress_every == 0 or idx == total):
            print(f"[merge] {group}: validate progress {idx}/{total} (good={len(good)} bad={len(bad)})", flush=True)
    return good, bad


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge a production into one ROOT file per process group "
            "(Egamma, Muon, qcd, ttbar_dileptonic, ttbar_semileptonic, vjets)."
        )
    )
    parser.add_argument("--output-base", required=True, help="Base output directory used in production.")
    parser.add_argument("--era", required=True, help="Era key, e.g. Run3_24.")
    parser.add_argument("--version", required=True, help="Production version, e.g. prod_v1.")
    parser.add_argument("--tag", required=True, help="Production tag, e.g. run3_24_dilep_emu_os_v1.")
    parser.add_argument("--outdir", required=True, help="Directory where merged files will be written.")
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional manifest JSON path. Default: filelists/<tag>/manifest.json if it exists.",
    )
    parser.add_argument(
        "--groups",
        default=",".join(DEFAULT_GROUPS),
        help=f"Comma-separated groups to merge. Default: {','.join(DEFAULT_GROUPS)}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=400,
        help="Max number of files per hadd call before two-step batching (default: 400).",
    )
    parser.add_argument("--jobs", type=int, default=4, help="hadd -j value (default: 4).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing merged outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned merges only.")
    parser.add_argument(
        "--validate-files",
        action="store_true",
        help="Check ROOT readability with rootls before merging and skip bad files.",
    )
    parser.add_argument(
        "--bad-files-report",
        default="",
        help="Optional JSON report path for skipped/corrupted files.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print validation progress every N files (default: 25, set 0 to disable).",
    )
    parser.add_argument(
        "--tmpdir",
        default="",
        help=(
            "Base directory for temporary partial hadd files. "
            "Default: <repo>/run/local_dilep_emu_os/tmp_hadd_merge"
        ),
    )
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parents[1]
    prod_dir = Path(args.output_base) / args.era / args.version / args.tag
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tmp_base_dir = Path(args.tmpdir) if args.tmpdir else (repo_dir / "run" / "local_dilep_emu_os" / "tmp_hadd_merge")

    if not prod_dir.is_dir():
        raise RuntimeError(f"Production directory not found: {prod_dir}")

    manifest_path = Path(args.manifest) if args.manifest else (repo_dir / "filelists" / args.tag / "manifest.json")
    manifest = load_manifest(manifest_path)
    if manifest:
        print(f"[merge] Loaded manifest: {manifest_path}")
    else:
        print(f"[merge] Manifest not found/empty: {manifest_path} (continuing without metadata summary)")

    selected_groups = {x.strip() for x in args.groups.split(",") if x.strip()}
    grouped_files: dict[str, list[Path]] = {g: [] for g in selected_groups}
    grouped_samples: dict[str, list[str]] = {g: [] for g in selected_groups}

    for sample_dir in sorted(prod_dir.iterdir()):
        if not sample_dir.is_dir():
            continue
        sample = sample_dir.name
        group = sample_to_group(sample)
        if not group or group not in selected_groups:
            continue
        files = sorted(sample_dir.glob("*.root"))
        if not files:
            continue
        grouped_files[group].extend(files)
        grouped_samples[group].append(sample)

    summary = {
        "production": {
            "output_base": str(args.output_base),
            "era": args.era,
            "version": args.version,
            "tag": args.tag,
            "prod_dir": str(prod_dir),
        },
        "groups": {},
    }
    bad_files_all: list[dict] = []

    for group in sorted(selected_groups):
        files = grouped_files.get(group, [])
        samples = grouped_samples.get(group, [])
        if not files:
            print(f"[merge] {group}: no files found, skipping.")
            continue

        if args.validate_files:
            good_files, bad_files = validate_root_files(
                files=files, group=group, progress_every=max(0, args.progress_every)
            )
            for rec in bad_files:
                rec["group"] = group
            bad_files_all.extend(bad_files)
            print(
                f"[merge] {group}: validated {len(files)} files -> good={len(good_files)} bad={len(bad_files)}"
            )
            files = good_files
            if not files:
                print(f"[merge] {group}: no valid files left after validation, skipping.")
                continue

        target = outdir / f"{group}.root"
        if target.exists() and not args.force:
            raise RuntimeError(f"Output exists and --force not set: {target}")

        print(f"[merge] {group}: {len(files)} files from {len(samples)} samples -> {target}")

        group_info = {
            "n_samples": len(samples),
            "n_input_files": len(files),
            "samples": samples,
            "output_file": str(target),
        }

        # MC normalization audit from manifest metadata.
        if group in ("qcd", "ttbar_dileptonic", "ttbar_semileptonic", "vjets") and manifest:
            total_xsec = 0.0
            total_sumw = 0.0
            lumi_values = set()
            missing = []
            for sample in samples:
                meta = manifest.get(sample, {})
                xsec = float(meta.get("xsec_pb", -1.0) or -1.0)
                sumw = float(meta.get("sum_weights", 0.0) or 0.0)
                lumi = float(meta.get("target_lumi_pb", 0.0) or 0.0)
                if xsec > 0:
                    total_xsec += xsec
                else:
                    missing.append(f"{sample}:xsec_pb")
                if sumw > 0:
                    total_sumw += sumw
                else:
                    missing.append(f"{sample}:sum_weights")
                if lumi > 0:
                    lumi_values.add(lumi)
                else:
                    missing.append(f"{sample}:target_lumi_pb")

            group_info["mc_norm"] = {
                "total_xsec_pb": total_xsec,
                "total_sum_weights": total_sumw,
                "target_lumi_pb_values": sorted(lumi_values),
                "missing_metadata": missing,
            }
            if total_sumw > 0 and total_xsec > 0 and len(lumi_values) == 1:
                lumi = next(iter(lumi_values))
                group_info["mc_norm"]["effective_norm_factor"] = (total_xsec * lumi) / total_sumw

        summary["groups"][group] = group_info

        if not args.dry_run:
            run_hadd(
                output_file=target,
                input_files=files,
                batch_size=max(1, args.batch_size),
                jobs=max(1, args.jobs),
                force=args.force,
                tmp_base_dir=tmp_base_dir,
            )

    summary_path = outdir / f"{args.tag}_merge_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
    print(f"[merge] Wrote summary: {summary_path}")

    if bad_files_all:
        report_path = Path(args.bad_files_report) if args.bad_files_report else (
            outdir / f"{args.tag}_bad_files.json"
        )
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(bad_files_all, handle, indent=2, sort_keys=True)
        print(f"[merge] Wrote bad-file report: {report_path} ({len(bad_files_all)} files)")

    if args.dry_run:
        print("[merge] Dry-run only. No files were merged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
