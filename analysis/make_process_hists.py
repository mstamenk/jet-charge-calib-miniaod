#!/usr/bin/env python3
"""Build and store histograms per process from split production files."""

import argparse
import glob
import os
import multiprocessing
from typing import Dict, List, Optional

import ROOT

from top_reco_utils import declare_cpp_helpers, define_top_reco_columns, enable_mt


PROCESSES = ["data", "qcd", "vjets", "ttbar_semileptonic", "ttbar_dileptonic"]


def classify_sample(sample_dir_name: str, data_stream: str) -> Optional[str]:
    parts = sample_dir_name.split("__")
    if len(parts) < 3:
        return None
    stype = parts[0]
    proc = parts[2]
    if stype == "data":
        if data_stream == "muon" and proc != "Muon":
            return None
        if data_stream == "egamma" and proc != "EGamma":
            return None
        return "data"
    if stype == "mc" and proc in ("qcd", "vjets", "ttbar_semileptonic", "ttbar_dileptonic"):
        return proc
    return None


def collect_files(prod_dir: str, data_stream: str, ttbar_dileptonic_fraction: float) -> Dict[str, List[str]]:
    out = {k: [] for k in PROCESSES}
    for entry in sorted(os.listdir(prod_dir)):
        sample_dir = os.path.join(prod_dir, entry)
        if not os.path.isdir(sample_dir):
            continue
        proc = classify_sample(entry, data_stream)
        if proc is None:
            continue
        files = sorted(glob.glob(os.path.join(sample_dir, "*.root")))
        if not files:
            continue
        if proc == "ttbar_dileptonic" and ttbar_dileptonic_fraction < 1.0:
            n_keep = max(1, int(len(files) * ttbar_dileptonic_fraction))
            print(f"[make_process_hists] {entry}: keep {n_keep}/{len(files)} ttbar_dileptonic files", flush=True)
            files = files[:n_keep]
        out[proc].extend(files)
    return out


def validate_files(files: List[str], process_name: str) -> List[str]:
    good = []
    bad = 0
    for fpath in files:
        tf = ROOT.TFile.Open(fpath, "READ")
        if not tf:
            bad += 1
            continue
        is_bad = bool(tf.IsZombie()) or bool(tf.TestBit(ROOT.TFile.kRecovered)) or tf.GetNkeys() <= 0
        tf.Close()
        if is_bad:
            bad += 1
            continue
        good.append(fpath)
    if bad > 0:
        print(f"[make_process_hists] {process_name}: skipped {bad} recovered/corrupt files", flush=True)
    return good


def add_common_columns(df, proc: str, norm_mode: str):
    cols = {str(c) for c in df.GetColumnNames()}
    is_mc = proc != "data"

    if is_mc and all(
        c in cols
        for c in ("genWeight", "puWeight", "prefireWeight", "sampleXsecPb", "targetLumiPb")
    ):
        if norm_mode == "manifest_sumw":
            if "sampleSumWeights" not in cols:
                raise RuntimeError("sampleSumWeights missing for manifest_sumw")
            df = df.Define(
                "analysis_weight",
                "compute_analysis_weight(genWeight, puWeight, prefireWeight, sampleXsecPb, sampleSumWeights, targetLumiPb)",
            )
        elif norm_mode == "processed_events":
            n_processed = int(df.Count().GetValue())
            if n_processed <= 0:
                n_processed = 1
            print(f"[make_process_hists] {proc}: processed_events norm, n={n_processed}", flush=True)
            df = df.Define(
                "analysis_weight",
                f"genWeight * puWeight * prefireWeight * ((sampleXsecPb * targetLumiPb) / {float(n_processed)})",
            )
        elif norm_mode == "processed_genweight":
            sumw = float(df.Sum("genWeight").GetValue())
            if sumw == 0.0:
                sumw = 1.0
            print(f"[make_process_hists] {proc}: processed_genweight norm, sumw={sumw:.6g}", flush=True)
            df = df.Define(
                "analysis_weight",
                f"genWeight * puWeight * prefireWeight * ((sampleXsecPb * targetLumiPb) / {sumw})",
            )
        else:
            raise RuntimeError(f"Unsupported norm mode: {norm_mode}")
    else:
        df = df.Define("analysis_weight", "1.0f")

    return (
        df.Define("mu0_pt", "safe_first_f(muon_pt, -1.f)")
        .Define("mu0_eta", "safe_first_f(muon_eta, -9.f)")
        .Define("mu0_phi", "safe_first_f(muon_phi, -9.f)")
        .Define("mu0_mass", "safe_first_f(muon_mass, 0.10566f)")
        .Define("mu0_charge", "safe_first_i(muon_charge, 0)")
        .Define("el0_pt", "safe_first_f(electron_pt, -1.f)")
        .Define("el0_eta", "safe_first_f(electron_eta, -9.f)")
        .Define("el0_phi", "safe_first_f(electron_phi, -9.f)")
        .Define("el0_mass", "safe_first_f(electron_mass, 0.000511f)")
        .Define("el0_charge", "safe_first_i(electron_charge, 0)")
        .Filter("mu0_pt > 0 && el0_pt > 0", "muon+electron present")
    )


