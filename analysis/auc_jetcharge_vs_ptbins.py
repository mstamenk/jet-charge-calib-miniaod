#!/usr/bin/env python3
import argparse
import math
import os
from array import array

import ROOT


def ensure_col(df, cols, name, expr):
    if name in cols:
        return df, cols
    df = df.Define(name, expr)
    cols.add(name)
    return df, cols


def apply_common_selection(df, bmu_deepb_min, mu_id_cut):
    cols = {str(c) for c in df.GetColumnNames()}

    # baseline lepton presence
    if "mu0_pt" in cols and "el0_pt" in cols:
        df = df.Filter("mu0_pt > 0 && el0_pt > 0", "mu+e present")

    # optional mu ID
    if mu_id_cut != "none":
        req = {
            "loose": "mu0_isLoose",
            "medium": "mu0_isMedium",
            "tight": "mu0_isTight",
        }[mu_id_cut]
        if req in cols:
            df = df.Filter(f"{req} > 0", f"muon {mu_id_cut} ID")

    # derive bmu deepb if needed
    cols = {str(c) for c in df.GetColumnNames()}
    if "topreco_bmu_btagDeepB" not in cols and "topreco_b1_index" in cols and "jet_btagDeepB" in cols:
        df, cols = ensure_col(
            df,
            cols,
            "topreco_bmu_btagDeepB",
            "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_btagDeepB.size()) ? jet_btagDeepB[topreco_b1_index] : -1.f",
        )

    if "topreco_bmu_btagDeepB" in cols:
        df = df.Filter(f"topreco_bmu_btagDeepB > {float(bmu_deepb_min)}", f"bmu DeepB > {float(bmu_deepb_min)}")

    # derive bmu pt if needed
    cols = {str(c) for c in df.GetColumnNames()}
    if "topreco_bmu_pt" not in cols and "topreco_b1_index" in cols and "jet_pt" in cols:
        df, cols = ensure_col(
            df,
            cols,
            "topreco_bmu_pt",
            "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_pt.size()) ? jet_pt[topreco_b1_index] : -1.f",
        )

    # derive charge score if needed
    cols = {str(c) for c in df.GetColumnNames()}
    if "topreco_bmu_charge_score" not in cols and "topreco_b1_index" in cols and "jet_charge_score" in cols:
        df, cols = ensure_col(
            df,
            cols,
            "topreco_bmu_charge_score",
            "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_charge_score.size()) ? jet_charge_score[topreco_b1_index] : -1.f",
        )

    # derive b(mu) truth labels if available
    cols = {str(c) for c in df.GetColumnNames()}
    if "topreco_bmu_hflav" not in cols and "topreco_b1_index" in cols and "jet_hflav" in cols:
        df, cols = ensure_col(
            df,
            cols,
            "topreco_bmu_hflav",
            "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_hflav.size()) ? jet_hflav[topreco_b1_index] : -99",
        )
    if "topreco_bmu_pflavcharge" not in cols and "topreco_b1_index" in cols:
        pflav_branch = None
        if "jet_pflavcharge" in cols:
            pflav_branch = "jet_pflavcharge"
        elif "jet_pflavCharge" in cols:
            pflav_branch = "jet_pflavCharge"
        if pflav_branch is not None:
            df, cols = ensure_col(
                df,
                cols,
                "topreco_bmu_pflavcharge",
                f"(topreco_b1_index>=0 && topreco_b1_index<(int){pflav_branch}.size()) ? {pflav_branch}[topreco_b1_index] : 0",
            )

    return df


