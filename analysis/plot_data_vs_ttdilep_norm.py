#!/usr/bin/env python3
import argparse
import os

import ROOT


def clone_hist(tf, name, suffix):
    h = tf.Get(name)
    if not h:
        return None
    hc = h.Clone(f"{name}_{suffix}")
    hc.SetDirectory(0)
    return hc


def normalize(h):
    integ = h.Integral(0, h.GetNbinsX() + 1)
    if integ > 0:
        h.Scale(1.0 / integ)


def draw_one(name, h_data, h_mc, outdir, label):
    c = ROOT.TCanvas(f"c_{name}", "", 900, 900)
    p1 = ROOT.TPad("p1", "", 0.0, 0.30, 1.0, 1.0)
    p2 = ROOT.TPad("p2", "", 0.0, 0.00, 1.0, 0.30)
    p1.SetBottomMargin(0.02)
    p2.SetTopMargin(0.02)
    p2.SetBottomMargin(0.35)
    p1.Draw()
    p2.Draw()

    p1.cd()
    h_mc.SetLineColor(ROOT.kAzure + 1)
    h_mc.SetLineWidth(3)
    h_mc.SetFillStyle(0)
    h_mc.GetYaxis().SetTitle("A.U.")
    h_mc.SetMaximum(max(h_mc.GetMaximum(), h_data.GetMaximum()) * 1.35)
    h_mc.Draw("hist")

    h_data.SetMarkerStyle(20)
    h_data.SetMarkerSize(1.0)
    h_data.SetMarkerColor(ROOT.kBlack)
    h_data.SetLineColor(ROOT.kBlack)
    h_data.Draw("e1 same")

    leg = ROOT.TLegend(0.62, 0.72, 0.90, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    leg.AddEntry(h_data, "Data (norm)", "lep")
    leg.AddEntry(h_mc, "t#bar{t} dileptonic (norm)", "l")
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
    lumi.DrawLatex(0.95, 0.92, label)

    p2.cd()
    r = h_data.Clone(f"r_{name}")
    r.SetDirectory(0)
    r.Divide(h_mc)
    r.SetMarkerStyle(20)
    r.SetMarkerSize(0.9)
    r.SetMarkerColor(ROOT.kBlack)
    r.SetLineColor(ROOT.kBlack)
    r.GetYaxis().SetTitle("Data/MC")
    r.GetYaxis().SetNdivisions(505)
    r.GetYaxis().SetTitleSize(0.10)
    r.GetYaxis().SetLabelSize(0.09)
    r.GetYaxis().SetTitleOffset(0.45)
    r.GetXaxis().SetTitle(h_data.GetXaxis().GetTitle())
    r.GetXaxis().SetTitleSize(0.12)
    r.GetXaxis().SetLabelSize(0.10)
    r.SetMinimum(0.4)
    r.SetMaximum(1.6)
    r.Draw("e1")

    l = ROOT.TLine(r.GetXaxis().GetXmin(), 1.0, r.GetXaxis().GetXmax(), 1.0)
    l.SetLineStyle(2)
    l.Draw("same")

    c.SaveAs(os.path.join(outdir, f"{name}_data_vs_ttdilep_norm.png"))
    c.Close()


def main():
    ap = argparse.ArgumentParser(description="Overlay normalized Data vs ttbar-dileptonic with ratio")
    ap.add_argument("--indir", default="analysis/hists_by_process_prodv1_sel")
    ap.add_argument("--outdir", default="analysis/plots_data_vs_ttdilep_norm")
    ap.add_argument("--label", default="Run 3 (2024)")
    ap.add_argument("--hists", nargs="*", default=[])
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    ROOT.gROOT.SetBatch(True)
    ROOT.gStyle.SetOptStat(0)

    f_data = ROOT.TFile.Open(os.path.join(args.indir, "data.root"), "READ")
    f_mc = ROOT.TFile.Open(os.path.join(args.indir, "ttbar_dileptonic.root"), "READ")
    if not f_data or f_data.IsZombie():
        raise RuntimeError("Could not open data.root")
    if not f_mc or f_mc.IsZombie():
        raise RuntimeError("Could not open ttbar_dileptonic.root")

    if args.hists:
        hist_names = args.hists
    else:
        hist_names = []
        for k in f_data.GetListOfKeys():
            o = k.ReadObj()
            if o.InheritsFrom("TH1") and f_mc.Get(k.GetName()):
                hist_names.append(k.GetName())

    print(f"[plot_data_vs_ttdilep_norm] plotting {len(hist_names)} histograms")
    for n in hist_names:
        hd = clone_hist(f_data, n, "data")
        hm = clone_hist(f_mc, n, "mc")
        if not hd or not hm:
            continue
        normalize(hd)
        normalize(hm)
        if hm.Integral(0, hm.GetNbinsX()+1) <= 0:
            print(f"[plot_data_vs_ttdilep_norm] skip {n}: empty MC")
            continue
        draw_one(n, hd, hm, args.outdir, args.label)

    f_data.Close()
    f_mc.Close()
    print(f"[plot_data_vs_ttdilep_norm] done: {args.outdir}")


if __name__ == "__main__":
    main()
