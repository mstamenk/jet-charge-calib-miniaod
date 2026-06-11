#!/usr/bin/env python3
"""Data/MC stacked plots for dilepton ttbar reco directly from split production files."""

import argparse
import glob
import os
import multiprocessing
import time
from typing import Optional

import ROOT

from top_reco_utils import define_top_reco_columns, enable_mt, declare_cpp_helpers


PROCESS_ORDER = ["qcd", "vjets", "ttbar_semileptonic", "ttbar_dileptonic"]
PROCESS_COLORS = {
    "qcd": ROOT.kYellow + 1,
    "vjets": ROOT.kRed + 1,
    "ttbar_semileptonic": ROOT.kAzure + 1,
    "ttbar_dileptonic": ROOT.kBlue + 2,
}
PROCESS_LABELS = {
    "qcd": "QCD",
    "vjets": "V+jets",
    "ttbar_semileptonic": "ttbar semileptonic",
    "ttbar_dileptonic": "ttbar dileptonic",
}


def classify_sample(sample_dir_name: str, data_stream: str) -> Optional[str]:
    parts = sample_dir_name.split("__")
    if len(parts) < 3:
        return None
    sample_type = parts[0]
    process = parts[2]
    if sample_type == "data":
        if data_stream == "muon" and process != "Muon":
            return None
        if data_stream == "egamma" and process != "EGamma":
            return None
        return "data"
    if sample_type == "mc" and process in PROCESS_ORDER:
        return process
    return None


def build_files_by_process(prod_dir: str, ttbar_dileptonic_fraction: float, data_stream: str) -> dict[str, list[str]]:
    files = {"data": []}
    for p in PROCESS_ORDER:
        files[p] = []

    for entry in sorted(os.listdir(prod_dir)):
        sample_dir = os.path.join(prod_dir, entry)
        if not os.path.isdir(sample_dir):
            continue
        category = classify_sample(entry, data_stream)
        if category is None:
            continue
        root_files = sorted(glob.glob(os.path.join(sample_dir, "*.root")))
        if not root_files:
            continue
        if category == "ttbar_dileptonic" and 0.0 < ttbar_dileptonic_fraction < 1.0:
            n_before = len(root_files)
            n_keep = max(1, int(len(root_files) * ttbar_dileptonic_fraction))
            root_files = root_files[:n_keep]
            print(
                f"[plot_data_mc] sample={entry} ttbar_dileptonic subsample: keep {n_keep}/{n_before} files",
                flush=True,
            )
        files[category].extend(root_files)
    return files


def add_common_columns(df, process_name: str, norm_mode: str):
    cols = {str(c) for c in df.GetColumnNames()}
    is_mc_process = process_name in PROCESS_ORDER
    has_weight_branches = (
        "genWeight" in cols
        and "puWeight" in cols
        and "prefireWeight" in cols
        and "sampleXsecPb" in cols
        and "targetLumiPb" in cols
    )
    has_sumw = "sampleSumWeights" in cols
    if is_mc_process and has_weight_branches:
        if norm_mode == "manifest_sumw":
            if not has_sumw:
                raise RuntimeError("norm-mode manifest_sumw requires sampleSumWeights branch.")
            df = df.Define(
                "analysis_weight",
                "compute_analysis_weight(genWeight, puWeight, prefireWeight, sampleXsecPb, sampleSumWeights, targetLumiPb)",
            )
        elif norm_mode == "processed_events":
            n_processed = int(df.Count().GetValue())
            if n_processed <= 0:
                n_processed = 1
            print(f"[plot_data_mc] {process_name}: processed-events norm with n_processed={n_processed}", flush=True)
            df = df.Define(
                "analysis_weight",
                f"genWeight * puWeight * prefireWeight * ((sampleXsecPb * targetLumiPb) / {float(n_processed)})",
            )
        elif norm_mode == "processed_genweight":
            sumw_processed = float(df.Sum("genWeight").GetValue())
            if sumw_processed == 0.0:
                sumw_processed = 1.0
            print(
                f"[plot_data_mc] {process_name}: processed-genweight norm with sumw_processed={sumw_processed:.6g}",
                flush=True,
            )
            df = df.Define(
                "analysis_weight",
                f"genWeight * puWeight * prefireWeight * ((sampleXsecPb * targetLumiPb) / {sumw_processed})",
            )
        else:
            raise RuntimeError(f"Unsupported norm mode: {norm_mode}")
    else:
        df = df.Define("analysis_weight", "1.0f")

    df = (
        df.Define("mu0_pt", "safe_first_f(muon_pt, -1.f)")
        .Define("mu0_eta", "safe_first_f(muon_eta, -9.f)")
        .Define("mu0_phi", "safe_first_f(muon_phi, -9.f)")
        .Define("mu0_mass", "safe_first_f(muon_mass, 0.10566f)")
        .Define("mu0_isLoose", "safe_first_i(muon_isLoose, -1)")
        .Define("mu0_isMedium", "safe_first_i(muon_isMedium, -1)")
        .Define("mu0_isTight", "safe_first_i(muon_isTight, -1)")
        .Define("mu0_charge", "safe_first_i(muon_charge, 0)")
        .Define("el0_pt", "safe_first_f(electron_pt, -1.f)")
        .Define("el0_eta", "safe_first_f(electron_eta, -9.f)")
        .Define("el0_phi", "safe_first_f(electron_phi, -9.f)")
        .Define("el0_mass", "safe_first_f(electron_mass, 0.000511f)")
        .Define("el0_cutBased", "safe_first_i(electron_cutBased, -1)")
        .Define("el0_charge", "safe_first_i(electron_charge, 0)")
        .Define("mu0_idbin", "(mu0_isTight>0)?2:((mu0_isMedium>0)?1:((mu0_isLoose>0)?0:-1))")
        .Filter("mu0_pt > 0 && el0_pt > 0", "muon+electron present")
    )
    return df


