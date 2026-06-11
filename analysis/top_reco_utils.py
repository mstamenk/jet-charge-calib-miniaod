#!/usr/bin/env python3
"""Utilities for dilepton ttbar reconstruction with ROOT RDataFrame."""

import ROOT

_HELPERS_DECLARED = False


def enable_mt(nthreads: int = 0) -> None:
    """Enable ROOT implicit multithreading."""
    if nthreads and nthreads > 0:
        ROOT.ROOT.EnableImplicitMT(int(nthreads))
    else:
        ROOT.ROOT.EnableImplicitMT()


def declare_cpp_helpers() -> None:
    """Declare C++ helper functions used from RDataFrame Define calls."""
    global _HELPERS_DECLARED
    if _HELPERS_DECLARED:
        return

    ROOT.gInterpreter.Declare(
        r"""
#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <vector>

#include "Math/Factory.h"
#include "Math/Functor.h"
#include "Math/Minimizer.h"
#include "TLorentzVector.h"
#include "ROOT/RVec.hxx"

struct TopRecoResult {
  float chi2 = 1e9f;
  float t1_mass = -1.f;
  float t2_mass = -1.f;
  float w1_mass = -1.f;
  float w2_mass = -1.f;
  float ttbar_mass = -1.f;
  float nu_pt = -1.f;
  float nubar_pt = -1.f;
  float met_residual = -1.f;
  int b1_index = -1;
  int b2_index = -1;
  bool converged = false;
};

float safe_first_f(const ROOT::VecOps::RVec<float>& v, float dflt) {
  return v.empty() ? dflt : v[0];
}

int safe_first_i(const ROOT::VecOps::RVec<int>& v, int dflt) {
  return v.empty() ? dflt : v[0];
}

float compute_analysis_weight(float genWeight,
                              float puWeight,
                              float prefireWeight,
                              float sampleXsecPb,
                              float sampleSumWeights,
                              float targetLumiPb) {
  // Event weight convention:
  //   w = genWeight * pu * prefire * (xsec[pb] * lumi[pb^-1] / sumW_signed)
  // Keep signed sumW to correctly account for NLO negative-weight events.
  // Only fall back to factor 1 when normalization inputs are missing/invalid.
  float norm = 1.0f;
  if (std::abs(sampleSumWeights) > 0.f && sampleXsecPb > 0.f && targetLumiPb > 0.f) {
    norm = (sampleXsecPb * targetLumiPb) / sampleSumWeights;
  }
  return genWeight * puWeight * prefireWeight * norm;
}

TopRecoResult reco_ttbar_dilep_fit(const ROOT::VecOps::RVec<float>& jet_pt,
                                   const ROOT::VecOps::RVec<float>& jet_eta,
                                   const ROOT::VecOps::RVec<float>& jet_phi,
                                   const ROOT::VecOps::RVec<float>& jet_mass,
                                   float mu_pt,
                                   float mu_eta,
                                   float mu_phi,
                                   float mu_mass,
                                   float el_pt,
                                   float el_eta,
                                   float el_phi,
                                   float el_mass,
                                   float met_pt,
                                   float met_phi) {
  TopRecoResult best;
  if (mu_pt <= 0.f || el_pt <= 0.f) {
    return best;
  }
  const int nj = static_cast<int>(jet_pt.size());
  if (nj < 2 || static_cast<int>(jet_eta.size()) < nj || static_cast<int>(jet_phi.size()) < nj ||
      static_cast<int>(jet_mass.size()) < nj) {
    return best;
  }

  TLorentzVector mu, el;
  mu.SetPtEtaPhiM(mu_pt, mu_eta, mu_phi, mu_mass);
  el.SetPtEtaPhiM(el_pt, el_eta, el_phi, el_mass);
  const float metx = met_pt * std::cos(met_phi);
  const float mety = met_pt * std::sin(met_phi);

  const int nj_use = std::min(nj, 4);
  const double mW = 80.379;
  const double mT = 172.5;
  const double sW = 15.0;
  const double sT = 20.0;
  const double sMET = 15.0;

  for (int ib1 = 0; ib1 < nj_use; ++ib1) {
    for (int ib2 = 0; ib2 < nj_use; ++ib2) {
      if (ib1 == ib2) {
        continue;
      }

      TLorentzVector b1, b2;
      b1.SetPtEtaPhiM(jet_pt[ib1], jet_eta[ib1], jet_phi[ib1], jet_mass[ib1]);
      b2.SetPtEtaPhiM(jet_pt[ib2], jet_eta[ib2], jet_phi[ib2], jet_mass[ib2]);

      auto chi2 = [&](const double* p) {
        const double nux = p[0], nuy = p[1], nuz = p[2];
        const double nbx = p[3], nby = p[4], nbz = p[5];
        const double nue = std::sqrt(nux * nux + nuy * nuy + nuz * nuz);
        const double nbe = std::sqrt(nbx * nbx + nby * nby + nbz * nbz);

        TLorentzVector nu, nubar;
        nu.SetPxPyPzE(nux, nuy, nuz, nue);
        nubar.SetPxPyPzE(nbx, nby, nbz, nbe);

        const TLorentzVector w1 = mu + nu;
        const TLorentzVector w2 = el + nubar;
        const TLorentzVector t1 = w1 + b1;
        const TLorentzVector t2 = w2 + b2;

        const double c1 = (w1.M() - mW) / sW;
        const double c2 = (w2.M() - mW) / sW;
        const double c3 = (t1.M() - mT) / sT;
        const double c4 = (t2.M() - mT) / sT;
        const double c5 = ((nux + nbx) - metx) / sMET;
        const double c6 = ((nuy + nby) - mety) / sMET;
        return c1 * c1 + c2 * c2 + c3 * c3 + c4 * c4 + c5 * c5 + c6 * c6;
      };

      std::unique_ptr<ROOT::Math::Minimizer> min(
          ROOT::Math::Factory::CreateMinimizer("Minuit2", "Migrad"));
      if (!min) {
        continue;
      }
      ROOT::Math::Functor fcn(chi2, 6);
      min->SetFunction(fcn);
      min->SetMaxFunctionCalls(2000);
      min->SetMaxIterations(1000);
      min->SetTolerance(1e-3);
      min->SetPrintLevel(0);

      min->SetVariable(0, "nux", metx * 0.5, 5.0);
      min->SetVariable(1, "nuy", mety * 0.5, 5.0);
      min->SetVariable(2, "nuz", 0.0, 10.0);
      min->SetVariable(3, "nbx", metx * 0.5, 5.0);
      min->SetVariable(4, "nby", mety * 0.5, 5.0);
      min->SetVariable(5, "nbz", 0.0, 10.0);

      min->SetVariableLimits(0, -500.0, 500.0);
      min->SetVariableLimits(1, -500.0, 500.0);
      min->SetVariableLimits(2, -1500.0, 1500.0);
      min->SetVariableLimits(3, -500.0, 500.0);
      min->SetVariableLimits(4, -500.0, 500.0);
      min->SetVariableLimits(5, -1500.0, 1500.0);

      const bool ok = min->Minimize();
      if (!ok) {
        continue;
      }
      const double* xs = min->X();
      const double this_chi2 = min->MinValue();
      if (this_chi2 >= best.chi2) {
        continue;
      }

      TLorentzVector nu, nubar;
      nu.SetPxPyPzE(xs[0], xs[1], xs[2], std::sqrt(xs[0] * xs[0] + xs[1] * xs[1] + xs[2] * xs[2]));
      nubar.SetPxPyPzE(xs[3], xs[4], xs[5], std::sqrt(xs[3] * xs[3] + xs[4] * xs[4] + xs[5] * xs[5]));
      const TLorentzVector w1 = mu + nu;
      const TLorentzVector w2 = el + nubar;
      const TLorentzVector t1 = w1 + b1;
      const TLorentzVector t2 = w2 + b2;
      const TLorentzVector tt = t1 + t2;

      best.chi2 = static_cast<float>(this_chi2);
      best.w1_mass = static_cast<float>(w1.M());
      best.w2_mass = static_cast<float>(w2.M());
      best.t1_mass = static_cast<float>(t1.M());
      best.t2_mass = static_cast<float>(t2.M());
      best.ttbar_mass = static_cast<float>(tt.M());
      best.nu_pt = static_cast<float>(nu.Pt());
      best.nubar_pt = static_cast<float>(nubar.Pt());
      best.met_residual = static_cast<float>(
          std::hypot((xs[0] + xs[3]) - metx, (xs[1] + xs[4]) - mety));
      best.b1_index = ib1;
      best.b2_index = ib2;
      best.converged = true;
    }
  }
  return best;
}
"""
    )
    _HELPERS_DECLARED = True