def add_bjet_columns(df):
    return (
        df.Filter("topreco_converged", "top reco converged")
        .Define("topreco_bmu_index", "topreco_b1_index")
        .Define("topreco_be_index", "topreco_b2_index")
        .Define(
            "topreco_bmu_btagDeepB",
            "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_btagDeepB.size()) ? jet_btagDeepB[topreco_bmu_index] : -1.f",
        )
        .Define(
            "topreco_be_btagDeepB",
            "(topreco_be_index>=0 && topreco_be_index<(int)jet_btagDeepB.size()) ? jet_btagDeepB[topreco_be_index] : -1.f",
        )
        .Define(
            "topreco_bmu_charge_score",
            "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_charge_score.size()) ? jet_charge_score[topreco_bmu_index] : -1.f",
        )
        .Define(
            "topreco_be_charge_score",
            "(topreco_be_index>=0 && topreco_be_index<(int)jet_charge_score.size()) ? jet_charge_score[topreco_be_index] : -1.f",
        )
    )


def build_selected_df(df, be_btag_cut: float, met_min: float):
    df = add_bjet_columns(df)
    sel = f"topreco_be_btagDeepB > {be_btag_cut}"
    if met_min > 0:
        sel += f" && met_pt >= {met_min}"
    return df.Filter(sel, "post-fit selection")