def add_bcand_columns(df):
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
        .Define(
            "topreco_bmu_pt",
            "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_pt.size()) ? jet_pt[topreco_bmu_index] : -1.f",
        )
        .Define(
            "topreco_be_pt",
            "(topreco_be_index>=0 && topreco_be_index<(int)jet_pt.size()) ? jet_pt[topreco_be_index] : -1.f",
        )
    )


def make_hist_map(df):
    df_fit = add_bcand_columns(df)
    return {
        "topmu_mass": df_fit.Histo1D(("h_topmu_mass", ";m_{top,#mu} [GeV];Events", 60, 100, 320), "topreco_t1_mass", "analysis_weight"),
        "tope_mass": df_fit.Histo1D(("h_tope_mass", ";m_{top,e} [GeV];Events", 60, 100, 320), "topreco_t2_mass", "analysis_weight"),
        "wmu_mass": df_fit.Histo1D(("h_wmu_mass", ";m_{W,#mu} [GeV];Events", 50, 0, 180), "topreco_w1_mass", "analysis_weight"),
        "we_mass": df_fit.Histo1D(("h_we_mass", ";m_{W,e} [GeV];Events", 50, 0, 180), "topreco_w2_mass", "analysis_weight"),
        "topfit_chi2": df_fit.Histo1D(("h_topfit_chi2", ";#chi^{2};Events", 60, 0, 120), "topreco_chi2", "analysis_weight"),
        "topfit_met_residual": df_fit.Histo1D(("h_topfit_met_residual", ";|#Delta MET| [GeV];Events", 60, 0, 120), "topreco_met_residual", "analysis_weight"),
        "mu_pt": df.Histo1D(("h_mu_pt", ";p_{T}^{#mu} [GeV];Events", 50, 0, 250), "mu0_pt", "analysis_weight"),
        "mu_eta": df.Histo1D(("h_mu_eta", ";#eta^{#mu};Events", 48, -2.4, 2.4), "mu0_eta", "analysis_weight"),
        "mu_phi": df.Histo1D(("h_mu_phi", ";#phi^{#mu};Events", 64, -3.2, 3.2), "mu0_phi", "analysis_weight"),
        "el_pt": df.Histo1D(("h_el_pt", ";p_{T}^{e} [GeV];Events", 50, 0, 250), "el0_pt", "analysis_weight"),
        "el_eta": df.Histo1D(("h_el_eta", ";#eta^{e};Events", 50, -2.5, 2.5), "el0_eta", "analysis_weight"),
        "el_phi": df.Histo1D(("h_el_phi", ";#phi^{e};Events", 64, -3.2, 3.2), "el0_phi", "analysis_weight"),
        "jet_pt": df.Histo1D(("h_jet_pt", ";p_{T}^{jet} [GeV];Jets", 60, 0, 300), "jet_pt", "analysis_weight"),
        "jet_eta": df.Histo1D(("h_jet_eta", ";#eta^{jet};Jets", 60, -3.0, 3.0), "jet_eta", "analysis_weight"),
        "njet": df.Histo1D(("h_njet", ";N_{jets};Events", 8, -0.5, 7.5), "nJetSel", "analysis_weight"),
        "bmu_btagDeepB": df_fit.Histo1D(("h_bmu_btagDeepB", ";DeepB(b_{#mu});Events", 40, 0, 1), "topreco_bmu_btagDeepB", "analysis_weight"),
        "be_btagDeepB": df_fit.Histo1D(("h_be_btagDeepB", ";DeepB(b_{e});Events", 40, 0, 1), "topreco_be_btagDeepB", "analysis_weight"),
        "bmu_charge_score": df_fit.Histo1D(("h_bmu_charge_score", ";charge score(b_{#mu});Events", 20, 0, 1), "topreco_bmu_charge_score", "analysis_weight"),
        "be_charge_score": df_fit.Histo1D(("h_be_charge_score", ";charge score(b_{e});Events", 20, 0, 1), "topreco_be_charge_score", "analysis_weight"),
        "bmu_pt": df_fit.Histo1D(("h_bmu_pt", ";p_{T}^{b_{#mu}} [GeV];Events", 50, 0, 300), "topreco_bmu_pt", "analysis_weight"),
        "be_pt": df_fit.Histo1D(("h_be_pt", ";p_{T}^{b_{e}} [GeV];Events", 50, 0, 300), "topreco_be_pt", "analysis_weight"),
    }