def build_rdf(input_file: str, tree: str = "Events", nthreads: int = 0):
    enable_mt(nthreads)
    declare_cpp_helpers()
    return ROOT.RDataFrame(tree, input_file)


def define_common_columns(df):
    """Define common analysis columns (weights and leading lepton values)."""
    return (
        df.Define(
            "analysis_weight",
            "compute_analysis_weight(genWeight, puWeight, prefireWeight, sampleXsecPb, sampleSumWeights, targetLumiPb)",
        )
        .Define("mu0_pt", "safe_first_f(muon_pt, -1.f)")
        .Define("mu0_eta", "safe_first_f(muon_eta, -9.f)")
        .Define("mu0_phi", "safe_first_f(muon_phi, -9.f)")
        .Define("mu0_mass", "safe_first_f(muon_mass, 0.10566f)")
        .Define("mu0_relIso04", "safe_first_f(muon_relIso04, -1.f)")
        .Define("mu0_isLoose", "safe_first_i(muon_isLoose, -1)")
        .Define("mu0_isMedium", "safe_first_i(muon_isMedium, -1)")
        .Define("mu0_isTight", "safe_first_i(muon_isTight, -1)")
        .Define("mu0_charge", "safe_first_i(muon_charge, 0)")
        .Define("el0_pt", "safe_first_f(electron_pt, -1.f)")
        .Define("el0_eta", "safe_first_f(electron_eta, -9.f)")
        .Define("el0_phi", "safe_first_f(electron_phi, -9.f)")
        .Define("el0_mass", "safe_first_f(electron_mass, 0.000511f)")
        .Define("el0_relIso03", "safe_first_f(electron_relIso03, -1.f)")
        .Define("el0_cutBased", "safe_first_i(electron_cutBased, -1)")
        .Define("el0_charge", "safe_first_i(electron_charge, 0)")
    )


def define_top_reco_columns(df):
    """Attach top-reconstruction fit result columns."""
    df = df.Define(
        "topreco",
        "reco_ttbar_dilep_fit(jet_pt, jet_eta, jet_phi, jet_mass, mu0_pt, mu0_eta, mu0_phi, mu0_mass, el0_pt, el0_eta, el0_phi, el0_mass, met_pt, met_phi)",
    )
    for name in [
        "chi2",
        "t1_mass",
        "t2_mass",
        "w1_mass",
        "w2_mass",
        "ttbar_mass",
        "nu_pt",
        "nubar_pt",
        "met_residual",
        "b1_index",
        "b2_index",
        "converged",
    ]:
        df = df.Define(f"topreco_{name}", f"topreco.{name}")
    return df
