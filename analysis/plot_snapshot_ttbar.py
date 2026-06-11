#!/usr/bin/env python3
import argparse
import os

import ROOT


def enable_mt(threads: int) -> None:
    if threads and threads > 0:
        ROOT.ROOT.EnableImplicitMT(threads)
    else:
        ROOT.ROOT.EnableImplicitMT()


def _unit_normalize(h) -> None:
    integ = h.Integral(0, h.GetNbinsX() + 1)
    if integ > 0:
        h.Scale(1.0 / integ)


def save_hist(h, outdir: str, name: str, normalize: bool = False) -> None:
    if normalize:
        _unit_normalize(h)
    c = ROOT.TCanvas(f"c_{name}", "", 900, 700)
    h.SetLineWidth(2)
    h.SetLineColor(ROOT.kAzure + 1)
    h.Draw("hist")
    h.GetYaxis().SetTitle("A.U." if normalize else "Events")
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def save_bpair_category_hist(h, outdir: str, name: str, normalize: bool = False) -> None:
    if normalize:
        _unit_normalize(h)
    c = ROOT.TCanvas(f"c_{name}", "", 1000, 700)
    h.SetLineWidth(2)
    h.SetLineColor(ROOT.kAzure + 1)
    h.SetFillColor(ROOT.kAzure - 9)
    h.SetFillStyle(1001)
    xax = h.GetXaxis()
    xax.SetBinLabel(1, "bb")
    xax.SetBinLabel(2, "bc+cb")
    xax.SetBinLabel(3, "cc")
    xax.SetBinLabel(4, "bl+lb")
    xax.SetBinLabel(5, "cl+lc")
    xax.SetBinLabel(6, "ll")
    xax.SetLabelSize(0.045)
    h.Draw("hist")
    h.GetYaxis().SetTitle("A.U." if normalize else "Events")
    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def save_stacked_categories(hmap, outdir: str, name: str, xtitle: str, normalize: bool = False) -> None:
    c = ROOT.TCanvas(f"c_{name}", "", 1000, 800)
    st = ROOT.THStack(f"st_{name}", f";{xtitle};Events")
    order = ["ll", "cl", "bl", "cc", "bc", "bb"]
    labels = {
        "bb": "bb",
        "bc": "bc+cb",
        "cc": "cc",
        "bl": "bl+lb",
        "cl": "cl+lc",
        "ll": "ll",
    }
    colors = {
        "bb": ROOT.kAzure + 1,
        "bc": ROOT.kBlue - 7,
        "cc": ROOT.kCyan - 3,
        "bl": ROOT.kOrange + 7,
        "cl": ROOT.kGreen + 2,
        "ll": ROOT.kGray + 1,
    }

    htot = None
    for k in order:
        h = hmap[k]
        h.SetFillColor(colors[k])
        h.SetLineColor(ROOT.kBlack)
        h.SetLineWidth(1)
        st.Add(h)
        if htot is None:
            htot = h.Clone(f"{name}_all")
            htot.SetDirectory(0)
        else:
            htot.Add(h)

    if normalize and htot and htot.Integral(0, htot.GetNbinsX() + 1) > 0:
        scale = 1.0 / htot.Integral(0, htot.GetNbinsX() + 1)
        for k in order:
            hmap[k].Scale(scale)
        htot.Scale(scale)

    st.Draw("hist")
    st.SetMaximum(st.GetMaximum() * 1.35 if st.GetMaximum() > 0 else 1.0)
    st.GetYaxis().SetTitle("A.U." if normalize else "Events")
    htot.SetFillStyle(0)
    htot.SetLineColor(ROOT.kBlack)
    htot.SetLineWidth(3)
    htot.Draw("hist same")

    leg = ROOT.TLegend(0.62, 0.55, 0.90, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    leg.AddEntry(htot, "all", "l")
    for k in ["bb", "bc", "cc", "bl", "cl", "ll"]:
        leg.AddEntry(hmap[k], labels[k], "f")
    leg.Draw()

    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot directly from a snapshot tree (no redefinitions).")
    parser.add_argument("--input", required=True, help="Input snapshot ROOT file")
    parser.add_argument("--tree", default="Events", help="Tree name")
    parser.add_argument("--outdir", default="analysis/plots_snapshot_ttbar", help="Output directory")
    parser.add_argument("--threads", type=int, default=0, help="ROOT implicit MT threads (0=ROOT default)")
    parser.add_argument("--mu-id-cut", choices=["none", "loose", "medium", "tight"], default="none")
    parser.add_argument("--normalize", action="store_true", help="Normalize each plotted histogram to unit area.")
    parser.add_argument("--bmu-deepb-min", type=float, default=None, help="Optional cut: topreco_bmu_btagDeepB > value")
    parser.add_argument("--mu-charge", choices=["all", "plus", "minus"], default="all", help="Optional muon charge split")
    parser.add_argument("--skip-flavor-pair-plots", action="store_true", help="Skip hflav pair-composition plots/stacks.")
    parser.add_argument("--force-flavor-pair-plots", action="store_true", help="Force flavour-pair plots even for data-like inputs.")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    enable_mt(args.threads)

    df = ROOT.RDataFrame(args.tree, args.input)
    cols = {str(c) for c in df.GetColumnNames()}

    # Basic lepton presence filter if snapshot has these columns.
    if "mu0_pt" in cols and "el0_pt" in cols:
        df = df.Filter("mu0_pt > 0 && el0_pt > 0", "mu+e present")

    # Optional muon ID cut, only if the corresponding branch exists.
    if args.mu_id_cut != "none":
        req = {
            "loose": "mu0_isLoose",
            "medium": "mu0_isMedium",
            "tight": "mu0_isTight",
        }[args.mu_id_cut]
        if req in cols:
            df = df.Filter(f"{req} > 0", f"muon {args.mu_id_cut} ID")
        else:
            print(f"[plot_snapshot_ttbar] Requested --mu-id-cut {args.mu_id_cut}, but '{req}' is missing. Skipping this cut.")

    # Optional bmu DeepB cut.
    if args.bmu_deepb_min is not None:
        if "topreco_bmu_btagDeepB" not in cols:
            if "topreco_b1_index" in cols and "jet_btagDeepB" in cols:
                df = df.Define(
                    "topreco_bmu_btagDeepB",
                    "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_btagDeepB.size()) ? jet_btagDeepB[topreco_b1_index] : -1.f",
                )
                cols.add("topreco_bmu_btagDeepB")
            else:
                raise RuntimeError(
                    "Requested --bmu-deepb-min but could not find 'topreco_bmu_btagDeepB' "
                    "and cannot derive it from top index + jet_btagDeepB."
                )
        df = df.Filter(f"topreco_bmu_btagDeepB > {float(args.bmu_deepb_min)}", f"bmu DeepB > {float(args.bmu_deepb_min)}")

    # Optional muon charge split.
    if args.mu_charge != "all":
        if "mu0_charge" not in cols:
            raise RuntimeError("Requested --mu-charge split but 'mu0_charge' is missing in input.")
        if args.mu_charge == "plus":
            df = df.Filter("mu0_charge > 0", "muon charge > 0")
        elif args.mu_charge == "minus":
            df = df.Filter("mu0_charge < 0", "muon charge < 0")

    specs = [
        ("mu0_pt", ("h_mu0_pt", "Muon p_{T};p_{T}^{#mu} [GeV];Events", 80, 0, 400), "mu0_pt"),
        ("mu0_eta", ("h_mu0_eta", "Muon #eta;#eta^{#mu};Events", 60, -3, 3), "mu0_eta"),
        ("mu0_phi", ("h_mu0_phi", "Muon #phi;#phi^{#mu};Events", 64, -3.2, 3.2), "mu0_phi"),
        ("mu0_charge", ("h_mu0_charge", "Muon charge;charge^{#mu};Events", 3, -1.5, 1.5), "mu0_charge"),
        ("el0_pt", ("h_el0_pt", "Electron p_{T};p_{T}^{e} [GeV];Events", 80, 0, 400), "el0_pt"),
        ("el0_eta", ("h_el0_eta", "Electron #eta;#eta^{e};Events", 60, -3, 3), "el0_eta"),
        ("el0_phi", ("h_el0_phi", "Electron #phi;#phi^{e};Events", 64, -3.2, 3.2), "el0_phi"),
        ("el0_charge", ("h_el0_charge", "Electron charge;charge^{e};Events", 3, -1.5, 1.5), "el0_charge"),
        ("nJetSel", ("h_nJetSel", "Selected jet multiplicity;N_{jets};Events", 10, -0.5, 9.5), "nJetSel"),
        ("met_pt", ("h_met_pt", "MET;MET [GeV];Events", 80, 0, 400), "met_pt"),
        ("topreco_chi2", ("h_topreco_chi2", "Top fit #chi^{2};#chi^{2};Events", 80, 0, 80), "topreco_chi2"),
        ("topreco_met_residual", ("h_topreco_met_residual", "|#Delta MET|;|#Delta MET| [GeV];Events", 80, 0, 120), "topreco_met_residual"),
        ("topreco_t1_mass", ("h_topreco_t1_mass", "Top(#mu) mass;m_{top,#mu} [GeV];Events", 80, 100, 300), "topreco_t1_mass"),
        ("topreco_t2_mass", ("h_topreco_t2_mass", "Top(e) mass;m_{top,e} [GeV];Events", 80, 100, 300), "topreco_t2_mass"),
        ("topreco_w1_mass", ("h_topreco_w1_mass", "W(#mu) mass;m_{W,#mu} [GeV];Events", 80, 0, 160), "topreco_w1_mass"),
        ("topreco_w2_mass", ("h_topreco_w2_mass", "W(e) mass;m_{W,e} [GeV];Events", 80, 0, 160), "topreco_w2_mass"),
        ("topreco_ttbar_mass", ("h_topreco_ttbar_mass", "t#bar{t} mass;m_{t#bar{t}} [GeV];Events", 100, 200, 1500), "topreco_ttbar_mass"),
        ("topreco_bmu_btagDeepB", ("h_topreco_bmu_btagDeepB", "b_{#mu} DeepB;DeepB;Events", 60, 0, 1), "topreco_bmu_btagDeepB"),
        ("topreco_be_btagDeepB", ("h_topreco_be_btagDeepB", "b_{e} DeepB;DeepB;Events", 60, 0, 1), "topreco_be_btagDeepB"),
        ("topreco_bmu_charge_score", ("h_topreco_bmu_charge_score", "b_{#mu} charge score;score;Events", 20, 0, 1), "topreco_bmu_charge_score"),
        ("topreco_be_charge_score", ("h_topreco_be_charge_score", "b_{e} charge score;score;Events", 20, 0, 1), "topreco_be_charge_score"),
    ]

    hist_ptrs = []
    names = []
    for needed_col, model, var in specs:
        if needed_col not in cols:
            continue
        if "analysis_weight" in cols:
            h = df.Histo1D(model, var, "analysis_weight")
        else:
            h = df.Histo1D(model, var)
        hist_ptrs.append(h)
        names.append(model[0])

    print(f"[plot_snapshot_ttbar] Materializing {len(hist_ptrs)} histograms...")
    for hptr, hname in zip(hist_ptrs, names):
        h = hptr.GetValue()
        save_hist(h, args.outdir, hname, normalize=args.normalize)

    input_base = os.path.basename(args.input).lower()
    auto_data_like = input_base.startswith("data") or "data_snapshot" in input_base
    skip_flavor = (args.skip_flavor_pair_plots or auto_data_like) and not args.force_flavor_pair_plots
    if skip_flavor:
        print("[plot_snapshot_ttbar] Skipping flavour-pair plots by request.")
        print(f"[plot_snapshot_ttbar] Done. Plots in: {args.outdir}")
        return

    df_cat = df
    cols_cat = set(cols)
    if "topreco_bmu_hflav" not in cols_cat and "topreco_b1_index" in cols_cat and "jet_hflav" in cols_cat:
        df_cat = df_cat.Define(
            "topreco_bmu_hflav",
            "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_hflav.size()) ? jet_hflav[topreco_b1_index] : -99",
        )
        cols_cat.add("topreco_bmu_hflav")
    if "topreco_be_hflav" not in cols_cat and "topreco_b2_index" in cols_cat and "jet_hflav" in cols_cat:
        df_cat = df_cat.Define(
            "topreco_be_hflav",
            "(topreco_b2_index>=0 && topreco_b2_index<(int)jet_hflav.size()) ? jet_hflav[topreco_b2_index] : -99",
        )
        cols_cat.add("topreco_be_hflav")

    if "topreco_bmu_hflav" in cols_cat and "topreco_be_hflav" in cols_cat:
        cat_defs = {
            "bb": "(topreco_bmu_hflav==5 && topreco_be_hflav==5)",
            "bc": "((topreco_bmu_hflav==5 && topreco_be_hflav==4) || (topreco_bmu_hflav==4 && topreco_be_hflav==5))",
            "cc": "(topreco_bmu_hflav==4 && topreco_be_hflav==4)",
            "bl": "((topreco_bmu_hflav==5 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==5))",
            "cl": "((topreco_bmu_hflav==4 && topreco_be_hflav==0) || (topreco_bmu_hflav==0 && topreco_be_hflav==4))",
            "ll": "(topreco_bmu_hflav==0 && topreco_be_hflav==0)",
        }

        # Build a category histogram explicitly to avoid JIT parser issues with nested ternaries.
        h_cat = ROOT.TH1D("h_bpair_hflavcat", "b-candidate flavour composition;category;Events", 6, -0.5, 5.5)
        h_cat.SetDirectory(0)
        ordered = ["bb", "bc", "cc", "bl", "cl", "ll"]
        for i, key in enumerate(ordered, start=1):
            dfi = df_cat.Filter(cat_defs[key], key)
            if "analysis_weight" in cols_cat:
                val = float(dfi.Sum("analysis_weight").GetValue())
            else:
                val = float(dfi.Count().GetValue())
            h_cat.SetBinContent(i, val)
        save_bpair_category_hist(h_cat, args.outdir, "h_bpair_hflavcat", normalize=args.normalize)
        print("[plot_snapshot_ttbar] Added h_bpair_hflavcat plot.")

        # Stacked flavour-composition overlays for all key reco distributions.
        stack_specs = [
            ("topreco_t1_mass", ("h_stk_topreco_t1_mass", "Top(#mu) mass;m_{top,#mu} [GeV];Events", 80, 100, 300), "m_{top,#mu} [GeV]"),
            ("topreco_t2_mass", ("h_stk_topreco_t2_mass", "Top(e) mass;m_{top,e} [GeV];Events", 80, 100, 300), "m_{top,e} [GeV]"),
            ("topreco_w1_mass", ("h_stk_topreco_w1_mass", "W(#mu) mass;m_{W,#mu} [GeV];Events", 80, 0, 160), "m_{W,#mu} [GeV]"),
            ("topreco_w2_mass", ("h_stk_topreco_w2_mass", "W(e) mass;m_{W,e} [GeV];Events", 80, 0, 160), "m_{W,e} [GeV]"),
            ("topreco_chi2", ("h_stk_topreco_chi2", "Top fit #chi^{2};#chi^{2};Events", 80, 0, 80), "#chi^{2}"),
            ("topreco_met_residual", ("h_stk_topreco_met_residual", "|#Delta MET|;|#Delta MET| [GeV];Events", 80, 0, 120), "|#Delta MET| [GeV]"),
            ("topreco_bmu_btagDeepB", ("h_stk_topreco_bmu_btagDeepB", "b_{#mu} DeepB;DeepB;Events", 60, 0, 1), "DeepB(b_{#mu})"),
            ("topreco_be_btagDeepB", ("h_stk_topreco_be_btagDeepB", "b_{e} DeepB;DeepB;Events", 60, 0, 1), "DeepB(b_{e})"),
            ("topreco_bmu_charge_score", ("h_stk_topreco_bmu_charge_score", "b_{#mu} charge score;score;Events", 20, 0, 1), "charge score(b_{#mu})"),
            ("topreco_be_charge_score", ("h_stk_topreco_be_charge_score", "b_{e} charge score;score;Events", 20, 0, 1), "charge score(b_{e})"),
            ("mu0_pt", ("h_stk_mu0_pt", "Muon p_{T};p_{T}^{#mu} [GeV];Events", 80, 0, 400), "p_{T}^{#mu} [GeV]"),
            ("el0_pt", ("h_stk_el0_pt", "Electron p_{T};p_{T}^{e} [GeV];Events", 80, 0, 400), "p_{T}^{e} [GeV]"),
            ("met_pt", ("h_stk_met_pt", "MET;MET [GeV];Events", 80, 0, 400), "MET [GeV]"),
            ("nJetSel", ("h_stk_nJetSel", "Selected jet multiplicity;N_{jets};Events", 10, -0.5, 9.5), "N_{jets}"),
        ]
        for var, model, xtitle in stack_specs:
            if var not in cols_cat:
                continue
            hmap = {}
            for key, sel in cat_defs.items():
                dfi = df_cat.Filter(sel, key)
                if "analysis_weight" in cols_cat:
                    hp = dfi.Histo1D(model, var, "analysis_weight")
                else:
                    hp = dfi.Histo1D(model, var)
                h = hp.GetValue().Clone(f"{model[0]}_{key}")
                h.SetDirectory(0)
                hmap[key] = h
            save_stacked_categories(hmap, args.outdir, model[0], xtitle, normalize=args.normalize)
        print("[plot_snapshot_ttbar] Added stacked flavour-composition plots.")
    else:
        print("[plot_snapshot_ttbar] Missing topreco_bmu_hflav/topreco_be_hflav, skipping flavour-category plot.")

    print(f"[plot_snapshot_ttbar] Done. Plots in: {args.outdir}")


if __name__ == "__main__":
    main()