def draw_stack_with_data(name, data_hist, mc_hists_by_process, outdir, title):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 900, 760)
    stack = ROOT.THStack(f"hs_{name}", title)
    leg = ROOT.TLegend(0.60, 0.60, 0.88, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)

    mc_sum = None
    for proc in PROCESS_ORDER:
        h = mc_hists_by_process.get(proc)
        if h is None:
            continue
        h.SetFillColor(PROCESS_COLORS[proc])
        h.SetLineColor(PROCESS_COLORS[proc])
        h.SetLineWidth(1)
        stack.Add(h)
        leg.AddEntry(h, PROCESS_LABELS[proc], "f")
        if mc_sum is None:
            mc_sum = h.Clone(f"{name}_mc_sum")
        else:
            mc_sum.Add(h)

    stack.Draw("HIST")
    stack.GetYaxis().SetTitle("Events")
    ymax = stack.GetMaximum()

    if data_hist is not None:
        data_hist.SetMarkerStyle(20)
        data_hist.SetMarkerSize(0.9)
        data_hist.SetLineColor(ROOT.kBlack)
        data_hist.SetMarkerColor(ROOT.kBlack)
        data_hist.Draw("E1 SAME")
        leg.AddEntry(data_hist, "Data", "pe")
        ymax = max(ymax, data_hist.GetMaximum())

    if mc_sum is not None:
        mc_band = mc_sum.Clone(f"{name}_mc_unc")
        mc_band.SetFillColorAlpha(ROOT.kGray + 2, 0.35)
        mc_band.SetLineColor(0)
        mc_band.SetMarkerSize(0)
        mc_band.Draw("E2 SAME")
        leg.AddEntry(mc_band, "MC stat. unc.", "f")

    stack.SetMaximum(1.35 * ymax if ymax > 0 else 1.0)
    leg.Draw()
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def main():
    parser = argparse.ArgumentParser(description="Plot data/MC ttbar-reco observables from split production samples.")
    parser.add_argument("--prod-dir", required=True, help="Production directory containing sample subdirs with ntuple_job_*.root.")
    parser.add_argument("--tree", default="Events", help="Input tree name")
    parser.add_argument("--outdir", default="analysis/plots_data_mc_ttbar_reco", help="Output plot directory")
    parser.add_argument("--threads", type=int, default=0, help="ROOT implicit MT threads (<=0: use all available cores)")
    parser.add_argument(
        "--data-stream",
        choices=["all", "muon", "egamma"],
        default="all",
        help="Which data stream to include (default: all). Use muon to avoid EGamma+Muon double counting.",
    )
    parser.add_argument(
        "--ttbar-dileptonic-fraction",
        type=float,
        default=1.0,
        help="Fraction of ttbar_dileptonic files to read (0<f<=1, default: 1.0).",
    )
    parser.add_argument(
        "--norm-mode",
        choices=["manifest_sumw", "processed_events", "processed_genweight"],
        default="manifest_sumw",
        help=(
            "MC normalization mode: manifest_sumw uses sampleSumWeights branch; "
            "processed_events uses number of processed events; "
            "processed_genweight uses sum(genWeight) over processed events."
        ),
    )
    args = parser.parse_args()
    if not (0.0 < args.ttbar_dileptonic_fraction <= 1.0):
        raise RuntimeError("--ttbar-dileptonic-fraction must be in (0, 1].")

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    nthreads = args.threads if args.threads and args.threads > 0 else (multiprocessing.cpu_count() or 1)
    print(f"[plot_data_mc] Using {nthreads} threads", flush=True)
    enable_mt(nthreads)
    declare_cpp_helpers()

    t0 = time.time()
    print("[plot_data_mc] Discovering input files...", flush=True)
    files_by_process = build_files_by_process(args.prod_dir, args.ttbar_dileptonic_fraction, args.data_stream)
    for proc, files in files_by_process.items():
        print(f"[plot_data_mc] {proc}: {len(files)} files")
    print(f"[plot_data_mc] File discovery done in {time.time() - t0:.1f} s", flush=True)

    hist_book = {}
    for proc, files in files_by_process.items():
        if not files:
            continue
        t_proc = time.time()
        print(f"[plot_data_mc] Building RDataFrame for {proc} ({len(files)} files)...", flush=True)
        df = ROOT.RDataFrame(args.tree, files)
        df = add_common_columns(df, proc, args.norm_mode)
        df = define_top_reco_columns(df)
        hist_book[proc] = make_hist_map(df)
        print(f"[plot_data_mc] Booked histograms for {proc} in {time.time() - t_proc:.1f} s", flush=True)

    var_titles = {
        "topmu_mass": "Top(#mu) mass",
        "tope_mass": "Top(e) mass",
        "wmu_mass": "W(#mu) mass",
        "we_mass": "W(e) mass",
        "topfit_chi2": "Kinematic fit #chi^{2}",
        "topfit_met_residual": "Kinematic fit MET residual",
        "mu_pt": "Muon p_{T}",
        "mu_eta": "Muon #eta",
        "mu_phi": "Muon #phi",
        "el_pt": "Electron p_{T}",
        "el_eta": "Electron #eta",
        "el_phi": "Electron #phi",
        "jet_pt": "Jet p_{T}",
        "jet_eta": "Jet #eta",
        "njet": "Jet multiplicity",
        "bmu_btagDeepB": "b_{#mu} tag score",
        "be_btagDeepB": "b_{e} tag score",
        "bmu_charge_score": "b_{#mu} charge score",
        "be_charge_score": "b_{e} charge score",
        "bmu_pt": "b_{#mu} p_{T}",
        "be_pt": "b_{e} p_{T}",
    }

    for var, title in var_titles.items():
        t_var = time.time()
        print(f"[plot_data_mc] Rendering {var}...", flush=True)
        data_hist = None
        if "data" in hist_book:
            print(f"[plot_data_mc]   materializing data:{var}", flush=True)
            data_hist = hist_book["data"][var].GetValue().Clone(f"{var}_data")
        mc_hists = {}
        for proc in PROCESS_ORDER:
            if proc in hist_book:
                print(f"[plot_data_mc]   materializing {proc}:{var}", flush=True)
                mc_hists[proc] = hist_book[proc][var].GetValue().Clone(f"{var}_{proc}")
        draw_stack_with_data(var, data_hist, mc_hists, args.outdir, title)
        print(f"[plot_data_mc] Done {var} in {time.time() - t_var:.1f} s", flush=True)

    print(f"[plot_data_mc] Wrote plots to: {args.outdir}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