def book_hists(df_sel) -> Dict[str, ROOT.RDF.RResultPtr]:
    hmap = {
        "mu_pt": df_sel.Histo1D(("h_mu_pt", ";p_{T}^{#mu} [GeV];Events", 50, 0, 250), "mu0_pt", "analysis_weight"),
        "mu_eta": df_sel.Histo1D(("h_mu_eta", ";#eta^{#mu};Events", 48, -2.4, 2.4), "mu0_eta", "analysis_weight"),
        "mu_phi": df_sel.Histo1D(("h_mu_phi", ";#phi^{#mu};Events", 64, -3.2, 3.2), "mu0_phi", "analysis_weight"),
        "el_pt": df_sel.Histo1D(("h_el_pt", ";p_{T}^{e} [GeV];Events", 50, 0, 250), "el0_pt", "analysis_weight"),
        "el_eta": df_sel.Histo1D(("h_el_eta", ";#eta^{e};Events", 50, -2.5, 2.5), "el0_eta", "analysis_weight"),
        "el_phi": df_sel.Histo1D(("h_el_phi", ";#phi^{e};Events", 64, -3.2, 3.2), "el0_phi", "analysis_weight"),
        "jet_pt": df_sel.Histo1D(("h_jet_pt", ";p_{T}^{jet} [GeV];Jets", 60, 0, 300), "jet_pt", "analysis_weight"),
        "jet_eta": df_sel.Histo1D(("h_jet_eta", ";#eta^{jet};Jets", 60, -3.0, 3.0), "jet_eta", "analysis_weight"),
        "njet": df_sel.Histo1D(("h_njet", ";N_{jets};Events", 8, -0.5, 7.5), "nJetSel", "analysis_weight"),
        "met_pt": df_sel.Histo1D(("h_met_pt", ";MET [GeV];Events", 60, 0, 300), "met_pt", "analysis_weight"),
        "topmu_mass": df_sel.Histo1D(("h_topmu_mass", ";m_{top,#mu} [GeV];Events", 60, 100, 320), "topreco_t1_mass", "analysis_weight"),
        "tope_mass": df_sel.Histo1D(("h_tope_mass", ";m_{top,e} [GeV];Events", 60, 100, 320), "topreco_t2_mass", "analysis_weight"),
        "wmu_mass": df_sel.Histo1D(("h_wmu_mass", ";m_{W,#mu} [GeV];Events", 50, 0, 180), "topreco_w1_mass", "analysis_weight"),
        "we_mass": df_sel.Histo1D(("h_we_mass", ";m_{W,e} [GeV];Events", 50, 0, 180), "topreco_w2_mass", "analysis_weight"),
        "topfit_chi2": df_sel.Histo1D(("h_topfit_chi2", ";#chi^{2};Events", 60, 0, 120), "topreco_chi2", "analysis_weight"),
        "topfit_met_residual": df_sel.Histo1D(("h_topfit_met_residual", ";|#Delta MET| [GeV];Events", 60, 0, 120), "topreco_met_residual", "analysis_weight"),
        "bmu_btagDeepB": df_sel.Histo1D(("h_bmu_btagDeepB", ";DeepB(b_{#mu});Events", 40, 0, 1), "topreco_bmu_btagDeepB", "analysis_weight"),
        "be_btagDeepB": df_sel.Histo1D(("h_be_btagDeepB", ";DeepB(b_{e});Events", 40, 0, 1), "topreco_be_btagDeepB", "analysis_weight"),
        "bmu_charge_score": df_sel.Histo1D(("h_bmu_charge_score", ";charge score(b_{#mu});Events", 20, 0, 1), "topreco_bmu_charge_score", "analysis_weight"),
        "be_charge_score": df_sel.Histo1D(("h_be_charge_score", ";charge score(b_{e});Events", 20, 0, 1), "topreco_be_charge_score", "analysis_weight"),
    }

    cols = {str(c) for c in df_sel.GetColumnNames()}
    if "topreco_bmu_hflav" in cols and "topreco_be_hflav" in cols:
        df_cat = df_sel.Define(
            "bpair_hflav_cat",
            "((topreco_bmu_hflav==5 && topreco_be_hflav==5) ? 0 : "
            "(((topreco_bmu_hflav==5 && topreco_be_hflav==4) || (topreco_bmu_hflav==4 && topreco_be_hflav==5)) ? 1 : "
            "((topreco_bmu_hflav==4 && topreco_be_hflav==4) ? 2 : "
            "(((topreco_bmu_hflav==5 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==5)) ? 3 : "
            "(((topreco_bmu_hflav==4 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==4)) ? 4 : "
            "((topreco_bmu_hflav==0 && topreco_be_hflav==0) ? 5 : -1)))))",
        )
        hmap["bpair_hflavcat"] = df_cat.Histo1D(
            ("h_bpair_hflavcat", ";b-candidate flavour category;Events", 6, -0.5, 5.5),
            "bpair_hflav_cat",
            "analysis_weight",
        )
    else:
        print("[make_process_hists] top_reco hflav branches missing: skip bpair_hflavcat (expected for data).", flush=True)

    return hmap


