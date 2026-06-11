#!/usr/bin/env python3
import argparse

import ROOT


def as_list(value):
    return [value[i] for i in range(value.size())]


def main():
    parser = argparse.ArgumentParser(description="Print jets ranked by pT from a jet-charge ntuple.")
    parser.add_argument("input", help="Output ROOT file from cmssw/test/run_cfg.py")
    parser.add_argument("--tree", default="Events", help="TTree name")
    args = parser.parse_args()

    root_file = ROOT.TFile.Open(args.input)
    if not root_file or root_file.IsZombie():
        raise RuntimeError(f"Could not open {args.input}")

    tree = root_file.Get(args.tree)
    if not tree:
        raise RuntimeError(f"Could not find tree {args.tree} in {args.input}")
    if tree.GetEntries() == 0:
        raise RuntimeError(f"Tree {args.tree} has no entries")

    tree.GetEntry(0)
    jets = []
    pts = as_list(tree.jet_pt)
    for idx, pt in enumerate(pts):
        jets.append(
            {
                "idx": idx,
                "pt": pt,
                "eta": tree.jet_eta[idx],
                "phi": tree.jet_phi[idx],
                "btag_deepb": tree.jet_btagDeepB[idx],
                "btag_robustpart": tree.jet_btagRobustParTAK4B[idx],
                "charge_score": tree.jet_charge_score[idx],
                "part_pos": tree.jet_ParTPosvsAll[idx],
                "part_neg": tree.jet_ParTNegvsAll[idx],
                "part_zero": tree.jet_ParTZerovsAll[idx],
                "part_pos_neg": tree.jet_ParTPosvsNeg[idx],
            }
        )

    jets.sort(key=lambda item: item["pt"], reverse=True)
    print(f"run:lumi:event = {int(tree.run)}:{int(tree.lumi)}:{int(tree.event)}")
    print(f"nJetSel = {int(tree.nJetSel)}")
    print(
        "rank  idx      pt      eta      phi   DeepB  RobustParT_B  charge_score  "
        "PosAll  NegAll  ZeroAll  PosNeg"
    )
    for rank, jet in enumerate(jets, start=1):
        print(
            f"{rank:4d} {jet['idx']:4d} "
            f"{jet['pt']:7.2f} {jet['eta']:8.3f} {jet['phi']:8.3f} "
            f"{jet['btag_deepb']:7.4f} {jet['btag_robustpart']:13.4f} "
            f"{jet['charge_score']:13.4f} {jet['part_pos']:7.4f} "
            f"{jet['part_neg']:7.4f} {jet['part_zero']:8.4f} {jet['part_pos_neg']:7.4f}"
        )


if __name__ == "__main__":
    main()
