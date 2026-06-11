#!/usr/bin/env python3
import argparse
import glob
import os

try:
    import ROOT
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "PyROOT is not available in this shell. Run inside a CMSSW runtime environment "
        "(source /cvmfs/cms.cern.ch/cmsset_default.sh; eval \"$(scram runtime -sh)\")."
    ) from exc

ROOT.gROOT.SetBatch(True)
ROOT.TH1.SetDefaultSumw2(True)


def list_inputs(patterns):
    files = []
    for item in patterns:
        matches = sorted(glob.glob(item))
        if matches:
            files.extend(matches)
        elif os.path.isfile(item):
            files.append(item)
    return sorted(set(files))


def branch_names(tree):
    out = set()
    for br in tree.GetListOfBranches():
        out.add(br.GetName())
    return out


def pick_charge_mode(branch_set):
    if "jet_charge_score" in branch_set:
        return "jet_charge_score"
    if "jet_ParTPosvsNeg" in branch_set:
        return "jet_ParTPosvsNeg"
    if "jet_ParTPosvsAll" in branch_set and "jet_ParTNegvsAll" in branch_set:
        return "jet_ParTPosvsAll_minus_jet_ParTNegvsAll"
    raise RuntimeError("No jet-charge branch found (expected jet_charge_score or ParT branches)")


def as_list(obj):
    return [obj[i] for i in range(len(obj))]


def classify_flavour(hflav):
    ah = abs(int(round(float(hflav))))
    if ah == 5:
        return "b"
    if ah == 4:
        return "c"

    if ah == 0:
        return "light"

    return 'other'


def make_hists(nbins, xmin, xmax):
    hists = {}
    for flav in ("b", "c", "light"):
        title = f"Jet charge score ({flav}-jets);score;Jets"
        hists[flav] = {
            "+": ROOT.TH1F(f"h_{flav}_plus", title, nbins, xmin, xmax),
            "-": ROOT.TH1F(f"h_{flav}_minus", title, nbins, xmin, xmax),
        }
    return hists


def fill_charge_histograms(tree, charge_mode, hists, include_missing):
    used_jets = 0
    for event in tree:
        if not hasattr(event, "jet_pflavCharge") or not hasattr(event, "jet_hflav"):
            continue

        pflav_charge = as_list(event.jet_pflavCharge)
        hflav = as_list(event.jet_hflav)

        if charge_mode == "jet_charge_score":
            charge_score = as_list(event.jet_charge_score)
        elif charge_mode == "jet_ParTPosvsNeg":
            charge_score = as_list(event.jet_ParTPosvsNeg)
        else:
            pos = as_list(event.jet_ParTPosvsAll)
            neg = as_list(event.jet_ParTNegvsAll)
            charge_score = [pos[i] - neg[i] for i in range(min(len(pos), len(neg)))]

        n = min(len(charge_score), len(pflav_charge), len(hflav))
        for i in range(n):
            score = float(charge_score[i])
            if (not include_missing) and score <= -0.99:
                continue
            sign = "+" if float(pflav_charge[i]) > 0 else "-" if float(pflav_charge[i]) < 0 else None
            if sign is None:
                continue
            flav = classify_flavour(hflav[i])
            hists[flav][sign].Fill(score)
            used_jets += 1
    return used_jets


def style_hist(hist, color):
    hist.SetStats(0)
    hist.SetLineColor(color)
    hist.SetMarkerColor(color)
    hist.SetLineWidth(3)
    hist.SetMarkerStyle(20)
    hist.SetMarkerSize(0.9)


def maybe_normalize(hist):
    integral = hist.Integral(0, hist.GetNbinsX() + 1)
    if integral > 0:
        hist.Scale(1.0 / integral)


def draw_flavour_overlay(h_plus, h_minus, outpath, normalize):
    c = ROOT.TCanvas(f"c_{os.path.basename(outpath)}", "", 900, 700)
    hp = h_plus.Clone(f"{h_plus.GetName()}_draw")
    hm = h_minus.Clone(f"{h_minus.GetName()}_draw")
    if normalize:
        maybe_normalize(hp)
        maybe_normalize(hm)
        hp.GetYaxis().SetTitle("A.U.")
    style_hist(hp, ROOT.kBlue + 1)
    style_hist(hm, ROOT.kRed + 1)
    ymax = max(hp.GetMaximum(), hm.GetMaximum(), 1e-6) * 1.25
    hp.SetMaximum(ymax)
    hp.Draw("E1")
    hm.Draw("E1 same")
    leg = ROOT.TLegend(0.62, 0.72, 0.88, 0.88)
    leg.SetBorderSize(0)
    leg.SetFillStyle(0)
    leg.AddEntry(hp, "+ pflavCharge", "l")
    leg.AddEntry(hm, "- pflavCharge", "l")
    leg.Draw()
    c.SaveAs(outpath)


