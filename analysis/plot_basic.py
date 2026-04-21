#!/usr/bin/env python3
import argparse
import glob
import math
import os

try:
    import ROOT
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "PyROOT is not available in this shell. Run inside a CMSSW runtime environment "
        "(source /cvmfs/cms.cern.ch/cmsset_default.sh; eval \"$(scram runtime -sh)\")."
    ) from exc

ROOT.gROOT.SetBatch(True)


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
    if "jet_pflavCharge" in branch_set:
        return "jet_pflavCharge"
    return "none"


def as_list(obj):
    return [obj[i] for i in range(len(obj))]


def save_hist(hist, outdir, name, draw_opt="hist"):
    c = ROOT.TCanvas(f"c_{name}", f"c_{name}", 900, 700)
    hist.Draw(draw_opt)
    c.SaveAs(os.path.join(outdir, f"{name}.png"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True, help="Input ROOT file(s) or globs")
    parser.add_argument("--tree", default="Events", help="Tree name")
    parser.add_argument("--outdir", default="analysis/plots", help="Output directory")
    args = parser.parse_args()

    files = list_inputs(args.input)
    if not files:
        raise RuntimeError("No input ROOT files matched")

    os.makedirs(args.outdir, exist_ok=True)

    h_lep_pt = ROOT.TH1F("h_lep_pt", "Selected lepton p_{T};p_{T} [GeV];Events", 60, 0, 300)
    h_jet_pt = ROOT.TH1F("h_jet_pt", "Selected jets p_{T};p_{T} [GeV];Jets", 80, 0, 400)
    h_jet_flav = ROOT.TH1F("h_jet_flav", "Jet hadron flavour;hadronFlavour;Jets", 16, -0.5, 15.5)
    h_jet_charge = ROOT.TH1F("h_jet_charge", "Jet charge score;score;Jets", 80, -2.0, 2.0)
    h_top_proxy = ROOT.TH1F("h_top_proxy", "Top-mass proxy;m_{proxy} [GeV];Events", 80, 0, 400)
    h_njets = ROOT.TH1F("h_njets", "nJetSel;nJetSel;Events", 12, -0.5, 11.5)
    h_nlep = ROOT.TH1F("h_nlep", "nLepSel (mu+e);nLepSel;Events", 6, -0.5, 5.5)

    h_trig_den = ROOT.TH1F("h_trig_den", "Trigger denominator;Lepton p_{T} [GeV];Events", 40, 0, 200)
    h_trig_num = ROOT.TH1F("h_trig_num", "Trigger numerator;Lepton p_{T} [GeV];Events", 40, 0, 200)

    charge_mode = "none"
    seen_events = 0

    for path in files:
        tf = ROOT.TFile.Open(path)
        if not tf or tf.IsZombie():
            print(f"[plot_basic] Skipping unreadable file: {path}")
            continue
        tree = tf.Get(args.tree)
        if not tree:
            print(f"[plot_basic] Tree '{args.tree}' not found in {path}")
            tf.Close()
            continue

        branches = branch_names(tree)
        if charge_mode == "none":
            charge_mode = pick_charge_mode(branches)
            print(f"[plot_basic] Jet-charge source: {charge_mode}")

        for event in tree:
            seen_events += 1
            nlep = int(event.nMuonSel) + int(event.nElectronSel)
            h_njets.Fill(int(event.nJetSel))
            h_nlep.Fill(nlep)

            if nlep > 0:
                lep_pt = float(event.lepton_pt)
                h_lep_pt.Fill(lep_pt)
                h_trig_den.Fill(lep_pt)
                if bool(event.pass_hlt):
                    h_trig_num.Fill(lep_pt)

            jet_pt = as_list(event.jet_pt)
            jet_eta = as_list(event.jet_eta)
            jet_phi = as_list(event.jet_phi)
            jet_mass = as_list(event.jet_mass)

            jet_flav = as_list(event.jet_hflav) if hasattr(event, "jet_hflav") else []

            for i, pt in enumerate(jet_pt):
                h_jet_pt.Fill(pt)
                if i < len(jet_flav):
                    h_jet_flav.Fill(jet_flav[i])

            if charge_mode == "jet_charge_score" and hasattr(event, "jet_charge_score"):
                for val in as_list(event.jet_charge_score):
                    h_jet_charge.Fill(val)
            elif charge_mode == "jet_ParTPosvsNeg" and hasattr(event, "jet_ParTPosvsNeg"):
                for val in as_list(event.jet_ParTPosvsNeg):
                    h_jet_charge.Fill(val)
            elif charge_mode == "jet_ParTPosvsAll_minus_jet_ParTNegvsAll":
                pos = as_list(event.jet_ParTPosvsAll)
                neg = as_list(event.jet_ParTNegvsAll)
                for i in range(min(len(pos), len(neg))):
                    h_jet_charge.Fill(pos[i] - neg[i])
            elif charge_mode == "jet_pflavCharge" and hasattr(event, "jet_pflavCharge"):
                for val in as_list(event.jet_pflavCharge):
                    h_jet_charge.Fill(val)

            if hasattr(event, "top_mass_proxy") and float(event.top_mass_proxy) > 0:
                h_top_proxy.Fill(float(event.top_mass_proxy))
            elif nlep > 0 and len(jet_pt) > 0:
                lep = ROOT.TLorentzVector()
                lep.SetPtEtaPhiM(float(event.lepton_pt), float(event.lepton_eta), float(event.lepton_phi), float(event.lepton_mass))
                j0 = ROOT.TLorentzVector()
                j0.SetPtEtaPhiM(float(jet_pt[0]), float(jet_eta[0]), float(jet_phi[0]), float(jet_mass[0]))
                met = ROOT.TLorentzVector()
                met.SetPtEtaPhiM(float(event.met_pt), 0.0, float(event.met_phi), 0.0)
                h_top_proxy.Fill((lep + j0 + met).M())

        tf.Close()

    if seen_events == 0:
        raise RuntimeError("No events processed from input files")

    eff = ROOT.TEfficiency(h_trig_num, h_trig_den)

    output_root = ROOT.TFile.Open(os.path.join(args.outdir, "basic_plots.root"), "RECREATE")
    for obj in [h_lep_pt, h_jet_pt, h_jet_flav, h_jet_charge, h_top_proxy, h_njets, h_nlep, h_trig_den, h_trig_num, eff]:
        obj.Write()
    output_root.Close()

    save_hist(h_lep_pt, args.outdir, "lepton_pt")
    save_hist(h_jet_pt, args.outdir, "jet_pt")
    save_hist(h_jet_flav, args.outdir, "jet_flavour")
    save_hist(h_jet_charge, args.outdir, "jet_charge_score")
    save_hist(h_top_proxy, args.outdir, "top_mass_proxy")
    save_hist(h_njets, args.outdir, "debug_njets")
    save_hist(h_nlep, args.outdir, "debug_nlep")

    c_eff = ROOT.TCanvas("c_trigger_eff", "c_trigger_eff", 900, 700)
    eff.SetTitle("Trigger efficiency;Lepton p_{T} [GeV];Efficiency")
    eff.Draw("AP")
    c_eff.SaveAs(os.path.join(args.outdir, "trigger_efficiency.png"))

    print(f"[plot_basic] Wrote plots to {args.outdir}")


if __name__ == "__main__":
    main()
