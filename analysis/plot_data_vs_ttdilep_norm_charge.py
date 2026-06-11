#!/usr/bin/env python3
import argparse
import os

import ROOT


def draw_one(name, h_data, h_mc, outdir, label):
    c = ROOT.TCanvas(f"c_{name}", "", 900, 900)
    p1 = ROOT.TPad("p1", "", 0.0, 0.30, 1.0, 1.0)
    p2 = ROOT.TPad("p2", "", 0.0, 0.00, 1.0, 0.30)
    p1.SetBottomMargin(0.02)
    p2.SetTopMargin(0.02)
    p2.SetBottomMargin(0.35)
    p1.Draw(); p2.Draw()

    p1.cd()
    h_mc.SetLineColor(ROOT.kAzure + 1)
    h_mc.SetLineWidth(3)
    h_mc.SetFillStyle(0)
    h_mc.GetYaxis().SetTitle("A.U.")
    h_mc.SetMaximum(max(h_mc.GetMaximum(), h_data.GetMaximum()) * 1.35 if max(h_mc.GetMaximum(), h_data.GetMaximum()) > 0 else 1.0)
    h_mc.Draw("hist")

    h_data.SetMarkerStyle(20)
    h_data.SetMarkerSize(1.0)
    h_data.SetMarkerColor(ROOT.kBlack)
    h_data.SetLineColor(ROOT.kBlack)
    h_data.Draw("e1 same")

    leg = ROOT.TLegend(0.60, 0.72, 0.90, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    leg.AddEntry(h_data, "Data (norm)", "lep")
    leg.AddEntry(h_mc, "t#bar{t} dileptonic (norm)", "l")
    leg.Draw()

    cms = ROOT.TLatex(); cms.SetNDC(True)
    cms.SetTextFont(62); cms.SetTextSize(0.05); cms.DrawLatex(0.12, 0.92, "CMS")
    cms.SetTextFont(52); cms.SetTextSize(0.04); cms.DrawLatex(0.20, 0.92, "Internal")
    lum = ROOT.TLatex(); lum.SetNDC(True)
    lum.SetTextFont(42); lum.SetTextSize(0.04); lum.SetTextAlign(31); lum.DrawLatex(0.95, 0.92, label)

    p2.cd()
    r = h_data.Clone(f"r_{name}")
    r.SetDirectory(0)
    r.Divide(h_mc)
    r.SetMarkerStyle(20); r.SetMarkerSize(0.9)
    r.GetYaxis().SetTitle("Data/MC")
    r.GetYaxis().SetNdivisions(505)
    r.GetYaxis().SetTitleSize(0.10)
    r.GetYaxis().SetLabelSize(0.09)
    r.GetYaxis().SetTitleOffset(0.45)
    r.GetXaxis().SetTitle(h_data.GetXaxis().GetTitle())
    r.GetXaxis().SetTitleSize(0.12)
    r.GetXaxis().SetLabelSize(0.10)
    r.SetMinimum(0.4); r.SetMaximum(1.6)
    r.Draw("e1")
    l = ROOT.TLine(r.GetXaxis().GetXmin(), 1.0, r.GetXaxis().GetXmax(), 1.0)
    l.SetLineStyle(2); l.Draw("same")

    c.SaveAs(os.path.join(outdir, f"{name}.png"))
    c.Close()


def norm(h):
    i = h.Integral(0, h.GetNbinsX() + 1)
    if i > 0:
        h.Scale(1.0 / i)


def book_h(df, var, model, use_weight):
    return df.Histo1D(model, var, "analysis_weight") if use_weight else df.Histo1D(model, var)


def main():
    ap = argparse.ArgumentParser(description="Data vs ttbar-dileptonic normalized overlays for all/mu+/mu-")
    ap.add_argument("--data-snapshot", default="analysis/hists_by_process_prodv1_sel/data_snapshot.root")
    ap.add_argument("--mc-snapshot", default="analysis/hists_by_process_prodv1_sel/ttbar_dileptonic_snapshot.root")
    ap.add_argument("--tree", default="Events")
    ap.add_argument("--outdir", default="analysis/plots_data_vs_ttdilep_norm_charge")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--label", default="Run 3 (2024)")
    ap.add_argument("--bmu-deepb-min", type=float, default=0.3)
    ap.add_argument("--with-bmu-pt-bins", action="store_true", help="Also make mu+/mu- plots split in b(mu)-jet pT bins.")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)
    ROOT.ROOT.EnableImplicitMT(args.threads if args.threads > 0 else 0)

    df_data = ROOT.RDataFrame(args.tree, args.data_snapshot)
    df_mc = ROOT.RDataFrame(args.tree, args.mc_snapshot)

    # Common baseline
    for dname, d in [("data", df_data), ("mc", df_mc)]:
        pass

    # Apply bmu deepB cut if branch present
    cols_data_pre = {str(c) for c in df_data.GetColumnNames()}
    cols_mc_pre = {str(c) for c in df_mc.GetColumnNames()}
    if "topreco_bmu_btagDeepB" in cols_data_pre:
        df_data = df_data.Filter(
            f"topreco_bmu_btagDeepB > {args.bmu_deepb_min}",
            f"bmu DeepB > {args.bmu_deepb_min}",
        )
        print(f"[plot_data_vs_ttdilep_norm_charge] Applied data cut: topreco_bmu_btagDeepB > {args.bmu_deepb_min}")
    else:
        print("[plot_data_vs_ttdilep_norm_charge] Data missing topreco_bmu_btagDeepB, no bmu DeepB cut applied.")

    if "topreco_bmu_btagDeepB" in cols_mc_pre:
        df_mc = df_mc.Filter(
            f"topreco_bmu_btagDeepB > {args.bmu_deepb_min}",
            f"bmu DeepB > {args.bmu_deepb_min}",
        )
        print(f"[plot_data_vs_ttdilep_norm_charge] Applied MC cut: topreco_bmu_btagDeepB > {args.bmu_deepb_min}")
    else:
        print("[plot_data_vs_ttdilep_norm_charge] MC missing topreco_bmu_btagDeepB, no bmu DeepB cut applied.")

    specs = [
        ("mu_pt", "mu0_pt", ("h_mu_pt", ";p_{T}^{#mu} [GeV];A.U.", 50, 0, 250)),
        ("el_pt", "el0_pt", ("h_el_pt", ";p_{T}^{e} [GeV];A.U.", 50, 0, 250)),
        ("met_pt", "met_pt", ("h_met_pt", ";MET [GeV];A.U.", 60, 0, 300)),
        ("topmu_mass", "topreco_t1_mass", ("h_topmu_mass", ";m_{top,#mu} [GeV];A.U.", 60, 100, 320)),
        ("tope_mass", "topreco_t2_mass", ("h_tope_mass", ";m_{top,e} [GeV];A.U.", 60, 100, 320)),
        ("wmu_mass", "topreco_w1_mass", ("h_wmu_mass", ";m_{W,#mu} [GeV];A.U.", 50, 0, 180)),
        ("we_mass", "topreco_w2_mass", ("h_we_mass", ";m_{W,e} [GeV];A.U.", 50, 0, 180)),
        ("chi2", "topreco_chi2", ("h_chi2", ";#chi^{2};A.U.", 60, 0, 120)),
        ("bmu_deepb", "topreco_bmu_btagDeepB", ("h_bmu_deepb", ";DeepB(b_{#mu});A.U.", 40, 0, 1)),
        ("be_deepb", "topreco_be_btagDeepB", ("h_be_deepb", ";DeepB(b_{e});A.U.", 40, 0, 1)),
        ("bmu_charge_score", "topreco_bmu_charge_score", ("h_bmu_charge_score", ";b_{#mu} charge score;A.U.", 20, 0, 1)),
        ("be_charge_score", "topreco_be_charge_score", ("h_be_charge_score", ";b_{e} charge score;A.U.", 20, 0, 1)),
    ]

    bmu_pt_specs = [
        ("10to20", "topreco_bmu_pt >= 10 && topreco_bmu_pt < 20"),
        ("20to30", "topreco_bmu_pt >= 20 && topreco_bmu_pt < 30"),
        ("30to50", "topreco_bmu_pt >= 30 && topreco_bmu_pt < 50"),
        ("50to80", "topreco_bmu_pt >= 50 && topreco_bmu_pt < 80"),
        ("80to110", "topreco_bmu_pt >= 80 && topreco_bmu_pt < 110"),
        ("110to150", "topreco_bmu_pt >= 110 && topreco_bmu_pt < 150"),
        ("gt150", "topreco_bmu_pt >= 150"),
    ]

    splits = [
        ("all", "1"),
        ("muplus", "mu0_charge > 0"),
        ("muminus", "mu0_charge < 0"),
    ]

    cols_data = {str(c) for c in df_data.GetColumnNames()}
    cols_mc = {str(c) for c in df_mc.GetColumnNames()}
    use_w_data = "analysis_weight" in cols_data
    use_w_mc = "analysis_weight" in cols_mc

    for tag, sel in splits:
        od = os.path.join(args.outdir, tag)
        os.makedirs(od, exist_ok=True)
        dfd = df_data.Filter(sel, tag)
        dfm = df_mc.Filter(sel, tag)
        print(f"[plot_data_vs_ttdilep_norm_charge] {tag}")

        for outname, var, model in specs:
            if var not in cols_data or var not in cols_mc:
                continue
            hd = book_h(dfd, var, model, use_w_data).GetValue().Clone(f"{outname}_d_{tag}")
            hm = book_h(dfm, var, model, use_w_mc).GetValue().Clone(f"{outname}_m_{tag}")
            hd.SetDirectory(0); hm.SetDirectory(0)
            norm(hd); norm(hm)
            if hm.Integral(0, hm.GetNbinsX()+1) <= 0:
                continue
            draw_one(f"{outname}_{tag}", hd, hm, od, args.label)

    if args.with_bmu_pt_bins:
        # Derive b(mu) pT if missing.
        if "topreco_bmu_pt" not in cols_data:
            if "topreco_b1_index" in cols_data and "jet_pt" in cols_data:
                df_data = df_data.Define(
                    "topreco_bmu_pt",
                    "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_pt.size()) ? jet_pt[topreco_b1_index] : -1.f",
                )
                cols_data.add("topreco_bmu_pt")
                print("[plot_data_vs_ttdilep_norm_charge] Derived data topreco_bmu_pt from topreco_b1_index + jet_pt")
        if "topreco_bmu_pt" not in cols_mc:
            if "topreco_b1_index" in cols_mc and "jet_pt" in cols_mc:
                df_mc = df_mc.Define(
                    "topreco_bmu_pt",
                    "(topreco_b1_index>=0 && topreco_b1_index<(int)jet_pt.size()) ? jet_pt[topreco_b1_index] : -1.f",
                )
                cols_mc.add("topreco_bmu_pt")
                print("[plot_data_vs_ttdilep_norm_charge] Derived MC topreco_bmu_pt from topreco_b1_index + jet_pt")

        if "topreco_bmu_pt" not in cols_data or "topreco_bmu_pt" not in cols_mc:
            print("[plot_data_vs_ttdilep_norm_charge] Missing topreco_bmu_pt in data or MC even after fallback: skipping bmu pT-binned plots")
        else:
            # only split by muon charge for the pT-binned mode
            for charge_tag, charge_sel in [("muplus", "mu0_charge > 0"), ("muminus", "mu0_charge < 0")]:
                for pt_tag, pt_sel in bmu_pt_specs:
                    sel = f"({charge_sel}) && ({pt_sel})"
                    od = os.path.join(args.outdir, f"{charge_tag}_bmupt_{pt_tag}")
                    os.makedirs(od, exist_ok=True)
                    dfd = df_data.Filter(sel, f"{charge_tag}_{pt_tag}")
                    dfm = df_mc.Filter(sel, f"{charge_tag}_{pt_tag}")
                    print(f"[plot_data_vs_ttdilep_norm_charge] {charge_tag}, bmu pT {pt_tag}")
                    for outname, var, model in specs:
                        if var not in cols_data or var not in cols_mc:
                            continue
                        hd = book_h(dfd, var, model, use_w_data).GetValue().Clone(f"{outname}_d_{charge_tag}_{pt_tag}")
                        hm = book_h(dfm, var, model, use_w_mc).GetValue().Clone(f"{outname}_m_{charge_tag}_{pt_tag}")
                        hd.SetDirectory(0)
                        hm.SetDirectory(0)
                        norm(hd)
                        norm(hm)
                        if hm.Integral(0, hm.GetNbinsX() + 1) <= 0:
                            continue
                        draw_one(
                            f"{outname}_{charge_tag}_bmupt_{pt_tag}",
                            hd,
                            hm,
                            od,
                            f"{args.label}, {charge_tag}, b_{{#mu}} p_{{T}} {pt_tag} GeV",
                        )

    print(f"[plot_data_vs_ttdilep_norm_charge] done: {args.outdir}")


if __name__ == "__main__":
    main()