def draw_combined(hists, outpath, normalize):
    c = ROOT.TCanvas("c_charge_by_flavour_combined", "", 1500, 500)
    c.Divide(3, 1)
    for i, flav in enumerate(("b", "c", "light"), start=1):
        c.cd(i)
        hp = hists[flav]["+"].Clone(f"{hists[flav]['+'].GetName()}_comb")
        hm = hists[flav]["-"].Clone(f"{hists[flav]['-'].GetName()}_comb")
        if normalize:
            maybe_normalize(hp)
            maybe_normalize(hm)
            hp.GetYaxis().SetTitle("A.U.")
        style_hist(hp, ROOT.kBlue + 1)
        style_hist(hm, ROOT.kRed + 1)
        ymax = max(hp.GetMaximum(), hm.GetMaximum(), 1e-6) * 1.25
        hp.SetMaximum(ymax)
        hp.SetTitle(f"{flav}-jets;score;{'A.U.' if normalize else 'Jets'}")
        hp.Draw("E1")
        hm.Draw("E1 same")
        leg = ROOT.TLegend(0.58, 0.72, 0.88, 0.88)
        leg.SetBorderSize(0)
        leg.SetFillStyle(0)
        leg.AddEntry(hp, "+ pflavCharge", "l")
        leg.AddEntry(hm, "- pflavCharge", "l")
        leg.Draw()
    c.SaveAs(outpath)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True, help="Input ROOT file(s) or globs")
    parser.add_argument("--tree", default="Events", help="Tree name")
    parser.add_argument("--outdir", default="analysis/plots_charge", help="Output directory")
    parser.add_argument("--nbins", type=int, default=20, help="Number of score bins")
    parser.add_argument("--xmin", type=float, default=0.0, help="Score axis minimum")
    parser.add_argument("--xmax", type=float, default=1.0, help="Score axis maximum")
    parser.add_argument("--normalize", action="store_true", help="Normalize each + / - histogram to unit area")
    parser.add_argument(
        "--include-missing",
        action="store_true",
        help="Include score <= -0.99 entries (default: drop missing-inference sentinel)",
    )
    args = parser.parse_args()

    files = list_inputs(args.input)
    if not files:
        raise RuntimeError("No input ROOT files matched")
    os.makedirs(args.outdir, exist_ok=True)

    hists = make_hists(args.nbins, args.xmin, args.xmax)
    charge_mode = None
    processed_events = 0
    used_jets = 0

    for path in files:
        tf = ROOT.TFile.Open(path)
        if not tf or tf.IsZombie():
            print(f"[plot_charge_by_flavor_sign] Skipping unreadable file: {path}")
            continue
        tree = tf.Get(args.tree)
        if not tree:
            print(f"[plot_charge_by_flavor_sign] Tree '{args.tree}' not found in {path}")
            tf.Close()
            continue
        if charge_mode is None:
            branches = branch_names(tree)
            if "jet_pflavCharge" not in branches:
                raise RuntimeError("Missing required branch: jet_pflavCharge")
            if "jet_hflav" not in branches:
                raise RuntimeError("Missing required branch: jet_hflav")
            charge_mode = pick_charge_mode(branches)
            print(f"[plot_charge_by_flavor_sign] Jet-charge source: {charge_mode}")

        processed_events += tree.GetEntries()
        used_jets += fill_charge_histograms(tree, charge_mode, hists, args.include_missing)
        tf.Close()

    if processed_events == 0:
        raise RuntimeError("No events processed from input files")
    if used_jets == 0:
        raise RuntimeError("No jets passed flavour/sign selection")

    output_root = ROOT.TFile.Open(os.path.join(args.outdir, "charge_by_flavour_sign.root"), "RECREATE")
    for flav in ("b", "c", "light"):
        hists[flav]["+"].Write()
        hists[flav]["-"].Write()
    output_root.Close()

    for flav in ("b", "c", "light"):
        draw_flavour_overlay(
            hists[flav]["+"],
            hists[flav]["-"],
            os.path.join(args.outdir, f"jet_charge_score_{flav}_plus_vs_minus.png"),
            args.normalize,
        )
    draw_combined(hists, os.path.join(args.outdir, "jet_charge_score_plus_vs_minus_combined.png"), args.normalize)

    print(f"[plot_charge_by_flavor_sign] Processed events: {processed_events}")
    print(f"[plot_charge_by_flavor_sign] Filled jets: {used_jets}")
    print(f"[plot_charge_by_flavor_sign] Wrote plots to {args.outdir}")


if __name__ == "__main__":
    main()