def compute_roc_auc(scores, labels):
    # labels: 1 signal class (mu-), 0 background class (mu+)
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return None, None, None

    pairs = sorted(zip(scores, labels), key=lambda x: x[0], reverse=True)
    tpr = [0.0]
    fpr = [0.0]
    tp = 0
    fp = 0
    prev_score = None
    for s, y in pairs:
        if prev_score is not None and s != prev_score:
            tpr.append(tp / pos)
            fpr.append(fp / neg)
        if y == 1:
            tp += 1
        else:
            fp += 1
        prev_score = s
    tpr.append(tp / pos)
    fpr.append(fp / neg)

    # Convert to the requested ROC convention:
    # x = (1 - background efficiency) = background rejection
    # y = signal efficiency
    sig_eff = tpr
    bkg_rej = [1.0 - x for x in fpr]

    # Sort by x-axis to compute AUC in this convention.
    pts = sorted(zip(bkg_rej, sig_eff), key=lambda p: p[0])
    auc = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        auc += 0.5 * dx * (pts[i][1] + pts[i - 1][1])

    x = [p[0] for p in pts]
    y = [p[1] for p in pts]
    return x, y, auc


def invert_scores(scores):
    return [1.0 - s for s in scores]


def extract_arrays(df_bin):
    arr = df_bin.AsNumpy(["topreco_bmu_charge_score", "mu0_charge"])
    scores = arr["topreco_bmu_charge_score"]
    charges = arr["mu0_charge"]
    out_s, out_l = [], []
    for s, q in zip(scores, charges):
        if not math.isfinite(float(s)):
            continue
        # Signal = mu-, Background = mu+
        if q < 0:
            out_s.append(float(s))
            out_l.append(1)
        elif q > 0:
            out_s.append(float(s))
            out_l.append(0)
    return out_s, out_l


def extract_arrays_truth_bjet(df_bin):
    arr = df_bin.AsNumpy(["topreco_bmu_charge_score", "topreco_bmu_hflav", "topreco_bmu_pflavcharge"])
    scores = arr["topreco_bmu_charge_score"]
    hfl = arr["topreco_bmu_hflav"]
    qfl = arr["topreco_bmu_pflavcharge"]
    out_s, out_l = [], []
    for s, hf, q in zip(scores, hfl, qfl):
        if not math.isfinite(float(s)):
            continue
        if int(hf) != 5:
            continue
        # Requested definition: signal = -1, background = +1
        if int(q) == -1:
            out_s.append(float(s))
            out_l.append(1)
        elif int(q) == 1:
            out_s.append(float(s))
            out_l.append(0)
    return out_s, out_l


def save_roc(x, y, auc, out_png, title):
    c = ROOT.TCanvas("croc", "", 800, 700)
    gr = ROOT.TGraph(len(x), array('d', x), array('d', y))
    gr.SetTitle(f"{title};1 - background efficiency;signal efficiency")
    gr.SetLineWidth(3)
    gr.SetLineColor(ROOT.kAzure + 1)
    gr.Draw("AL")
    diag = ROOT.TLine(0.0, 1.0, 1.0, 0.0)
    diag.SetLineStyle(2)
    diag.Draw("same")
    txt = ROOT.TLatex()
    txt.SetNDC(True)
    txt.SetTextSize(0.04)
    txt.DrawLatex(0.18, 0.84, f"AUC = {auc:.4f}")
    c.SaveAs(out_png)
    c.Close()


