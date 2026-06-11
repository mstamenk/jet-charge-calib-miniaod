#!/usr/bin/env python3
"""Fast sanity-count report on split production samples (no top fit)."""

import argparse
import glob
import os
import multiprocessing
from typing import Optional, Tuple

import ROOT

ROOT.gInterpreter.Declare(
    r"""
#include <cmath>
float compute_analysis_weight(float genWeight,
                              float puWeight,
                              float prefireWeight,
                              float sampleXsecPb,
                              float sampleSumWeights,
                              float targetLumiPb) {
  float norm = 1.0f;
  if (std::abs(sampleSumWeights) > 0.f && sampleXsecPb > 0.f && targetLumiPb > 0.f) {
    norm = (sampleXsecPb * targetLumiPb) / sampleSumWeights;
  }
  return genWeight * puWeight * prefireWeight * norm;
}
"""
)


def classify(sample_dir_name: str) -> Optional[Tuple[str, str]]:
    parts = sample_dir_name.split("__")
    if len(parts) < 3:
        return None
    stype = parts[0]
    proc = parts[2]
    if stype == "data":
        return ("data", proc)
    if stype == "mc":
        return ("mc", proc)
    return None


def main():
    parser = argparse.ArgumentParser(description="Sanity-check event counts from split sample directories.")
    parser.add_argument("--prod-dir", required=True, help="Production directory with sample subdirs.")
    parser.add_argument("--tree", default="Events", help="Tree name (default: Events).")
    parser.add_argument("--threads", type=int, default=0, help="ROOT implicit MT threads (<=0: use all available cores).")
    parser.add_argument("--data-stream", choices=["all", "muon", "egamma"], default="all")
    parser.add_argument("--sample-limit", type=int, default=0, help="Optional max samples per process (0=all).")
    args = parser.parse_args()

    ROOT.gROOT.SetBatch(True)
    nthreads = args.threads if args.threads and args.threads > 0 else (multiprocessing.cpu_count() or 1)
    print(f"[count] Using {nthreads} threads", flush=True)
    ROOT.ROOT.EnableImplicitMT(nthreads)

    sample_rows = []
    proc_totals = {}

    sample_dirs = [d for d in sorted(os.listdir(args.prod_dir)) if os.path.isdir(os.path.join(args.prod_dir, d))]
    print(f"[count] Found {len(sample_dirs)} sample directories", flush=True)

    per_proc_seen = {}
    for sample in sample_dirs:
        cls = classify(sample)
        if cls is None:
            continue
        stype, proc = cls
        if stype == "data":
            if args.data_stream == "muon" and proc != "Muon":
                continue
            if args.data_stream == "egamma" and proc != "EGamma":
                continue
            pkey = "data"
        else:
            pkey = proc

        per_proc_seen.setdefault(pkey, 0)
        if args.sample_limit > 0 and per_proc_seen[pkey] >= args.sample_limit:
            continue
        per_proc_seen[pkey] += 1

        files = sorted(glob.glob(os.path.join(args.prod_dir, sample, "*.root")))
        if not files:
            continue

        print(f"[count] {sample}: {len(files)} files", flush=True)
        df = ROOT.RDataFrame(args.tree, files)
        n_all = int(df.Count().GetValue())
        w_all = -1.0

        cols = {str(c) for c in df.GetColumnNames()}
        is_mc = (stype == "mc")
        if is_mc and all(
            c in cols
            for c in ("genWeight", "puWeight", "prefireWeight", "sampleXsecPb", "sampleSumWeights", "targetLumiPb")
        ):
            dfw = df.Define(
                "analysis_weight",
                "compute_analysis_weight(genWeight, puWeight, prefireWeight, sampleXsecPb, sampleSumWeights, targetLumiPb)",
            )
            w_all = float(dfw.Sum("analysis_weight").GetValue())

        if "muon_pt" in cols and "electron_pt" in cols:
            df_sel = df.Filter("muon_pt.size()>0 && electron_pt.size()>0", ">=1 mu and >=1 e")
            n_emu = int(df_sel.Count().GetValue())
        else:
            n_emu = -1

        if "nJetSel" in cols:
            df_j2 = df.Filter("nJetSel>=2", "nJetSel>=2")
            n_j2 = int(df_j2.Count().GetValue())
            if n_emu >= 0:
                n_emu_j2 = int(df.Filter("muon_pt.size()>0 && electron_pt.size()>0 && nJetSel>=2").Count().GetValue())
            else:
                n_emu_j2 = -1
        else:
            n_j2 = -1
            n_emu_j2 = -1

        row = {
            "process": pkey,
            "sample": sample,
            "files": len(files),
            "n_all": n_all,
            "w_all": w_all,
            "n_emu": n_emu,
            "n_j2": n_j2,
            "n_emu_j2": n_emu_j2,
        }
        sample_rows.append(row)

        if pkey not in proc_totals:
            proc_totals[pkey] = {"files": 0, "n_all": 0, "w_all": 0.0, "n_emu": 0, "n_j2": 0, "n_emu_j2": 0}
        proc_totals[pkey]["files"] += len(files)
        proc_totals[pkey]["n_all"] += max(0, n_all)
        if w_all >= 0:
            proc_totals[pkey]["w_all"] += w_all
        proc_totals[pkey]["n_emu"] += max(0, n_emu)
        proc_totals[pkey]["n_j2"] += max(0, n_j2)
        proc_totals[pkey]["n_emu_j2"] += max(0, n_emu_j2)

    print("\n[count] Process totals")
    for pkey in sorted(proc_totals):
        t = proc_totals[pkey]
        print(
            f"  {pkey:20s} files={t['files']:6d}  n_all={t['n_all']:10d}  w_all={t['w_all']:14.6g}  n_emu={t['n_emu']:10d}  n_j2={t['n_j2']:10d}  n_emu_j2={t['n_emu_j2']:10d}"
        )

    print("\n[count] Sample rows")
    for r in sample_rows:
        print(
            f"  {r['process']:20s} {r['sample']} | files={r['files']} n_all={r['n_all']} w_all={r['w_all']:.6g} n_emu={r['n_emu']} n_j2={r['n_j2']} n_emu_j2={r['n_emu_j2']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
