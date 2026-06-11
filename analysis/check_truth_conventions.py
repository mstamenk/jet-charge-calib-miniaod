#!/usr/bin/env python3
import argparse
import json
import math

import ROOT


def _v(v):
    return list(v) if hasattr(v, "__len__") else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--max-events", type=int, default=200000)
    ap.add_argument("--output", default="studies/ttbar_dilepton_reco/output/truth_convention_summary.json")
    args = ap.parse_args()

    f = ROOT.TFile.Open(args.input)
    t = f.Get("Events")

    n = 0
    convA_ok = 0
    convB_ok = 0
    amb = 0
    unique_vals = set()

    for ev in t:
        if args.max_events > 0 and n >= args.max_events:
            break
        jets_q = _v(ev.jet_pflavCharge)
        jets_h = _v(ev.jet_hflav)
        muq = int(getattr(ev, "mu0_charge", 0))
        elq = int(getattr(ev, "el0_charge", 0))
        if muq * elq >= 0:
            continue
        bidx = [i for i, h in enumerate(jets_h) if abs(int(h)) == 5]
        if len(bidx) != 2:
            continue
        n += 1
        qvals = [int(jets_q[i]) for i in bidx]
        unique_vals.update(qvals)
        if 0 in qvals or qvals[0] == qvals[1]:
            amb += 1
            continue
        # A: negative means b, positive means bbar
        # choose b-jet as one paired to positive lepton (l+)
        lplus_is_el = elq > 0
        bA = bidx[0] if qvals[0] < 0 else bidx[1]
        bB = bidx[0] if qvals[0] > 0 else bidx[1]
        # loose pairing proxy: closer m_lb between l+ and b than l+ and bbar
        jets_pt = _v(ev.jet_pt); jets_eta = _v(ev.jet_eta); jets_phi = _v(ev.jet_phi); jets_m = _v(ev.jet_mass)

        def p4(pt, eta, phi, m):
            px = pt * math.cos(phi); py = pt * math.sin(phi); pz = pt * math.sinh(eta); e = math.sqrt(max(0.0, px*px+py*py+pz*pz+m*m)); return (px,py,pz,e)

        def mass(a, b):
            x = [a[i]+b[i] for i in range(4)]
            return math.sqrt(max(0.0, x[3]*x[3] - x[0]*x[0] - x[1]*x[1] - x[2]*x[2]))

        el = p4(ev.el0_pt, ev.el0_eta, ev.el0_phi, ev.el0_mass)
        mu = p4(ev.mu0_pt, ev.mu0_eta, ev.mu0_phi, ev.mu0_mass)
        jb = p4(jets_pt[bA], jets_eta[bA], jets_phi[bA], jets_m[bA])
        jbb = p4(jets_pt[bB], jets_eta[bB], jets_phi[bB], jets_m[bB])
        lplus = el if lplus_is_el else mu
        lminus = mu if lplus_is_el else el
        okA = mass(lplus, jb) + mass(lminus, jbb) <= mass(lplus, jbb) + mass(lminus, jb)

        # B inverted
        bA2 = bidx[0] if qvals[0] > 0 else bidx[1]
        bB2 = bidx[0] if qvals[0] < 0 else bidx[1]
        jb2 = p4(jets_pt[bA2], jets_eta[bA2], jets_phi[bA2], jets_m[bA2])
        jbb2 = p4(jets_pt[bB2], jets_eta[bB2], jets_phi[bB2], jets_m[bB2])
        okB = mass(lplus, jb2) + mass(lminus, jbb2) <= mass(lplus, jbb2) + mass(lminus, jb2)
        convA_ok += int(okA)
        convB_ok += int(okB)

    chosen = "A" if convA_ok >= convB_ok else "B"
    out = {
        "n_clean_events": n,
        "convA_consistency": (convA_ok / max(1, n)),
        "convB_consistency": (convB_ok / max(1, n)),
        "chosen_convention": chosen,
        "chosen_sign": -1 if chosen == "A" else 1,
        "ambiguous_or_zero_charge_fraction": amb / max(1, n),
        "observed_unique_values": sorted(unique_vals),
        "truth_charge_convention_used": "jet_pflavCharge < 0 => b" if chosen == "A" else "jet_pflavCharge > 0 => b",
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