def save_auc_summary(bins_labels, auc_data, auc_mc, auc_mc_truth, out_png):
    c = ROOT.TCanvas("cauc", "", 1000, 700)
    n = len(bins_labels)
    x = array('d', [i + 0.5 for i in range(n)])

    yd = array('d', [auc_data.get(k, float('nan')) for k in bins_labels])
    ym = array('d', [auc_mc.get(k, float('nan')) for k in bins_labels])
    yt = array('d', [auc_mc_truth.get(k, float('nan')) for k in bins_labels])

    gd = ROOT.TGraph(n, x, yd)
    gm = ROOT.TGraph(n, x, ym)
    gt = ROOT.TGraph(n, x, yt)

    frame = ROOT.TH1F("frame_auc", "Jet-charge AUC vs b_{#mu} p_{T} bin; b_{#mu} p_{T} bin; AUC", n, 0, n)
    for i, lab in enumerate(bins_labels, start=1):
        frame.GetXaxis().SetBinLabel(i, lab)
    frame.SetMinimum(0.3)
    frame.SetMaximum(1.0)
    frame.Draw()

    gd.SetMarkerStyle(20)
    gd.SetMarkerSize(1.1)
    gd.SetMarkerColor(ROOT.kBlack)
    gd.SetLineColor(ROOT.kBlack)

    gm.SetMarkerStyle(21)
    gm.SetMarkerSize(1.1)
    gm.SetMarkerColor(ROOT.kAzure + 1)
    gm.SetLineColor(ROOT.kAzure + 1)

    gt.SetMarkerStyle(33)
    gt.SetMarkerSize(1.3)
    gt.SetMarkerColor(ROOT.kRed + 1)
    gt.SetLineColor(ROOT.kRed + 1)

    gd.Draw("PL same")
    gm.Draw("PL same")
    gt.Draw("PL same")

    leg = ROOT.TLegend(0.66, 0.75, 0.90, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    leg.AddEntry(gd, "Data", "pl")
    leg.AddEntry(gm, "t#bar{t} dileptonic (mu charge labels)", "pl")
    leg.AddEntry(gt, "t#bar{t} dileptonic truth (hflav=5, pflavCharge)", "pl")
    leg.Draw()

    c.SaveAs(out_png)
    c.Close()


def main():
    ap = argparse.ArgumentParser(description="Compute jet-charge AUC vs b(mu) pT bins for Data and MC")
    ap.add_argument("--data-snapshot", default="analysis/hists_by_process_prodv1_sel/data_snapshot.root")
    ap.add_argument("--mc-snapshot", default="analysis/hists_by_process_prodv1_sel/ttbar_dileptonic_snapshot.root")
    ap.add_argument("--tree", default="Events")
    ap.add_argument("--outdir", default="analysis/plots_auc_jetcharge_ptbins")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--bmu-deepb-min", type=float, default=0.3)
    ap.add_argument("--mu-id-cut", choices=["none", "loose", "medium", "tight"], default="none")
    ap.add_argument("--skip-pt-bins", action="store_true", help="Only compute overall AUC values (data and MC).")
    ap.add_argument(
        "--mc-roc-mode",
        choices=["mucharge", "truth", "both"],
        default="both",
        help="MC ROC label mode: mucharge (mu-/mu+), truth (hflav==5 and pflavcharge +/-1), or both.",
    )
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.ROOT.EnableImplicitMT(args.threads if args.threads > 0 else 0)

    df_data = ROOT.RDataFrame(args.tree, args.data_snapshot)
    df_mc = ROOT.RDataFrame(args.tree, args.mc_snapshot)

    df_data = apply_common_selection(df_data, args.bmu_deepb_min, args.mu_id_cut)
    df_mc = apply_common_selection(df_mc, args.bmu_deepb_min, args.mu_id_cut)
    cols_mc = {str(c) for c in df_mc.GetColumnNames()}

    pt_bins = [
        ("20-30", "topreco_bmu_pt >= 20 && topreco_bmu_pt < 30"),
        ("30-50", "topreco_bmu_pt >= 30 && topreco_bmu_pt < 50"),
        ("50-80", "topreco_bmu_pt >= 50 && topreco_bmu_pt < 80"),
        ("80-110", "topreco_bmu_pt >= 80 && topreco_bmu_pt < 110"),
        ("110-150", "topreco_bmu_pt >= 110 && topreco_bmu_pt < 150"),
        (">150", "topreco_bmu_pt >= 150"),
    ]

    auc_data = {}
    auc_mc = {}
    auc_mc_truth_bins = {}

    # Overall (same selection, no pT bin split): two values requested by user.
    s_all_d, l_all_d = extract_arrays(df_data)
    s_all_m, l_all_m = extract_arrays(df_mc)
    roc_all_d = compute_roc_auc(s_all_d, l_all_d)
    roc_all_m = compute_roc_auc(s_all_m, l_all_m)
    roc_all_d_inv = compute_roc_auc(invert_scores(s_all_d), l_all_d)
    roc_all_m_inv = compute_roc_auc(invert_scores(s_all_m), l_all_m)
    if roc_all_d[2] is not None:
        save_roc(roc_all_d[0], roc_all_d[1], roc_all_d[2], os.path.join(args.outdir, "roc_data_overall.png"), "Data (overall)")
    if args.mc_roc_mode in ("mucharge", "both") and roc_all_m[2] is not None:
        save_roc(roc_all_m[0], roc_all_m[1], roc_all_m[2], os.path.join(args.outdir, "roc_mc_overall.png"), "t#bar{t} dileptonic (overall)")
    with open(os.path.join(args.outdir, "auc_overall.txt"), "w") as f:
        f.write("Signal definition: mu- (mu0_charge < 0)\n")
        f.write("Background definition: mu+ (mu0_charge > 0)\n")
        f.write(f"auc_data_overall_score: {roc_all_d[2]}\n")
        f.write(f"auc_mc_overall_score: {roc_all_m[2]}\n")
        f.write(f"auc_data_overall_one_minus_score: {roc_all_d_inv[2]}\n")
        f.write(f"auc_mc_overall_one_minus_score: {roc_all_m_inv[2]}\n")
        f.write(f"n_data_overall: {len(s_all_d)}\n")
        f.write(f"n_mc_overall: {len(s_all_m)}\n")
    print(
        f"[auc_jetcharge_vs_ptbins] OVERALL: "
        f"AUC_data(score)={roc_all_d[2]} AUC_mc(score)={roc_all_m[2]} "
        f"AUC_data(1-score)={roc_all_d_inv[2]} AUC_mc(1-score)={roc_all_m_inv[2]} "
        f"n_data={len(s_all_d)} n_mc={len(s_all_m)}"
    )

    # Additional MC-truth ROC/AUC using b(mu) hadron flavour and parton-flavour charge.
    have_truth = {"topreco_bmu_hflav", "topreco_bmu_pflavcharge", "topreco_bmu_charge_score"}.issubset(cols_mc)
    if args.mc_roc_mode in ("truth", "both") and have_truth:
        s_all_truth, l_all_truth = extract_arrays_truth_bjet(df_mc)
        roc_all_truth = compute_roc_auc(s_all_truth, l_all_truth)
        roc_all_truth_inv = compute_roc_auc(invert_scores(s_all_truth), l_all_truth)
        if roc_all_truth[2] is not None:
            save_roc(
                roc_all_truth[0],
                roc_all_truth[1],
                roc_all_truth[2],
                os.path.join(args.outdir, "roc_mc_overall_truth_hflav5_pq.png"),
                "t#bar{t} dileptonic truth: hflav=5, q_{pflav}=-1(sig),+1(bkg)",
            )
        with open(os.path.join(args.outdir, "auc_overall_mc_truth_hflav5_pq.txt"), "w") as f:
            f.write("Sample: MC ttbar dileptonic\n")
            f.write("Selection: b(mu) jet hadron flavour == 5\n")
            f.write("Signal definition: jet_pflavcharge == -1\n")
            f.write("Background definition: jet_pflavcharge == +1\n")
            f.write(f"auc_mc_truth_score: {roc_all_truth[2]}\n")
            f.write(f"auc_mc_truth_one_minus_score: {roc_all_truth_inv[2]}\n")
            f.write(f"n_mc_truth: {len(s_all_truth)}\n")
        print(
            f"[auc_jetcharge_vs_ptbins] OVERALL MC-TRUTH: "
            f"AUC(score)={roc_all_truth[2]} AUC(1-score)={roc_all_truth_inv[2]} n={len(s_all_truth)}"
        )
    elif args.mc_roc_mode in ("truth", "both"):
        print("[auc_jetcharge_vs_ptbins] MC truth branches missing (topreco_bmu_hflav/topreco_bmu_pflavcharge), skipping truth ROC.")

    if args.skip_pt_bins:
        print(f"[auc_jetcharge_vs_ptbins] done: {args.outdir}")
        return

    for label, sel in pt_bins:
        out_bin = os.path.join(args.outdir, label.replace(">", "gt").replace("-", "to"))
        os.makedirs(out_bin, exist_ok=True)

        dfd = df_data.Filter(sel, f"bmu pt {label}")
        dfm = df_mc.Filter(sel, f"bmu pt {label}")

        sd, ld = extract_arrays(dfd)
        sm, lm = extract_arrays(dfm)

        roc_d = compute_roc_auc(sd, ld)
        roc_m = compute_roc_auc(sm, lm)
        roc_d_inv = compute_roc_auc(invert_scores(sd), ld)
        roc_m_inv = compute_roc_auc(invert_scores(sm), lm)
        roc_m_truth = None
        roc_m_truth_inv = None
        if args.mc_roc_mode in ("truth", "both") and have_truth:
            s_truth, l_truth = extract_arrays_truth_bjet(dfm)
            roc_m_truth = compute_roc_auc(s_truth, l_truth)
            roc_m_truth_inv = compute_roc_auc(invert_scores(s_truth), l_truth)

        if roc_d[2] is not None:
            auc_data[label] = roc_d[2]
            save_roc(roc_d[0], roc_d[1], roc_d[2], os.path.join(out_bin, "roc_data.png"), f"Data, b_{{#mu}} p_{{T}} {label} GeV")
        else:
            auc_data[label] = float('nan')

        if roc_m[2] is not None:
            auc_mc[label] = roc_m[2]
            save_roc(roc_m[0], roc_m[1], roc_m[2], os.path.join(out_bin, "roc_mc.png"), f"t#bar{{t}} dileptonic, b_{{#mu}} p_{{T}} {label} GeV")
        else:
            auc_mc[label] = float('nan')

        with open(os.path.join(out_bin, "auc.txt"), "w") as f:
            f.write(f"pt_bin: {label}\n")
            f.write(f"auc_data_score: {auc_data[label]}\n")
            f.write(f"auc_mc_score: {auc_mc[label]}\n")
            f.write(f"auc_data_one_minus_score: {roc_d_inv[2]}\n")
            f.write(f"auc_mc_one_minus_score: {roc_m_inv[2]}\n")
            f.write(f"n_data: {len(sd)}\n")
            f.write(f"n_mc: {len(sm)}\n")
            if roc_m_truth is not None:
                f.write(f"auc_mc_truth_hflav5_pq_score: {roc_m_truth[2]}\n")
                f.write(f"auc_mc_truth_hflav5_pq_one_minus_score: {roc_m_truth_inv[2]}\n")
                f.write(f"n_mc_truth_hflav5_pq: {len(s_truth)}\n")

        if args.mc_roc_mode in ("mucharge", "both"):
            print(
                f"[auc_jetcharge_vs_ptbins] {label}: "
                f"AUC_data(score)={auc_data[label]} AUC_mc(score)={auc_mc[label]} "
                f"AUC_data(1-score)={roc_d_inv[2]} AUC_mc(1-score)={roc_m_inv[2]} "
                f"n_data={len(sd)} n_mc={len(sm)}"
            )
        else:
            print(
                f"[auc_jetcharge_vs_ptbins] {label}: "
                f"AUC_data(score)={auc_data[label]} "
                f"AUC_data(1-score)={roc_d_inv[2]} "
                f"n_data={len(sd)} n_mc={len(sm)}"
            )
        if roc_m_truth is not None and roc_m_truth[2] is not None:
            auc_mc_truth_bins[label] = roc_m_truth[2]
            save_roc(
                roc_m_truth[0],
                roc_m_truth[1],
                roc_m_truth[2],
                os.path.join(out_bin, "roc_mc_truth_hflav5_pq.png"),
                f"MC truth, hflav=5, q_{{pflav}}=-1/+1, b_{{#mu}} p_{{T}} {label} GeV",
            )
        else:
            auc_mc_truth_bins[label] = float('nan')

    labels = [x[0] for x in pt_bins]
    save_auc_summary(
        labels,
        auc_data,
        auc_mc,
        auc_mc_truth_bins,
        os.path.join(args.outdir, "auc_vs_ptbins_data_mc.png"),
    )

    print(f"[auc_jetcharge_vs_ptbins] done: {args.outdir}")


if __name__ == "__main__":
    main()
