#!/usr/bin/env python3
"""Plot dilepton ttbar reconstruction quantities from local ntuples."""

import argparse
import os

import ROOT

from top_reco_utils import build_rdf, define_common_columns, define_top_reco_columns


def save_hist(hist, outdir, name, title="", xtitle="", ytitle="Events"):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 900, 700)
    hist.SetLineWidth(2)
    if title:
        hist.SetTitle(title)
    if xtitle:
        hist.GetXaxis().SetTitle(xtitle)
    if ytitle:
        hist.GetYaxis().SetTitle(ytitle)
    hist.Draw("HIST E")
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def save_hist2d(hist, outdir, name, title="", xtitle="", ytitle=""):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 900, 700)
    if title:
        hist.SetTitle(title)
    if xtitle:
        hist.GetXaxis().SetTitle(xtitle)
    if ytitle:
        hist.GetYaxis().SetTitle(ytitle)
    hist.Draw("COLZ")
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def save_hist_overlay(hist1, hist2, outdir, name, label1, label2, title="", xtitle="", ytitle="Events"):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 900, 700)
    hist1.SetLineColor(ROOT.kBlue + 1)
    hist2.SetLineColor(ROOT.kRed + 1)
    hist1.SetLineWidth(2)
    hist2.SetLineWidth(2)
    max_y = max(hist1.GetMaximum(), hist2.GetMaximum())
    hist1.SetMaximum(1.25 * max_y if max_y > 0 else 1.0)
    if title:
        hist1.SetTitle(title)
    if xtitle:
        hist1.GetXaxis().SetTitle(xtitle)
    if ytitle:
        hist1.GetYaxis().SetTitle(ytitle)
    hist1.Draw("HIST E")
    hist2.Draw("HIST E same")
    leg = ROOT.TLegend(0.62, 0.76, 0.88, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    leg.AddEntry(hist1, label1, "l")
    leg.AddEntry(hist2, label2, "l")
    leg.Draw()
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def save_hist_stack(hists_with_labels, outdir, name, title="", xtitle="", ytitle="Events", overlay_hist=None, overlay_label="all"):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 900, 700)
    stack = ROOT.THStack(f"hs_{name}", title if title else "")
    colors = [ROOT.kAzure + 1, ROOT.kOrange + 7, ROOT.kGreen + 2, ROOT.kMagenta + 1, ROOT.kCyan + 1, ROOT.kRed + 1]
    leg = ROOT.TLegend(0.62, 0.62, 0.88, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    for i, (hist, label) in enumerate(hists_with_labels):
        hist.SetFillColor(colors[i % len(colors)])
        hist.SetLineColor(colors[i % len(colors)])
        hist.SetLineWidth(1)
        stack.Add(hist)
        leg.AddEntry(hist, label, "f")
    stack.Draw("hist")
    if xtitle:
        stack.GetXaxis().SetTitle(xtitle)
    if ytitle:
        stack.GetYaxis().SetTitle(ytitle)
    if overlay_hist is not None:
        overlay_band = overlay_hist.Clone(f"{overlay_hist.GetName()}_{name}_unc")
        overlay_band.SetFillColorAlpha(ROOT.kGray + 1, 0.35)
        overlay_band.SetLineColor(0)
        overlay_band.SetMarkerSize(0)
        overlay_hist.SetFillStyle(0)
        overlay_hist.SetFillColor(0)
        overlay_hist.SetLineColor(ROOT.kBlack)
        overlay_hist.SetLineWidth(3)
        overlay_band.Draw("E2 same")
        overlay_hist.Draw("hist same")
        leg.AddEntry(overlay_hist, overlay_label, "l")
        leg.AddEntry(overlay_band, "stat. unc.", "f")
    leg.Draw()
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def save_hist_stack_triptych(panels, outdir, name, xtitle="", ytitle="Events"):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 1800, 600)
    c.Divide(3, 1)
    colors = [ROOT.kAzure + 1, ROOT.kOrange + 7, ROOT.kGreen + 2, ROOT.kMagenta + 1, ROOT.kCyan + 1, ROOT.kRed + 1]
    for i, panel in enumerate(panels, start=1):
        c.cd(i)
        stack = ROOT.THStack(f"hs_{name}_{i}", panel["title"])
        leg = ROOT.TLegend(0.58, 0.60, 0.88, 0.88)
        leg.SetBorderSize(0)
        leg.SetFillStyle(0)
        for j, (hist, label) in enumerate(panel["hists"]):
            hist.SetFillColor(colors[j % len(colors)])
            hist.SetLineColor(colors[j % len(colors)])
            hist.SetLineWidth(1)
            stack.Add(hist)
            leg.AddEntry(hist, label, "f")
        stack.Draw("hist")
        stack.GetXaxis().SetTitle(xtitle)
        stack.GetYaxis().SetTitle(ytitle)
        overlay = panel["overlay"]
        overlay.SetFillStyle(0)
        overlay.SetFillColor(0)
        overlay.SetLineColor(ROOT.kBlack)
        overlay.SetLineWidth(3)
        overlay.Draw("hist same")
        leg.AddEntry(overlay, "all", "l")
        leg.Draw()
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def main():
    parser = argparse.ArgumentParser(description="Plot dilepton reconstruction quantities using RDataFrame.")
    parser.add_argument(
        "--input",
        default="run/local_dilep_emu_os/profile_timing_10k_afterfix_numEvent100000.root",
        help="Input ROOT file",
    )
    parser.add_argument("--tree", default="Events", help="Input tree name")
    parser.add_argument("--outdir", default="analysis/plots_ttbar_reco", help="Output plot directory")
    parser.add_argument("--threads", type=int, default=0, help="RDataFrame MT threads (0 = ROOT default)")
    parser.add_argument(
        "--mu-id-cut",
        choices=["none", "loose", "medium", "tight"],
        default="tight",
        help="Muon ID requirement applied before plotting.",
    )
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)

    df = build_rdf(args.input, args.tree, args.threads)
    initial_cols = {str(c) for c in df.GetColumnNames()}

    # If running on a processed snapshot, reuse precomputed columns.
    has_snapshot_reco = {"mu0_pt", "el0_pt", "topreco_chi2", "topreco_t1_mass", "topreco_b1_index"}.issubset(initial_cols)
    if has_snapshot_reco:
        print("[plot_ttbar_reco] Detected snapshot-style input, reusing precomputed mu0/el0/topreco columns.")
        if "analysis_weight" not in initial_cols:
            df = df.Define("analysis_weight", "1.0f")
        if "mu0_isLoose" not in initial_cols and "muon_isLoose" in initial_cols:
            df = df.Define("mu0_isLoose", "safe_first_i(muon_isLoose, -1)")
        if "mu0_isMedium" not in initial_cols and "muon_isMedium" in initial_cols:
            df = df.Define("mu0_isMedium", "safe_first_i(muon_isMedium, -1)")
        if "mu0_isTight" not in initial_cols and "muon_isTight" in initial_cols:
            df = df.Define("mu0_isTight", "safe_first_i(muon_isTight, -1)")
        if "mu0_idbin" not in initial_cols:
            if {"mu0_isTight", "mu0_isMedium", "mu0_isLoose"}.issubset(initial_cols):
                df = df.Define("mu0_idbin", "(mu0_isTight>0)?2:((mu0_isMedium>0)?1:((mu0_isLoose>0)?0:-1))")
            else:
                df = df.Define("mu0_idbin", "-1")
        df = df.Filter("mu0_pt > 0 && el0_pt > 0", "muon+electron present")
    else:
        df = define_common_columns(df)
        df = df.Define("mu0_idbin", "(mu0_isTight>0)?2:((mu0_isMedium>0)?1:((mu0_isLoose>0)?0:-1))")
        df = df.Filter("mu0_pt > 0 && el0_pt > 0", "muon+electron present")
        df = define_top_reco_columns(df)

    if args.mu_id_cut != "none":
        mu_id_expr = {
            "loose": "mu0_isLoose > 0",
            "medium": "mu0_isMedium > 0",
            "tight": "mu0_isTight > 0",
        }[args.mu_id_cut]
        needed_col = {
            "loose": "mu0_isLoose",
            "medium": "mu0_isMedium",
            "tight": "mu0_isTight",
        }[args.mu_id_cut]
        colnames_now = {str(c) for c in df.GetColumnNames()}
        if needed_col not in colnames_now:
            raise RuntimeError(
                f"Requested --mu-id-cut {args.mu_id_cut}, but branch '{needed_col}' is missing in this input."
            )
        df = df.Filter(mu_id_expr, f"muon {args.mu_id_cut} ID")

    # Snapshot compatibility: some reduced snapshots do not persist electron cutBased ID.
    colnames_now = {str(c) for c in df.GetColumnNames()}
    if "el0_cutBased" not in colnames_now:
        df = df.Define("el0_cutBased", "-1")

    colnames = {str(c) for c in df.GetColumnNames()}
    be_btag_candidates = [
        ("jet_btagPNetB", "PNetB"),
        ("jet_btag_pfParticleNetFromMiniAODAK4B", "PNetB"),
        ("jet_btag_pfRobustParTAK4JetTags_ParTBvsAll", "ParTBvsAll"),
    ]
    be_btag_branch = None
    be_btag_label = None
    for branch_name, branch_label in be_btag_candidates:
        if branch_name in colnames:
            be_btag_branch = branch_name
            be_btag_label = branch_label
            break
    if be_btag_branch is None:
        raise RuntimeError("No PNet/ParT b-tag score branch found (checked jet_btagPNetB, jet_btag_pfParticleNetFromMiniAODAK4B, jet_btag_pfRobustParTAK4JetTags_ParTBvsAll).")

    # Lepton kinematics + IDs.
    h_mu_pt = df.Histo1D(("h_mu_pt", "Muon p_{T};p_{T}^{#mu} [GeV];Events", 80, 0, 400), "mu0_pt", "analysis_weight")
    h_mu_eta = df.Histo1D(("h_mu_eta", "Muon #eta;#eta^{#mu};Events", 60, -3.0, 3.0), "mu0_eta", "analysis_weight")
    h_mu_phi = df.Histo1D(("h_mu_phi", "Muon #phi;#phi^{#mu};Events", 64, -3.2, 3.2), "mu0_phi", "analysis_weight")
    h_mu_id = df.Histo1D(("h_mu_id", "Muon ID (0 loose, 1 medium, 2 tight);ID bin;Events", 4, -0.5, 3.5), "mu0_idbin", "analysis_weight")
    h_mu_charge = df.Histo1D(("h_mu_charge", "Muon charge;charge^{#mu};Events", 3, -1.5, 1.5), "mu0_charge", "analysis_weight")

    h_el_pt = df.Histo1D(("h_el_pt", "Electron p_{T};p_{T}^{e} [GeV];Events", 80, 0, 400), "el0_pt", "analysis_weight")
    h_el_eta = df.Histo1D(("h_el_eta", "Electron #eta;#eta^{e};Events", 60, -3.0, 3.0), "el0_eta", "analysis_weight")
    h_el_phi = df.Histo1D(("h_el_phi", "Electron #phi;#phi^{e};Events", 64, -3.2, 3.2), "el0_phi", "analysis_weight")
    h_el_id = df.Histo1D(("h_el_id", "Electron cutBased ID;cutBased;Events", 6, -0.5, 5.5), "el0_cutBased", "analysis_weight")
    h_el_charge = df.Histo1D(("h_el_charge", "Electron charge;charge^{e};Events", 3, -1.5, 1.5), "el0_charge", "analysis_weight")

    # Jet and flavour composition.
    h_njet = df.Histo1D(("h_njet", "Selected jet multiplicity;N_{jets};Events", 10, -0.5, 9.5), "nJetSel", "analysis_weight")
    df = df.Define("nJetHadFlav5", "ROOT::VecOps::Sum(jet_hflav == 5)")
    h_njet_hflav5 = df.Histo1D(("h_njet_hflav5", "Jet multiplicity with hadron flavour == 5;N_{jets}(hflav=5);Events", 12, -0.5, 11.5), "nJetHadFlav5", "analysis_weight")
    h_jet_pt = df.Histo1D(("h_jet_pt", "Jet p_{T};p_{T}^{jet} [GeV];Jets", 80, 0, 400), "jet_pt", "analysis_weight")
    h_jet_eta = df.Histo1D(("h_jet_eta", "Jet #eta;#eta^{jet};Jets", 60, -3.0, 3.0), "jet_eta", "analysis_weight")
    h_jet_phi = df.Histo1D(("h_jet_phi", "Jet #phi;#phi^{jet};Jets", 64, -3.2, 3.2), "jet_phi", "analysis_weight")
    h_jet_flav = df.Histo1D(("h_jet_flav", "Jet hadron flavour;hadron flavour;Jets", 11, -0.5, 10.5), "jet_hflav")

    # Top-reco fit outputs.
    df_fit = df.Filter("topreco_converged", "top fit converged")
    fit_defs = [
        ("topreco_bmu_index", "topreco_b1_index"),
        ("topreco_be_index", "topreco_b2_index"),
        ("topreco_bmu_pt", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_pt.size()) ? jet_pt[topreco_bmu_index] : -1.f"),
        ("topreco_be_pt", "(topreco_be_index>=0 && topreco_be_index<(int)jet_pt.size()) ? jet_pt[topreco_be_index] : -1.f"),
        ("topreco_bmu_eta", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_eta.size()) ? jet_eta[topreco_bmu_index] : -9.f"),
        ("topreco_be_eta", "(topreco_be_index>=0 && topreco_be_index<(int)jet_eta.size()) ? jet_eta[topreco_be_index] : -9.f"),
        ("topreco_bmu_hflav", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_hflav.size()) ? jet_hflav[topreco_bmu_index] : -99"),
        ("topreco_be_hflav", "(topreco_be_index>=0 && topreco_be_index<(int)jet_hflav.size()) ? jet_hflav[topreco_be_index] : -99"),
        ("topreco_bmu_btagDeepB", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_btagDeepB.size()) ? jet_btagDeepB[topreco_bmu_index] : -1.f"),
        ("topreco_be_btagDeepB", "(topreco_be_index>=0 && topreco_be_index<(int)jet_btagDeepB.size()) ? jet_btagDeepB[topreco_be_index] : -1.f"),
        ("topreco_be_btagAlt", f"(topreco_be_index>=0 && topreco_be_index<(int){be_btag_branch}.size()) ? {be_btag_branch}[topreco_be_index] : -1.f"),
        ("topreco_bmu_charge_score", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_charge_score.size()) ? jet_charge_score[topreco_bmu_index] : -9.f"),
        ("topreco_be_charge_score", "(topreco_be_index>=0 && topreco_be_index<(int)jet_charge_score.size()) ? jet_charge_score[topreco_be_index] : -9.f"),
        ("topreco_bmu_charge_k03", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_charge_k03.size()) ? jet_charge_k03[topreco_bmu_index] : -9.f"),
        ("topreco_bmu_charge_k05", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_charge_k05.size()) ? jet_charge_k05[topreco_bmu_index] : -9.f"),
        ("topreco_bmu_charge_k10", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_charge_k10.size()) ? jet_charge_k10[topreco_bmu_index] : -9.f"),
        ("topreco_bmu_charge_k20", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_charge_k20.size()) ? jet_charge_k20[topreco_bmu_index] : -9.f"),
        ("topreco_be_charge_k03", "(topreco_be_index>=0 && topreco_be_index<(int)jet_charge_k03.size()) ? jet_charge_k03[topreco_be_index] : -9.f"),
        ("topreco_be_charge_k05", "(topreco_be_index>=0 && topreco_be_index<(int)jet_charge_k05.size()) ? jet_charge_k05[topreco_be_index] : -9.f"),
        ("topreco_be_charge_k10", "(topreco_be_index>=0 && topreco_be_index<(int)jet_charge_k10.size()) ? jet_charge_k10[topreco_be_index] : -9.f"),
        ("topreco_be_charge_k20", "(topreco_be_index>=0 && topreco_be_index<(int)jet_charge_k20.size()) ? jet_charge_k20[topreco_be_index] : -9.f"),
        ("topreco_bmu_ParTNegvsAll", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTNegvsAll.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTNegvsAll[topreco_bmu_index] : -1.f"),
        ("topreco_bmu_ParTPosvsAll", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTPosvsAll.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTPosvsAll[topreco_bmu_index] : -1.f"),
        ("topreco_bmu_ParTZerovsAll", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTZerovsAll.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTZerovsAll[topreco_bmu_index] : -1.f"),
        ("topreco_bmu_ParTPosvsNeg", "(topreco_bmu_index>=0 && topreco_bmu_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTPosvsNeg.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTPosvsNeg[topreco_bmu_index] : -1.f"),
        ("topreco_be_ParTNegvsAll", "(topreco_be_index>=0 && topreco_be_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTNegvsAll.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTNegvsAll[topreco_be_index] : -1.f"),
        ("topreco_be_ParTPosvsAll", "(topreco_be_index>=0 && topreco_be_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTPosvsAll.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTPosvsAll[topreco_be_index] : -1.f"),
        ("topreco_be_ParTZerovsAll", "(topreco_be_index>=0 && topreco_be_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTZerovsAll.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTZerovsAll[topreco_be_index] : -1.f"),
        ("topreco_be_ParTPosvsNeg", "(topreco_be_index>=0 && topreco_be_index<(int)jet_btag_pfRobustParTAK4JetTags_ParTPosvsNeg.size()) ? jet_btag_pfRobustParTAK4JetTags_ParTPosvsNeg[topreco_be_index] : -1.f"),
    ]
    fit_cols = {str(c) for c in df_fit.GetColumnNames()}
    for name, expr in fit_defs:
        if name in fit_cols:
            df_fit = df_fit.Redefine(name, expr)
        else:
            df_fit = df_fit.Define(name, expr)
            fit_cols.add(name)
    h_chi2 = df_fit.Histo1D(("h_top_chi2", "Top fit #chi^{2};#chi^{2};Events", 80, 0, 80), "topreco_chi2", "analysis_weight")
    h_topmu = df_fit.Histo1D(("h_topmu_mass", "Top(#mu) mass;m_{top,#mu} [GeV];Events", 80, 100, 300), "topreco_t1_mass", "analysis_weight")
    h_tope = df_fit.Histo1D(("h_tope_mass", "Top(e) mass;m_{top,e} [GeV];Events", 80, 100, 300), "topreco_t2_mass", "analysis_weight")
    h_wmu = df_fit.Histo1D(("h_wmu_mass", "W(#mu) mass;m_{W,#mu} [GeV];Events", 80, 0, 160), "topreco_w1_mass", "analysis_weight")
    h_we = df_fit.Histo1D(("h_we_mass", "W(e) mass;m_{W,e} [GeV];Events", 80, 0, 160), "topreco_w2_mass", "analysis_weight")
    h_tt = df_fit.Histo1D(("h_tt_mass", "t#bar{t} mass;m_{t#bar{t}} [GeV];Events", 100, 200, 1500), "topreco_ttbar_mass", "analysis_weight")
    h_nu_pt = df_fit.Histo1D(("h_nu_pt", "#nu p_{T};p_{T}^{#nu} [GeV];Events", 80, 0, 400), "topreco_nu_pt", "analysis_weight")
    h_nub_pt = df_fit.Histo1D(("h_nub_pt", "#bar{#nu} p_{T};p_{T}^{#bar{#nu}} [GeV];Events", 80, 0, 400), "topreco_nubar_pt", "analysis_weight")
    h_met_res = df_fit.Histo1D(("h_met_res", "MET constraint residual;|#Delta MET| [GeV];Events", 80, 0, 120), "topreco_met_residual", "analysis_weight")
    h_bmu_pt = df_fit.Histo1D(("h_bmu_pt", "b_{#mu} candidate p_{T};p_{T}^{b_{#mu}} [GeV];Events", 80, 0, 400), "topreco_bmu_pt", "analysis_weight")
    h_be_pt = df_fit.Histo1D(("h_be_pt", "b_{e} candidate p_{T};p_{T}^{b_{e}} [GeV];Events", 80, 0, 400), "topreco_be_pt", "analysis_weight")
    h_bmu_eta = df_fit.Histo1D(("h_bmu_eta", "b_{#mu} candidate #eta;#eta^{b_{#mu}};Events", 60, -3.0, 3.0), "topreco_bmu_eta", "analysis_weight")
    h_be_eta = df_fit.Histo1D(("h_be_eta", "b_{e} candidate #eta;#eta^{b_{e}};Events", 60, -3.0, 3.0), "topreco_be_eta", "analysis_weight")
    h_bmu_hflav = df_fit.Histo1D(("h_bmu_hflav", "b_{#mu} candidate hadron flavour;hadron flavour;Events", 11, -0.5, 10.5), "topreco_bmu_hflav", "analysis_weight")
    h_be_hflav = df_fit.Histo1D(("h_be_hflav", "b_{e} candidate hadron flavour;hadron flavour;Events", 11, -0.5, 10.5), "topreco_be_hflav", "analysis_weight")
    h_bmu_btag = df_fit.Histo1D(("h_bmu_btagDeepB", "b_{#mu} candidate DeepB;DeepB;Events", 60, 0.0, 1.0), "topreco_bmu_btagDeepB", "analysis_weight")
    h_be_btag = df_fit.Histo1D(("h_be_btagDeepB", "b_{e} candidate DeepB;DeepB;Events", 60, 0.0, 1.0), "topreco_be_btagDeepB", "analysis_weight")
    h_bmu_charge_score = df_fit.Histo1D(("h_bmu_charge_score", "b_{#mu} charge score;charge score;Events", 20, 0.0, 1.0), "topreco_bmu_charge_score", "analysis_weight")
    h_be_charge_score = df_fit.Histo1D(("h_be_charge_score", "b_{e} charge score;charge score;Events", 20, 0.0, 1.0), "topreco_be_charge_score", "analysis_weight")
    df_fit_muplus = df_fit.Filter("mu0_charge == 1", "mu charge +1")
    df_fit_muminus = df_fit.Filter("mu0_charge == -1", "mu charge -1")
    h_bmu_charge_score_muplus = df_fit_muplus.Histo1D(
        ("h_bmu_charge_score_muplus", "b_{#mu} charge score (mu charge +1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_muminus = df_fit_muminus.Histo1D(
        ("h_bmu_charge_score_muminus", "b_{#mu} charge score (mu charge -1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_be_charge_score_muplus = df_fit_muplus.Histo1D(
        ("h_be_charge_score_muplus", "b_{e} charge score (mu charge +1);charge score;Events", 20, 0.0, 1.0),
        "topreco_be_charge_score",
        "analysis_weight",
    )
    h_be_charge_score_muminus = df_fit_muminus.Histo1D(
        ("h_be_charge_score_muminus", "b_{e} charge score (mu charge -1);charge score;Events", 20, 0.0, 1.0),
        "topreco_be_charge_score",
        "analysis_weight",
    )
    df_fit_bmu_hflav5 = df_fit.Filter("topreco_bmu_hflav == 5", "bmu hadron flavour == 5")
    h_bmu_charge_score_bmu_hflav5 = df_fit_bmu_hflav5.Histo1D(
        ("h_bmu_charge_score_bmu_hflav5", "b_{#mu} charge score (b_{#mu} hflav=5);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_be_charge_score_bmu_hflav5 = df_fit_bmu_hflav5.Histo1D(
        ("h_be_charge_score_bmu_hflav5", "b_{e} charge score (b_{#mu} hflav=5);charge score;Events", 20, 0.0, 1.0),
        "topreco_be_charge_score",
        "analysis_weight",
    )
    df_fit_2j_be03 = df_fit.Filter("nJetSel == 2 && topreco_be_btagAlt > 0.3", "nJetSel==2, be btag>0.3")
    df_fit_3j_be03 = df_fit.Filter("nJetSel == 3 && topreco_be_btagAlt > 0.3", "nJetSel==3, be btag>0.3")
    df_fit_4j_be03 = df_fit.Filter("nJetSel == 4 && topreco_be_btagAlt > 0.3", "nJetSel==4, be btag>0.3")
    df_fit_2j_be03_bmu_hflav5 = df_fit_2j_be03.Filter("topreco_bmu_hflav == 5", "bmu hadron flavour == 5")
    df_fit_3j_be03_bmu_hflav5 = df_fit_3j_be03.Filter("topreco_bmu_hflav == 5", "bmu hadron flavour == 5")
    df_fit_4j_be03_bmu_hflav5 = df_fit_4j_be03.Filter("topreco_bmu_hflav == 5", "bmu hadron flavour == 5")
    h_bmu_charge_score_2j_be03 = df_fit_2j_be03.Histo1D(
        ("h_bmu_charge_score_2j_be03", "b_{#mu} charge score (N_{jets}=2, b_{e} btag>0.3);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_3j_be03 = df_fit_3j_be03.Histo1D(
        ("h_bmu_charge_score_3j_be03", "b_{#mu} charge score (N_{jets}=3, b_{e} btag>0.3);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_4j_be03 = df_fit_4j_be03.Histo1D(
        ("h_bmu_charge_score_4j_be03", "b_{#mu} charge score (N_{jets}=4, b_{e} btag>0.3);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_2j_be03_bmu_hflav5 = df_fit_2j_be03_bmu_hflav5.Histo1D(
        ("h_bmu_charge_score_2j_be03_bmu_hflav5", "b_{#mu} charge score (N_{jets}=2, b_{e} btag>0.3, b_{#mu} hflav=5);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_3j_be03_bmu_hflav5 = df_fit_3j_be03_bmu_hflav5.Histo1D(
        ("h_bmu_charge_score_3j_be03_bmu_hflav5", "b_{#mu} charge score (N_{jets}=3, b_{e} btag>0.3, b_{#mu} hflav=5);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_4j_be03_bmu_hflav5 = df_fit_4j_be03_bmu_hflav5.Histo1D(
        ("h_bmu_charge_score_4j_be03_bmu_hflav5", "b_{#mu} charge score (N_{jets}=4, b_{e} btag>0.3, b_{#mu} hflav=5);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    df_fit_2j_be03_muplus = df_fit_2j_be03.Filter("mu0_charge == 1", "mu charge +1")
    df_fit_2j_be03_muminus = df_fit_2j_be03.Filter("mu0_charge == -1", "mu charge -1")
    df_fit_3j_be03_muplus = df_fit_3j_be03.Filter("mu0_charge == 1", "mu charge +1")
    df_fit_3j_be03_muminus = df_fit_3j_be03.Filter("mu0_charge == -1", "mu charge -1")
    df_fit_4j_be03_muplus = df_fit_4j_be03.Filter("mu0_charge == 1", "mu charge +1")
    df_fit_4j_be03_muminus = df_fit_4j_be03.Filter("mu0_charge == -1", "mu charge -1")
    h_bmu_charge_score_2j_be03_muplus = df_fit_2j_be03_muplus.Histo1D(
        ("h_bmu_charge_score_2j_be03_muplus", "b_{#mu} charge score (N_{jets}=2, b_{e} btag>0.3, #mu charge +1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_2j_be03_muminus = df_fit_2j_be03_muminus.Histo1D(
        ("h_bmu_charge_score_2j_be03_muminus", "b_{#mu} charge score (N_{jets}=2, b_{e} btag>0.3, #mu charge -1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_3j_be03_muplus = df_fit_3j_be03_muplus.Histo1D(
        ("h_bmu_charge_score_3j_be03_muplus", "b_{#mu} charge score (N_{jets}=3, b_{e} btag>0.3, #mu charge +1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_3j_be03_muminus = df_fit_3j_be03_muminus.Histo1D(
        ("h_bmu_charge_score_3j_be03_muminus", "b_{#mu} charge score (N_{jets}=3, b_{e} btag>0.3, #mu charge -1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_4j_be03_muplus = df_fit_4j_be03_muplus.Histo1D(
        ("h_bmu_charge_score_4j_be03_muplus", "b_{#mu} charge score (N_{jets}=4, b_{e} btag>0.3, #mu charge +1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_score_4j_be03_muminus = df_fit_4j_be03_muminus.Histo1D(
        ("h_bmu_charge_score_4j_be03_muminus", "b_{#mu} charge score (N_{jets}=4, b_{e} btag>0.3, #mu charge -1);charge score;Events", 20, 0.0, 1.0),
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h_bmu_charge_k03 = df_fit.Histo1D(("h_bmu_charge_k03", "b_{#mu} charge k=0.3;charge_{k=0.3};Events", 80, -2.0, 2.0), "topreco_bmu_charge_k03", "analysis_weight")
    h_bmu_charge_k05 = df_fit.Histo1D(("h_bmu_charge_k05", "b_{#mu} charge k=0.5;charge_{k=0.5};Events", 80, -2.0, 2.0), "topreco_bmu_charge_k05", "analysis_weight")
    h_bmu_charge_k10 = df_fit.Histo1D(("h_bmu_charge_k10", "b_{#mu} charge k=1.0;charge_{k=1.0};Events", 80, -2.0, 2.0), "topreco_bmu_charge_k10", "analysis_weight")
    h_bmu_charge_k20 = df_fit.Histo1D(("h_bmu_charge_k20", "b_{#mu} charge k=2.0;charge_{k=2.0};Events", 80, -2.0, 2.0), "topreco_bmu_charge_k20", "analysis_weight")
    h_be_charge_k03 = df_fit.Histo1D(("h_be_charge_k03", "b_{e} charge k=0.3;charge_{k=0.3};Events", 80, -2.0, 2.0), "topreco_be_charge_k03", "analysis_weight")
    h_be_charge_k05 = df_fit.Histo1D(("h_be_charge_k05", "b_{e} charge k=0.5;charge_{k=0.5};Events", 80, -2.0, 2.0), "topreco_be_charge_k05", "analysis_weight")
    h_be_charge_k10 = df_fit.Histo1D(("h_be_charge_k10", "b_{e} charge k=1.0;charge_{k=1.0};Events", 80, -2.0, 2.0), "topreco_be_charge_k10", "analysis_weight")
    h_be_charge_k20 = df_fit.Histo1D(("h_be_charge_k20", "b_{e} charge k=2.0;charge_{k=2.0};Events", 80, -2.0, 2.0), "topreco_be_charge_k20", "analysis_weight")
    h_bmu_parTNegvsAll = df_fit.Histo1D(("h_bmu_parTNegvsAll", "b_{#mu} ParTNegvsAll;score;Events", 60, 0.0, 1.0), "topreco_bmu_ParTNegvsAll", "analysis_weight")
    h_bmu_parTPosvsAll = df_fit.Histo1D(("h_bmu_parTPosvsAll", "b_{#mu} ParTPosvsAll;score;Events", 60, 0.0, 1.0), "topreco_bmu_ParTPosvsAll", "analysis_weight")
    h_bmu_parTZerovsAll = df_fit.Histo1D(("h_bmu_parTZerovsAll", "b_{#mu} ParTZerovsAll;score;Events", 60, 0.0, 1.0), "topreco_bmu_ParTZerovsAll", "analysis_weight")
    h_bmu_parTPosvsNeg = df_fit.Histo1D(("h_bmu_parTPosvsNeg", "b_{#mu} ParTPosvsNeg;score;Events", 60, 0.0, 1.0), "topreco_bmu_ParTPosvsNeg", "analysis_weight")
    h_be_parTNegvsAll = df_fit.Histo1D(("h_be_parTNegvsAll", "b_{e} ParTNegvsAll;score;Events", 60, 0.0, 1.0), "topreco_be_ParTNegvsAll", "analysis_weight")
    h_be_parTPosvsAll = df_fit.Histo1D(("h_be_parTPosvsAll", "b_{e} ParTPosvsAll;score;Events", 60, 0.0, 1.0), "topreco_be_ParTPosvsAll", "analysis_weight")
    h_be_parTZerovsAll = df_fit.Histo1D(("h_be_parTZerovsAll", "b_{e} ParTZerovsAll;score;Events", 60, 0.0, 1.0), "topreco_be_ParTZerovsAll", "analysis_weight")
    h_be_parTPosvsNeg = df_fit.Histo1D(("h_be_parTPosvsNeg", "b_{e} ParTPosvsNeg;score;Events", 60, 0.0, 1.0), "topreco_be_ParTPosvsNeg", "analysis_weight")
    h2_mu_charge_vs_bmu_charge_score = df_fit.Histo2D(
        ("h2_mu_charge_vs_bmu_charge_score", "Muon charge vs b_{#mu} charge score;charge^{#mu};b_{#mu} charge score", 3, -1.5, 1.5, 20, 0.0, 1.0),
        "mu0_charge",
        "topreco_bmu_charge_score",
        "analysis_weight",
    )
    h2_el_charge_vs_be_charge_score = df_fit.Histo2D(
        ("h2_el_charge_vs_be_charge_score", "Electron charge vs b_{e} charge score;charge^{e};b_{e} charge score", 3, -1.5, 1.5, 20, 0.0, 1.0),
        "el0_charge",
        "topreco_be_charge_score",
        "analysis_weight",
    )

    # Top-mass category overlays by hadron flavour combinations of (bmu, be):
    # b=5, c=4, l=0 with unordered pairs.
    df_cat_bb = df_fit.Filter("topreco_bmu_hflav==5 && topreco_be_hflav==5", "bb")
    df_cat_bc = df_fit.Filter("(topreco_bmu_hflav==5 && topreco_be_hflav==4) || (topreco_bmu_hflav==4 && topreco_be_hflav==5)", "bc")
    df_cat_bl = df_fit.Filter("(topreco_bmu_hflav==5 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==5)", "bl")
    df_cat_cc = df_fit.Filter("topreco_bmu_hflav==4 && topreco_be_hflav==4", "cc")
    df_cat_cl = df_fit.Filter("(topreco_bmu_hflav==4 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==4)", "cl")
    df_cat_ll = df_fit.Filter("topreco_bmu_hflav==0 && topreco_be_hflav==0", "ll")

    h_topmu_bb = df_cat_bb.Histo1D(("h_topmu_bb", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight")
    h_topmu_bc = df_cat_bc.Histo1D(("h_topmu_bc", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight")
    h_topmu_bl = df_cat_bl.Histo1D(("h_topmu_bl", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight")
    h_topmu_cc = df_cat_cc.Histo1D(("h_topmu_cc", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight")
    h_topmu_cl = df_cat_cl.Histo1D(("h_topmu_cl", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight")
    h_topmu_ll = df_cat_ll.Histo1D(("h_topmu_ll", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight")

    h_tope_bb = df_cat_bb.Histo1D(("h_tope_bb", "", 80, 100, 300), "topreco_t2_mass", "analysis_weight")
    h_tope_bc = df_cat_bc.Histo1D(("h_tope_bc", "", 80, 100, 300), "topreco_t2_mass", "analysis_weight")
    h_tope_bl = df_cat_bl.Histo1D(("h_tope_bl", "", 80, 100, 300), "topreco_t2_mass", "analysis_weight")
    h_tope_cc = df_cat_cc.Histo1D(("h_tope_cc", "", 80, 100, 300), "topreco_t2_mass", "analysis_weight")
    h_tope_cl = df_cat_cl.Histo1D(("h_tope_cl", "", 80, 100, 300), "topreco_t2_mass", "analysis_weight")
    h_tope_ll = df_cat_ll.Histo1D(("h_tope_ll", "", 80, 100, 300), "topreco_t2_mass", "analysis_weight")

    # Triptych for top(mu) mass composition in Njets = 2,3,4.
    def make_topmu_category_hists(df_in, prefix):
        df_bb_loc = df_in.Filter("topreco_bmu_hflav==5 && topreco_be_hflav==5", "bb")
        df_bc_loc = df_in.Filter("(topreco_bmu_hflav==5 && topreco_be_hflav==4) || (topreco_bmu_hflav==4 && topreco_be_hflav==5)", "bc")
        df_bl_loc = df_in.Filter("(topreco_bmu_hflav==5 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==5)", "bl")
        df_cc_loc = df_in.Filter("topreco_bmu_hflav==4 && topreco_be_hflav==4", "cc")
        df_cl_loc = df_in.Filter("(topreco_bmu_hflav==4 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==4)", "cl")
        df_ll_loc = df_in.Filter("topreco_bmu_hflav==0 && topreco_be_hflav==0", "ll")
        return {
            "all": df_in.Histo1D((f"h_{prefix}_all", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
            "bb": df_bb_loc.Histo1D((f"h_{prefix}_bb", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
            "bc": df_bc_loc.Histo1D((f"h_{prefix}_bc", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
            "bl": df_bl_loc.Histo1D((f"h_{prefix}_bl", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
            "cc": df_cc_loc.Histo1D((f"h_{prefix}_cc", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
            "cl": df_cl_loc.Histo1D((f"h_{prefix}_cl", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
            "ll": df_ll_loc.Histo1D((f"h_{prefix}_ll", "", 80, 100, 300), "topreco_t1_mass", "analysis_weight"),
        }

    topmu_2j = make_topmu_category_hists(df_fit.Filter("nJetSel == 2", "nJetSel==2"), "topmu_2j")
    topmu_3j = make_topmu_category_hists(df_fit.Filter("nJetSel == 3", "nJetSel==3"), "topmu_3j")
    topmu_4j = make_topmu_category_hists(df_fit.Filter("nJetSel == 4", "nJetSel==4"), "topmu_4j")
    topmu_2j_be03 = make_topmu_category_hists(df_fit.Filter("nJetSel == 2 && topreco_be_btagAlt > 0.3", "nJetSel==2, be btag>0.3"), "topmu_2j_be03")
    topmu_3j_be03 = make_topmu_category_hists(df_fit.Filter("nJetSel == 3 && topreco_be_btagAlt > 0.3", "nJetSel==3, be btag>0.3"), "topmu_3j_be03")
    topmu_4j_be03 = make_topmu_category_hists(df_fit.Filter("nJetSel == 4 && topreco_be_btagAlt > 0.3", "nJetSel==4, be btag>0.3"), "topmu_4j_be03")

    # Trigger event loop once and save outputs.
    histos = [
        h_mu_pt,
        h_mu_eta,
        h_mu_phi,
        h_mu_id,
        h_mu_charge,
        h_el_pt,
        h_el_eta,
        h_el_phi,
        h_el_id,
        h_el_charge,
        h_njet,
        h_njet_hflav5,
        h_jet_pt,
        h_jet_eta,
        h_jet_phi,
        h_jet_flav,
        h_chi2,
        h_topmu,
        h_tope,
        h_wmu,
        h_we,
        h_tt,
        h_nu_pt,
        h_nub_pt,
        h_met_res,
        h_bmu_pt,
        h_be_pt,
        h_bmu_eta,
        h_be_eta,
        h_bmu_hflav,
        h_be_hflav,
        h_bmu_btag,
        h_be_btag,
        h_bmu_charge_score,
        h_be_charge_score,
        h_bmu_charge_score_muplus,
        h_bmu_charge_score_muminus,
        h_be_charge_score_muplus,
        h_be_charge_score_muminus,
        h_bmu_charge_score_bmu_hflav5,
        h_be_charge_score_bmu_hflav5,
        h_bmu_charge_score_2j_be03,
        h_bmu_charge_score_3j_be03,
        h_bmu_charge_score_4j_be03,
        h_bmu_charge_score_2j_be03_bmu_hflav5,
        h_bmu_charge_score_3j_be03_bmu_hflav5,
        h_bmu_charge_score_4j_be03_bmu_hflav5,
        h_bmu_charge_score_2j_be03_muplus,
        h_bmu_charge_score_2j_be03_muminus,
        h_bmu_charge_score_3j_be03_muplus,
        h_bmu_charge_score_3j_be03_muminus,
        h_bmu_charge_score_4j_be03_muplus,
        h_bmu_charge_score_4j_be03_muminus,
        h_bmu_charge_k03,
        h_bmu_charge_k05,
        h_bmu_charge_k10,
        h_bmu_charge_k20,
        h_be_charge_k03,
        h_be_charge_k05,
        h_be_charge_k10,
        h_be_charge_k20,
        h_bmu_parTNegvsAll,
        h_bmu_parTPosvsAll,
        h_bmu_parTZerovsAll,
        h_bmu_parTPosvsNeg,
        h_be_parTNegvsAll,
        h_be_parTPosvsAll,
        h_be_parTZerovsAll,
        h_be_parTPosvsNeg,
        h2_mu_charge_vs_bmu_charge_score,
        h2_el_charge_vs_be_charge_score,
        h_topmu_bb,
        h_topmu_bc,
        h_topmu_bl,
        h_topmu_cc,
        h_topmu_cl,
        h_topmu_ll,
        h_tope_bb,
        h_tope_bc,
        h_tope_bl,
        h_tope_cc,
        h_tope_cl,
        h_tope_ll,
        topmu_2j["all"],
        topmu_2j["bb"],
        topmu_2j["bc"],
        topmu_2j["bl"],
        topmu_2j["cc"],
        topmu_2j["cl"],
        topmu_2j["ll"],
        topmu_3j["all"],
        topmu_3j["bb"],
        topmu_3j["bc"],
        topmu_3j["bl"],
        topmu_3j["cc"],
        topmu_3j["cl"],
        topmu_3j["ll"],
        topmu_4j["all"],
        topmu_4j["bb"],
        topmu_4j["bc"],
        topmu_4j["bl"],
        topmu_4j["cc"],
        topmu_4j["cl"],
        topmu_4j["ll"],
        topmu_2j_be03["all"],
        topmu_2j_be03["bb"],
        topmu_2j_be03["bc"],
        topmu_2j_be03["bl"],
        topmu_2j_be03["cc"],
        topmu_2j_be03["cl"],
        topmu_2j_be03["ll"],
        topmu_3j_be03["all"],
        topmu_3j_be03["bb"],
        topmu_3j_be03["bc"],
        topmu_3j_be03["bl"],
        topmu_3j_be03["cc"],
        topmu_3j_be03["cl"],
        topmu_3j_be03["ll"],
        topmu_4j_be03["all"],
        topmu_4j_be03["bb"],
        topmu_4j_be03["bc"],
        topmu_4j_be03["bl"],
        topmu_4j_be03["cc"],
        topmu_4j_be03["cl"],
        topmu_4j_be03["ll"],
    ]
    ROOT.RDF.RunGraphs(histos)

    save_hist(h_mu_pt.GetValue(), args.outdir, "mu_pt", xtitle="p_{T}^{#mu} [GeV]")
    save_hist(h_mu_eta.GetValue(), args.outdir, "mu_eta", xtitle="#eta^{#mu}")
    save_hist(h_mu_phi.GetValue(), args.outdir, "mu_phi", xtitle="#phi^{#mu}")
    save_hist(h_mu_id.GetValue(), args.outdir, "mu_id", xtitle="ID bin")
    save_hist(h_mu_charge.GetValue(), args.outdir, "mu_charge", xtitle="charge^{#mu}")

    save_hist(h_el_pt.GetValue(), args.outdir, "el_pt", xtitle="p_{T}^{e} [GeV]")
    save_hist(h_el_eta.GetValue(), args.outdir, "el_eta", xtitle="#eta^{e}")
    save_hist(h_el_phi.GetValue(), args.outdir, "el_phi", xtitle="#phi^{e}")
    save_hist(h_el_id.GetValue(), args.outdir, "el_id", xtitle="cutBased")
    save_hist(h_el_charge.GetValue(), args.outdir, "el_charge", xtitle="charge^{e}")

    save_hist(h_njet.GetValue(), args.outdir, "njet", xtitle="N_{jets}")
    save_hist(h_njet_hflav5.GetValue(), args.outdir, "njet_hflav5", xtitle="N_{jets}(hflav=5)")
    save_hist(h_jet_pt.GetValue(), args.outdir, "jet_pt", xtitle="p_{T}^{jet} [GeV]", ytitle="Jets")
    save_hist(h_jet_eta.GetValue(), args.outdir, "jet_eta", xtitle="#eta^{jet}", ytitle="Jets")
    save_hist(h_jet_phi.GetValue(), args.outdir, "jet_phi", xtitle="#phi^{jet}", ytitle="Jets")
    save_hist(h_jet_flav.GetValue(), args.outdir, "jet_hadron_flavor", xtitle="hadron flavour", ytitle="Jets")

    save_hist(h_chi2.GetValue(), args.outdir, "topfit_chi2", xtitle="#chi^{2}")
    save_hist(h_topmu.GetValue(), args.outdir, "topmu_mass", xtitle="m_{top,#mu} [GeV]")
    save_hist(h_tope.GetValue(), args.outdir, "tope_mass", xtitle="m_{top,e} [GeV]")
    save_hist(h_wmu.GetValue(), args.outdir, "wmu_mass", xtitle="m_{W,#mu} [GeV]")
    save_hist(h_we.GetValue(), args.outdir, "we_mass", xtitle="m_{W,e} [GeV]")
    save_hist(h_tt.GetValue(), args.outdir, "ttbar_mass", xtitle="m_{t#bar{t}} [GeV]")
    save_hist(h_nu_pt.GetValue(), args.outdir, "nu_pt", xtitle="p_{T}^{#nu} [GeV]")
    save_hist(h_nub_pt.GetValue(), args.outdir, "nubar_pt", xtitle="p_{T}^{#bar{#nu}} [GeV]")
    save_hist(h_met_res.GetValue(), args.outdir, "met_residual", xtitle="|#Delta MET| [GeV]")
    save_hist(h_bmu_pt.GetValue(), args.outdir, "topfit_bmu_pt", xtitle="p_{T}^{b_{#mu}} [GeV]")
    save_hist(h_be_pt.GetValue(), args.outdir, "topfit_be_pt", xtitle="p_{T}^{b_{e}} [GeV]")
    save_hist(h_bmu_eta.GetValue(), args.outdir, "topfit_bmu_eta", xtitle="#eta^{b_{#mu}}")
    save_hist(h_be_eta.GetValue(), args.outdir, "topfit_be_eta", xtitle="#eta^{b_{e}}")
    save_hist(h_bmu_hflav.GetValue(), args.outdir, "topfit_bmu_hadron_flav", xtitle="hadron flavour")
    save_hist(h_be_hflav.GetValue(), args.outdir, "topfit_be_hadron_flav", xtitle="hadron flavour")
    save_hist(h_bmu_btag.GetValue(), args.outdir, "topfit_bmu_btagDeepB", xtitle="DeepB")
    save_hist(h_be_btag.GetValue(), args.outdir, "topfit_be_btagDeepB", xtitle="DeepB")
    save_hist(h_bmu_charge_score.GetValue(), args.outdir, "topfit_bmu_charge_score", xtitle="charge score")
    save_hist(h_be_charge_score.GetValue(), args.outdir, "topfit_be_charge_score", xtitle="charge score")
    save_hist(h_bmu_charge_k03.GetValue(), args.outdir, "topfit_bmu_charge_k03", xtitle="charge_{k=0.3}")
    save_hist(h_bmu_charge_k05.GetValue(), args.outdir, "topfit_bmu_charge_k05", xtitle="charge_{k=0.5}")
    save_hist(h_bmu_charge_k10.GetValue(), args.outdir, "topfit_bmu_charge_k10", xtitle="charge_{k=1.0}")
    save_hist(h_bmu_charge_k20.GetValue(), args.outdir, "topfit_bmu_charge_k20", xtitle="charge_{k=2.0}")
    save_hist(h_be_charge_k03.GetValue(), args.outdir, "topfit_be_charge_k03", xtitle="charge_{k=0.3}")
    save_hist(h_be_charge_k05.GetValue(), args.outdir, "topfit_be_charge_k05", xtitle="charge_{k=0.5}")
    save_hist(h_be_charge_k10.GetValue(), args.outdir, "topfit_be_charge_k10", xtitle="charge_{k=1.0}")
    save_hist(h_be_charge_k20.GetValue(), args.outdir, "topfit_be_charge_k20", xtitle="charge_{k=2.0}")
    save_hist(h_bmu_parTNegvsAll.GetValue(), args.outdir, "topfit_bmu_ParTNegvsAll", xtitle="score")
    save_hist(h_bmu_parTPosvsAll.GetValue(), args.outdir, "topfit_bmu_ParTPosvsAll", xtitle="score")
    save_hist(h_bmu_parTZerovsAll.GetValue(), args.outdir, "topfit_bmu_ParTZerovsAll", xtitle="score")
    save_hist(h_bmu_parTPosvsNeg.GetValue(), args.outdir, "topfit_bmu_ParTPosvsNeg", xtitle="score")
    save_hist(h_be_parTNegvsAll.GetValue(), args.outdir, "topfit_be_ParTNegvsAll", xtitle="score")
    save_hist(h_be_parTPosvsAll.GetValue(), args.outdir, "topfit_be_ParTPosvsAll", xtitle="score")
    save_hist(h_be_parTZerovsAll.GetValue(), args.outdir, "topfit_be_ParTZerovsAll", xtitle="score")
    save_hist(h_be_parTPosvsNeg.GetValue(), args.outdir, "topfit_be_ParTPosvsNeg", xtitle="score")
    save_hist2d(
        h2_mu_charge_vs_bmu_charge_score.GetValue(),
        args.outdir,
        "mu_charge_vs_bmu_charge_score",
        xtitle="charge^{#mu}",
        ytitle="b_{#mu} charge score",
    )
    save_hist2d(
        h2_el_charge_vs_be_charge_score.GetValue(),
        args.outdir,
        "el_charge_vs_be_charge_score",
        xtitle="charge^{e}",
        ytitle="b_{e} charge score",
    )
    save_hist_stack(
        [
            (h_topmu_bb.GetValue(), "bb"),
            (h_topmu_bc.GetValue(), "bc"),
            (h_topmu_bl.GetValue(), "bl"),
            (h_topmu_cc.GetValue(), "cc"),
            (h_topmu_cl.GetValue(), "cl"),
            (h_topmu_ll.GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav",
        title="Top(#mu) mass by (b_{#mu},b_{e}) hadron flavour",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=h_topmu.GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (h_tope_bb.GetValue(), "bb"),
            (h_tope_bc.GetValue(), "bc"),
            (h_tope_bl.GetValue(), "bl"),
            (h_tope_cc.GetValue(), "cc"),
            (h_tope_cl.GetValue(), "cl"),
            (h_tope_ll.GetValue(), "ll"),
        ],
        args.outdir,
        "tope_mass_stack_hflav",
        title="Top(e) mass by (b_{#mu},b_{e}) hadron flavour",
        xtitle="m_{top,e} [GeV]",
        overlay_hist=h_tope.GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (topmu_2j["bb"].GetValue(), "bb"),
            (topmu_2j["bc"].GetValue(), "bc"),
            (topmu_2j["bl"].GetValue(), "bl"),
            (topmu_2j["cc"].GetValue(), "cc"),
            (topmu_2j["cl"].GetValue(), "cl"),
            (topmu_2j["ll"].GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav_njet2",
        title="Top(#mu) mass by (b_{#mu},b_{e}) hadron flavour, N_{jets}==2",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=topmu_2j["all"].GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (topmu_3j["bb"].GetValue(), "bb"),
            (topmu_3j["bc"].GetValue(), "bc"),
            (topmu_3j["bl"].GetValue(), "bl"),
            (topmu_3j["cc"].GetValue(), "cc"),
            (topmu_3j["cl"].GetValue(), "cl"),
            (topmu_3j["ll"].GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav_njet3",
        title="Top(#mu) mass by (b_{#mu},b_{e}) hadron flavour, N_{jets}==3",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=topmu_3j["all"].GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (topmu_4j["bb"].GetValue(), "bb"),
            (topmu_4j["bc"].GetValue(), "bc"),
            (topmu_4j["bl"].GetValue(), "bl"),
            (topmu_4j["cc"].GetValue(), "cc"),
            (topmu_4j["cl"].GetValue(), "cl"),
            (topmu_4j["ll"].GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav_njet4",
        title="Top(#mu) mass by (b_{#mu},b_{e}) hadron flavour, N_{jets}==4",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=topmu_4j["all"].GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (topmu_2j_be03["bb"].GetValue(), "bb"),
            (topmu_2j_be03["bc"].GetValue(), "bc"),
            (topmu_2j_be03["bl"].GetValue(), "bl"),
            (topmu_2j_be03["cc"].GetValue(), "cc"),
            (topmu_2j_be03["cl"].GetValue(), "cl"),
            (topmu_2j_be03["ll"].GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav_njet2_beBtagGt03",
        title=f"Top(#mu) mass by (b_{{#mu}},b_{{e}}) hadron flavour, N_{{jets}}==2, b_{{e}} {be_btag_label}>0.3",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=topmu_2j_be03["all"].GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (topmu_3j_be03["bb"].GetValue(), "bb"),
            (topmu_3j_be03["bc"].GetValue(), "bc"),
            (topmu_3j_be03["bl"].GetValue(), "bl"),
            (topmu_3j_be03["cc"].GetValue(), "cc"),
            (topmu_3j_be03["cl"].GetValue(), "cl"),
            (topmu_3j_be03["ll"].GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav_njet3_beBtagGt03",
        title=f"Top(#mu) mass by (b_{{#mu}},b_{{e}}) hadron flavour, N_{{jets}}==3, b_{{e}} {be_btag_label}>0.3",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=topmu_3j_be03["all"].GetValue(),
        overlay_label="all",
    )
    save_hist_stack(
        [
            (topmu_4j_be03["bb"].GetValue(), "bb"),
            (topmu_4j_be03["bc"].GetValue(), "bc"),
            (topmu_4j_be03["bl"].GetValue(), "bl"),
            (topmu_4j_be03["cc"].GetValue(), "cc"),
            (topmu_4j_be03["cl"].GetValue(), "cl"),
            (topmu_4j_be03["ll"].GetValue(), "ll"),
        ],
        args.outdir,
        "topmu_mass_stack_hflav_njet4_beBtagGt03",
        title=f"Top(#mu) mass by (b_{{#mu}},b_{{e}}) hadron flavour, N_{{jets}}==4, b_{{e}} {be_btag_label}>0.3",
        xtitle="m_{top,#mu} [GeV]",
        overlay_hist=topmu_4j_be03["all"].GetValue(),
        overlay_label="all",
    )
    save_hist_overlay(
        h_bmu_charge_score.GetValue(),
        h_be_charge_score.GetValue(),
        args.outdir,
        "bmu_be_charge_score_overlay",
        "b_{#mu} charge score",
        "b_{e} charge score",
        xtitle="charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_muplus.GetValue(),
        h_bmu_charge_score_muminus.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_mu_charge",
        "#mu charge = +1",
        "#mu charge = -1",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_be_charge_score_muplus.GetValue(),
        h_be_charge_score_muminus.GetValue(),
        args.outdir,
        "be_charge_score_overlay_mu_charge",
        "#mu charge = +1",
        "#mu charge = -1",
        xtitle="b_{e} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score.GetValue(),
        h_bmu_charge_score_bmu_hflav5.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_bmu_hflav5",
        "All events",
        "b_{#mu} hflav = 5",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_2j_be03_muplus.GetValue(),
        h_bmu_charge_score_2j_be03_muminus.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_mu_charge_njet2_beBtagGt03",
        "#mu charge = +1",
        "#mu charge = -1",
        title=f"b_{{#mu}} charge score, N_{{jets}}=2, b_{{e}} {be_btag_label}>0.3",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_3j_be03_muplus.GetValue(),
        h_bmu_charge_score_3j_be03_muminus.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_mu_charge_njet3_beBtagGt03",
        "#mu charge = +1",
        "#mu charge = -1",
        title=f"b_{{#mu}} charge score, N_{{jets}}=3, b_{{e}} {be_btag_label}>0.3",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_4j_be03_muplus.GetValue(),
        h_bmu_charge_score_4j_be03_muminus.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_mu_charge_njet4_beBtagGt03",
        "#mu charge = +1",
        "#mu charge = -1",
        title=f"b_{{#mu}} charge score, N_{{jets}}=4, b_{{e}} {be_btag_label}>0.3",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_be_charge_score.GetValue(),
        h_be_charge_score_bmu_hflav5.GetValue(),
        args.outdir,
        "be_charge_score_overlay_bmu_hflav5",
        "All events",
        "b_{#mu} hflav = 5",
        xtitle="b_{e} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_2j_be03.GetValue(),
        h_bmu_charge_score_2j_be03_bmu_hflav5.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_bmu_hflav5_njet2_beBtagGt03",
        "All events",
        "b_{#mu} hflav = 5",
        title=f"b_{{#mu}} charge score, N_{{jets}}=2, b_{{e}} {be_btag_label}>0.3",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_3j_be03.GetValue(),
        h_bmu_charge_score_3j_be03_bmu_hflav5.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_bmu_hflav5_njet3_beBtagGt03",
        "All events",
        "b_{#mu} hflav = 5",
        title=f"b_{{#mu}} charge score, N_{{jets}}=3, b_{{e}} {be_btag_label}>0.3",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )
    save_hist_overlay(
        h_bmu_charge_score_4j_be03.GetValue(),
        h_bmu_charge_score_4j_be03_bmu_hflav5.GetValue(),
        args.outdir,
        "bmu_charge_score_overlay_bmu_hflav5_njet4_beBtagGt03",
        "All events",
        "b_{#mu} hflav = 5",
        title=f"b_{{#mu}} charge score, N_{{jets}}=4, b_{{e}} {be_btag_label}>0.3",
        xtitle="b_{#mu} charge score",
        ytitle="Events",
    )

    out_root = ROOT.TFile.Open(os.path.join(args.outdir, "ttbar_reco_plots.root"), "RECREATE")
    for h in [
        h_mu_pt.GetValue(),
        h_mu_eta.GetValue(),
        h_mu_phi.GetValue(),
        h_mu_id.GetValue(),
        h_mu_charge.GetValue(),
        h_el_pt.GetValue(),
        h_el_eta.GetValue(),
        h_el_phi.GetValue(),
        h_el_id.GetValue(),
        h_el_charge.GetValue(),
        h_njet.GetValue(),
        h_njet_hflav5.GetValue(),
        h_jet_pt.GetValue(),
        h_jet_eta.GetValue(),
        h_jet_phi.GetValue(),
        h_jet_flav.GetValue(),
        h_chi2.GetValue(),
        h_topmu.GetValue(),
        h_tope.GetValue(),
        h_wmu.GetValue(),
        h_we.GetValue(),
        h_tt.GetValue(),
        h_nu_pt.GetValue(),
        h_nub_pt.GetValue(),
        h_met_res.GetValue(),
        h_bmu_pt.GetValue(),
        h_be_pt.GetValue(),
        h_bmu_eta.GetValue(),
        h_be_eta.GetValue(),
        h_bmu_hflav.GetValue(),
        h_be_hflav.GetValue(),
        h_bmu_btag.GetValue(),
        h_be_btag.GetValue(),
        h_bmu_charge_score.GetValue(),
        h_be_charge_score.GetValue(),
        h_bmu_charge_score_muplus.GetValue(),
        h_bmu_charge_score_muminus.GetValue(),
        h_be_charge_score_muplus.GetValue(),
        h_be_charge_score_muminus.GetValue(),
        h_bmu_charge_score_bmu_hflav5.GetValue(),
        h_be_charge_score_bmu_hflav5.GetValue(),
        h_bmu_charge_score_2j_be03.GetValue(),
        h_bmu_charge_score_3j_be03.GetValue(),
        h_bmu_charge_score_4j_be03.GetValue(),
        h_bmu_charge_score_2j_be03_bmu_hflav5.GetValue(),
        h_bmu_charge_score_3j_be03_bmu_hflav5.GetValue(),
        h_bmu_charge_score_4j_be03_bmu_hflav5.GetValue(),
        h_bmu_charge_score_2j_be03_muplus.GetValue(),
        h_bmu_charge_score_2j_be03_muminus.GetValue(),
        h_bmu_charge_score_3j_be03_muplus.GetValue(),
        h_bmu_charge_score_3j_be03_muminus.GetValue(),
        h_bmu_charge_score_4j_be03_muplus.GetValue(),
        h_bmu_charge_score_4j_be03_muminus.GetValue(),
        h_bmu_charge_k03.GetValue(),
        h_bmu_charge_k05.GetValue(),
        h_bmu_charge_k10.GetValue(),
        h_bmu_charge_k20.GetValue(),
        h_be_charge_k03.GetValue(),
        h_be_charge_k05.GetValue(),
        h_be_charge_k10.GetValue(),
        h_be_charge_k20.GetValue(),
        h_bmu_parTNegvsAll.GetValue(),
        h_bmu_parTPosvsAll.GetValue(),
        h_bmu_parTZerovsAll.GetValue(),
        h_bmu_parTPosvsNeg.GetValue(),
        h_be_parTNegvsAll.GetValue(),
        h_be_parTPosvsAll.GetValue(),
        h_be_parTZerovsAll.GetValue(),
        h_be_parTPosvsNeg.GetValue(),
        h2_mu_charge_vs_bmu_charge_score.GetValue(),
        h2_el_charge_vs_be_charge_score.GetValue(),
        h_topmu_bb.GetValue(),
        h_topmu_bc.GetValue(),
        h_topmu_bl.GetValue(),
        h_topmu_cc.GetValue(),
        h_topmu_cl.GetValue(),
        h_topmu_ll.GetValue(),
        h_tope_bb.GetValue(),
        h_tope_bc.GetValue(),
        h_tope_bl.GetValue(),
        h_tope_cc.GetValue(),
        h_tope_cl.GetValue(),
        h_tope_ll.GetValue(),
    ]:
        h.Write()
    out_root.Close()

    print(f"[plot_ttbar_reco] Wrote plots and ROOT file to: {args.outdir}")


if __name__ == "__main__":
    main()