def main():
    parser = argparse.ArgumentParser(description="Produce per-process ROOT histogram files.")
    parser.add_argument("--prod-dir", required=True)
    parser.add_argument("--outdir", default="analysis/hists_by_process")
    parser.add_argument("--tree", default="Events")
    parser.add_argument("--threads", type=int, default=0, help="ROOT threads (<=0: use all available cores)")
    parser.add_argument("--data-stream", choices=["all", "muon", "egamma"], default="muon")
    parser.add_argument("--ttbar-dileptonic-fraction", type=float, default=1.0)
    parser.add_argument(
        "--norm-mode",
        choices=["manifest_sumw", "processed_events", "processed_genweight"],
        default="manifest_sumw",
    )
    parser.add_argument("--muon-min-pt", type=float, default=30.0, help="Muon pT cut before top reco.")
    parser.add_argument("--min-njets", type=int, default=2, help="Min nJetSel before top reco.")
    parser.add_argument("--max-njets", type=int, default=4, help="Max nJetSel before top reco.")
    parser.add_argument("--be-btag-cut", type=float, default=0.3, help="Cut on topreco_be_btagDeepB after fit.")
    parser.add_argument("--met-min", type=float, default=0.0, help="Optional MET cut after fit.")
    parser.add_argument("--write-snapshot", action="store_true", help="Write selected event snapshot per process.")
    parser.add_argument(
        "--snapshot-mode",
        choices=["all", "minimal"],
        default="all",
        help="Snapshot content: all branches (default) or minimal analysis subset.",
    )
    args = parser.parse_args()

    if not (0.0 < args.ttbar_dileptonic_fraction <= 1.0):
        raise RuntimeError("--ttbar-dileptonic-fraction must be in (0,1].")

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    nthreads = args.threads if args.threads and args.threads > 0 else (multiprocessing.cpu_count() or 1)
    print(f"[make_process_hists] Using {nthreads} threads", flush=True)
    enable_mt(nthreads)
    declare_cpp_helpers()

    files_by_proc = collect_files(args.prod_dir, args.data_stream, args.ttbar_dileptonic_fraction)
    for proc in PROCESSES:
        files = files_by_proc.get(proc, [])
        if not files:
            continue
        files = validate_files(files, proc)
        if not files:
            print(f"[make_process_hists] {proc}: no valid files left after validation", flush=True)
            continue
        print(f"[make_process_hists] Processing {proc}: {len(files)} files", flush=True)
        df = ROOT.RDataFrame(args.tree, files)
        df = add_common_columns(df, proc, args.norm_mode)
        df = df.Filter(
            f"nJetSel >= {int(args.min_njets)} && nJetSel <= {int(args.max_njets)} && mu0_pt > {float(args.muon_min_pt)}",
            "prefit baseline",
        )
        df = define_top_reco_columns(df)
        df_sel = build_selected_df(df, float(args.be_btag_cut), float(args.met_min))
        if args.write_snapshot:
            snap_path = os.path.join(args.outdir, f"{proc}_snapshot.root")
            print(f"[make_process_hists] Writing snapshot: {snap_path}", flush=True)
            if args.snapshot_mode == "all":
                df_sel.Snapshot("Events", snap_path)
            else:
                snap_cols = [
                    "analysis_weight",
                    "mu0_pt", "mu0_eta", "mu0_phi", "mu0_charge",
                    "el0_pt", "el0_eta", "el0_phi", "el0_charge",
                    "met_pt", "met_phi", "nJetSel",
                    "topreco_chi2", "topreco_t1_mass", "topreco_t2_mass",
                    "topreco_w1_mass", "topreco_w2_mass", "topreco_ttbar_mass",
                    "topreco_met_residual", "topreco_bmu_btagDeepB", "topreco_be_btagDeepB",
                    "topreco_bmu_charge_score", "topreco_be_charge_score",
                ]
                df_sel.Snapshot("Events", snap_path, snap_cols)

        hmap = book_hists(df_sel)

        outpath = os.path.join(args.outdir, f"{proc}.root")
        fout = ROOT.TFile.Open(outpath, "RECREATE")
        for name, hptr in hmap.items():
            print(f"[make_process_hists]   materializing {proc}:{name}", flush=True)
            h = hptr.GetValue()
            h.SetName(name)
            h.Write()
        fout.Close()
        print(f"[make_process_hists] Wrote {outpath}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
