#!/usr/bin/env python3
import argparse
import os

import ROOT


def get_hist(tfile, name):
    h = tfile.Get(name)
    if not h:
        return None
    h = h.Clone(f"{name}_{tfile.GetName().split('/')[-1]}")
    h.SetDirectory(0)
    return h


def style_data(h):
    h.SetMarkerStyle(20)
    h.SetMarkerSize(1.0)
    h.SetLineColor(ROOT.kBlack)
    h.SetMarkerColor(ROOT.kBlack)


def style_mc(h, color):
    h.SetFillColor(color)
    h.SetLineColor(ROOT.kBlack)
    h.SetLineWidth(1)


def make_ratio(data_h, mc_h):
    ratio = data_h.Clone(f"ratio_{data_h.GetName()}")
    ratio.SetDirectory(0)
    ratio.Divide(mc_h)
    ratio.SetMarkerStyle(20)
    ratio.SetMarkerSize(0.9)
    ratio.SetLineColor(ROOT.kBlack)
    ratio.SetMarkerColor(ROOT.kBlack)
    return ratio


def draw_one(name, h_data, h_qcd, h_vjets, h_ttsemi, h_ttdilep, outdir, lumi_label):
    mc_only = (name == "bpair_hflavcat")
    c = ROOT.TCanvas(f"c_{name}", "", 900, 900)
    if mc_only:
        pad1 = ROOT.TPad("pad1", "", 0.0, 0.00, 1.0, 1.0)
        pad2 = None
        pad1.SetBottomMargin(0.12)
    else:
        pad1 = ROOT.TPad("pad1", "", 0.0, 0.30, 1.0, 1.0)
        pad2 = ROOT.TPad("pad2", "", 0.0, 0.00, 1.0, 0.30)
        pad1.SetBottomMargin(0.02)
        pad2.SetTopMargin(0.02)
        pad2.SetBottomMargin(0.35)
    pad1.Draw()
    if pad2:
        pad2.Draw()

    pad1.cd()

    # Colors requested: ttbar blue shades, qcd yellow, vjets red.
    style_mc(h_ttdilep, ROOT.kAzure + 1)
    style_mc(h_ttsemi, ROOT.kBlue - 7)
    style_mc(h_qcd, ROOT.kYellow + 1)
    style_mc(h_vjets, ROOT.kRed + 1)
    style_data(h_data)

    stack = ROOT.THStack(f"st_{name}", h_data.GetTitle())
    # Bottom->top order
    stack.Add(h_qcd)
    stack.Add(h_vjets)
    stack.Add(h_ttsemi)
    stack.Add(h_ttdilep)
    stack.Draw("hist")

    mc_sum = h_qcd.Clone(f"mc_{name}")
    mc_sum.Add(h_vjets)
    mc_sum.Add(h_ttsemi)
    mc_sum.Add(h_ttdilep)

    ymax = stack.GetMaximum() * 1.35 if mc_only else max(stack.GetMaximum(), h_data.GetMaximum()) * 1.35
    stack.SetMaximum(ymax)
    stack.GetYaxis().SetTitle("Events")
    stack.GetYaxis().SetTitleSize(0.045)
    stack.GetYaxis().SetLabelSize(0.04)
    if name == "bpair_hflavcat":
        xax = stack.GetXaxis()
        xax.SetBinLabel(1, "bb")
        xax.SetBinLabel(2, "bc+cb")
        xax.SetBinLabel(3, "cc")
        xax.SetBinLabel(4, "bl+lb")
        xax.SetBinLabel(5, "cl+lc")
        xax.SetBinLabel(6, "ll")
        xax.SetLabelSize(0.045)

    if not mc_only:
        h_data.Draw("e1 same")

    leg = ROOT.TLegend(0.62, 0.58, 0.90, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    if not mc_only:
        leg.AddEntry(h_data, "Data", "lep")
    leg.AddEntry(h_ttdilep, "t#bar{t} dileptonic", "f")
    leg.AddEntry(h_ttsemi, "t#bar{t} semileptonic", "f")
    leg.AddEntry(h_qcd, "QCD", "f")
    leg.AddEntry(h_vjets, "V+jets", "f")
    leg.Draw()

    cms = ROOT.TLatex()
    cms.SetNDC(True)
    cms.SetTextFont(62)
    cms.SetTextSize(0.05)
    cms.DrawLatex(0.12, 0.92, "CMS")
    cms.SetTextFont(52)
    cms.SetTextSize(0.04)
    cms.DrawLatex(0.20, 0.92, "Internal")

    lumi = ROOT.TLatex()
    lumi.SetNDC(True)
    lumi.SetTextFont(42)
    lumi.SetTextSize(0.04)
    lumi.SetTextAlign(31)
    lumi.DrawLatex(0.95, 0.92, lumi_label)

    if not mc_only:
        pad2.cd()
        ratio = make_ratio(h_data, mc_sum)
        ratio.GetYaxis().SetTitle("Data/MC")
        ratio.GetYaxis().SetNdivisions(505)
        ratio.GetYaxis().SetTitleSize(0.10)
        ratio.GetYaxis().SetLabelSize(0.09)
        ratio.GetYaxis().SetTitleOffset(0.45)
        ratio.GetXaxis().SetTitle(h_data.GetXaxis().GetTitle())
        ratio.GetXaxis().SetTitleSize(0.12)
        ratio.GetXaxis().SetLabelSize(0.10)
        ratio.SetMinimum(0.4)
        ratio.SetMaximum(1.6)
        ratio.Draw("e1")

        line = ROOT.TLine(ratio.GetXaxis().GetXmin(), 1.0, ratio.GetXaxis().GetXmax(), 1.0)
        line.SetLineStyle(2)
        line.Draw("same")

    c.SaveAs(os.path.join(outdir, f"{name}_data_mc.png"))
    c.Close()


def main():
    parser = argparse.ArgumentParser(description="Plot data/MC from per-process histogram ROOT files.")
    parser.add_argument("--indir", default="analysis/hists_by_process_prodv1_sel", help="Directory with data.root/qcd.root/vjets.root/ttbar_*.root")
    parser.add_argument("--outdir", default="analysis/plots_data_mc", help="Output plot directory")
    parser.add_argument("--lumi-label", default="Run 3 (2024)", help="Top-right label")
    parser.add_argument("--hists", nargs="*", default=[], help="Optional subset of histogram names")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)

    paths = {
        "data": os.path.join(args.indir, "data.root"),
        "qcd": os.path.join(args.indir, "qcd.root"),
        "vjets": os.path.join(args.indir, "vjets.root"),
        "ttsemi": os.path.join(args.indir, "ttbar_semileptonic.root"),
        "ttdilep": os.path.join(args.indir, "ttbar_dileptonic.root"),
    }

    files = {}
    for key, p in paths.items():
        tf = ROOT.TFile.Open(p, "READ")
        if not tf or tf.IsZombie():
            raise RuntimeError(f"Could not open {p}")
        files[key] = tf

    if args.hists:
        hist_names = args.hists
    else:
        hist_names = []
        for k in files["data"].GetListOfKeys():
            obj = k.ReadObj()
            if obj.InheritsFrom("TH1"):
                hist_names.append(k.GetName())

    print(f"[plot_data_mc] plotting {len(hist_names)} histograms")
    for name in hist_names:
        h_data = get_hist(files["data"], name)
        h_qcd = get_hist(files["qcd"], name)
        h_vjets = get_hist(files["vjets"], name)
        h_ttsemi = get_hist(files["ttsemi"], name)
        h_ttdilep = get_hist(files["ttdilep"], name)
        if not all([h_data, h_qcd, h_vjets, h_ttsemi, h_ttdilep]):
            print(f"[plot_data_mc] skip {name}: missing in one process")
            continue
        print(f"[plot_data_mc] {name}")
        draw_one(name, h_data, h_qcd, h_vjets, h_ttsemi, h_ttdilep, args.outdir, args.lumi_label)

    for tf in files.values():
        tf.Close()
    print(f"[plot_data_mc] done: {args.outdir}")


if __name__ == "__main__":
    main()
