#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

#include "FWCore/Framework/interface/Frameworkfwd.h"
#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/one/EDFilter.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/MessageLogger/interface/MessageLogger.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/Utilities/interface/Exception.h"

#include "DataFormats/Common/interface/TriggerResults.h"
#include "DataFormats/PatCandidates/interface/Electron.h"
#include "DataFormats/PatCandidates/interface/Jet.h"
#include "DataFormats/PatCandidates/interface/Muon.h"
#include "DataFormats/Math/interface/deltaR.h"
#include "DataFormats/VertexReco/interface/Vertex.h"
#include "FWCore/Common/interface/TriggerNames.h"

namespace {

inline std::string toLowerCopy(std::string s) {
  std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
  return s;
}

inline bool isSupportedMuonIdWp(const std::string& wp) {
  return (wp == "none" || wp == "loose" || wp == "medium" || wp == "tight");
}

inline bool isSupportedElectronIdWp(const std::string& wp) {
  return (wp == "none" || wp == "veto" || wp == "loose" || wp == "medium" || wp == "tight");
}

inline int minElectronCutBasedForWp(const std::string& wp) {
  if (wp == "none") {
    return -1;
  }
  if (wp == "veto") {
    return 1;
  }
  if (wp == "loose") {
    return 2;
  }
  if (wp == "medium") {
    return 3;
  }
  if (wp == "tight") {
    return 4;
  }
  return 999;
}

inline bool getElectronIdValueByName(const pat::Electron& electron, const std::string& name, float& value) {
  if (electron.hasUserInt(name)) {
    value = static_cast<float>(electron.userInt(name));
    return true;
  }
  if (electron.hasUserFloat(name)) {
    value = electron.userFloat(name);
    return true;
  }
  try {
    for (const auto& pair : electron.electronIDs()) {
      if (pair.first == name) {
        value = pair.second;
        return true;
      }
    }
  } catch (...) {
  }
  return false;
}

inline int cutBasedFromFlags(const bool sawCutBased,
                             const bool passVeto,
                             const bool passLoose,
                             const bool passMedium,
                             const bool passTight) {
  if (passTight) {
    return 4;
  }
  if (passMedium) {
    return 3;
  }
  if (passLoose) {
    return 2;
  }
  if (passVeto) {
    return 1;
  }
  return sawCutBased ? 0 : -1;
}

inline int electronCutBasedValueFromNamedKeys(const pat::Electron& electron,
                                              const std::string& veto_key,
                                              const std::string& loose_key,
                                              const std::string& medium_key,
                                              const std::string& tight_key) {
  float value = -1.0f;
  const bool hasVeto = getElectronIdValueByName(electron, veto_key, value);
  const bool passVeto = hasVeto && (value > 0.5f);
  const bool hasLoose = getElectronIdValueByName(electron, loose_key, value);
  const bool passLoose = hasLoose && (value > 0.5f);
  const bool hasMedium = getElectronIdValueByName(electron, medium_key, value);
  const bool passMedium = hasMedium && (value > 0.5f);
  const bool hasTight = getElectronIdValueByName(electron, tight_key, value);
  const bool passTight = hasTight && (value > 0.5f);
  const bool saw = hasVeto || hasLoose || hasMedium || hasTight;
  return cutBasedFromFlags(saw, passVeto, passLoose, passMedium, passTight);
}

inline int electronCutBasedValueFromFamily(const pat::Electron& electron, const std::string& family_prefix) {
  return electronCutBasedValueFromNamedKeys(
      electron, family_prefix + "-veto", family_prefix + "-loose", family_prefix + "-medium", family_prefix + "-tight");
}

inline int electronCutBasedValue(const pat::Electron& electron) {
  if (electron.hasUserInt("cutBased")) {
    return electron.userInt("cutBased");
  }
  if (electron.hasUserFloat("cutBased")) {
    return static_cast<int>(electron.userFloat("cutBased"));
  }
  for (const std::string& family : {std::string("cutBasedElectronID-RunIIIWinter22-V1"),
                                    std::string("cutBasedElectronID-Fall17-94X-V2"),
                                    std::string("cutBasedElectronID-Fall17-94X-V1"),
                                    std::string("cutBasedElectronID-Summer16-80X-V1")}) {
    const int from_family = electronCutBasedValueFromFamily(electron, family);
    if (from_family >= 0) {
      return from_family;
    }
  }
  const int from_embedded = electronCutBasedValueFromNamedKeys(
      electron, "cutBasedID_veto", "cutBasedID_loose", "cutBasedID_medium", "cutBasedID_tight");
  if (from_embedded >= 0) {
    return from_embedded;
  }
  return -1;
}

}  // namespace

class EventPreselectionFilter : public edm::one::EDFilter<> {
public:
  explicit EventPreselectionFilter(const edm::ParameterSet&);
  ~EventPreselectionFilter() override = default;

  bool filter(edm::Event&, const edm::EventSetup&) override;
  void endJob() override;

private:
  bool passHLT(const edm::Event&);
  bool passJetId(const pat::Jet&) const;

  edm::EDGetTokenT<edm::View<pat::Jet>> jetsToken_;
  edm::EDGetTokenT<edm::View<pat::Jet>> jetsPuppiToken_;
  edm::EDGetTokenT<edm::View<pat::Muon>> muonsToken_;
  edm::EDGetTokenT<edm::View<pat::Electron>> electronsToken_;
  edm::EDGetTokenT<reco::VertexCollection> verticesToken_;
  edm::EDGetTokenT<edm::TriggerResults> triggerToken_;

  bool applyHLT_;
  bool applyJetSelection_;
  std::vector<std::string> hltPaths_;
  unsigned int minNJets_;
  int maxNJets_;
  double jetMinPt_;
  double jetMaxEta_;
  std::string jetId_;
  double jetLeptonOverlapDR_;
  bool usePuppiJets_;
  std::string leptonMode_;
  int maxNLeptons_;
  double muonMinPt_;
  double muonMaxEta_;
  std::string muonId_;
  double muonMaxRelIso04_;
  double electronMinPt_;
  double electronMaxEta_;
  std::string electronId_;
  double electronMaxRelIso03_;
  bool verboseSummary_;

  uint64_t nProcessed_ = 0;
  uint64_t nPassHLT_ = 0;
  uint64_t nPassLeptons_ = 0;
  uint64_t nPassJets_ = 0;
  uint64_t nPassed_ = 0;
};

EventPreselectionFilter::EventPreselectionFilter(const edm::ParameterSet& cfg)
    : jetsToken_(cfg.getParameter<bool>("applyJetSelection")
                     ? consumes<edm::View<pat::Jet>>(cfg.getParameter<edm::InputTag>("jets"))
                     : edm::EDGetTokenT<edm::View<pat::Jet>>()),
      jetsPuppiToken_(cfg.getParameter<bool>("applyJetSelection")
                          ? consumes<edm::View<pat::Jet>>(cfg.getParameter<edm::InputTag>("jetsPuppi"))
                          : edm::EDGetTokenT<edm::View<pat::Jet>>()),
      muonsToken_(consumes<edm::View<pat::Muon>>(cfg.getParameter<edm::InputTag>("muons"))),
      electronsToken_(consumes<edm::View<pat::Electron>>(cfg.getParameter<edm::InputTag>("electrons"))),
      verticesToken_(consumes<reco::VertexCollection>(cfg.getParameter<edm::InputTag>("vertices"))),
      triggerToken_(consumes<edm::TriggerResults>(cfg.getParameter<edm::InputTag>("triggerResults"))),
      applyHLT_(cfg.getParameter<bool>("applyHLT")),
      applyJetSelection_(cfg.getParameter<bool>("applyJetSelection")),
      hltPaths_(cfg.getParameter<std::vector<std::string>>("hltPaths")),
      minNJets_(cfg.getParameter<unsigned int>("minNJets")),
      maxNJets_(cfg.getParameter<int>("maxNJets")),
      jetMinPt_(cfg.getParameter<double>("jetMinPt")),
      jetMaxEta_(cfg.getParameter<double>("jetMaxEta")),
      jetId_(cfg.getParameter<std::string>("jetId")),
      jetLeptonOverlapDR_(cfg.getParameter<double>("jetLeptonOverlapDR")),
      usePuppiJets_(cfg.getParameter<bool>("usePuppiJets")),
      leptonMode_(cfg.getParameter<std::string>("leptonMode")),
      maxNLeptons_(cfg.getParameter<int>("maxNLeptons")),
      muonMinPt_(cfg.getParameter<double>("muonMinPt")),
      muonMaxEta_(cfg.getParameter<double>("muonMaxEta")),
      muonId_(cfg.getParameter<std::string>("muonId")),
      muonMaxRelIso04_(cfg.getParameter<double>("muonMaxRelIso04")),
      electronMinPt_(cfg.getParameter<double>("electronMinPt")),
      electronMaxEta_(cfg.getParameter<double>("electronMaxEta")),
      electronId_(cfg.getParameter<std::string>("electronId")),
      electronMaxRelIso03_(cfg.getParameter<double>("electronMaxRelIso03")),
      verboseSummary_(cfg.getUntrackedParameter<bool>("verboseSummary", true)) {
  jetId_ = toLowerCopy(jetId_);
  muonId_ = toLowerCopy(muonId_);
  electronId_ = toLowerCopy(electronId_);

  if (!isSupportedMuonIdWp(muonId_)) {
    throw cms::Exception("Configuration") << "Unsupported muonId working point '" << muonId_ << "'";
  }
  if (!isSupportedElectronIdWp(electronId_)) {
    throw cms::Exception("Configuration") << "Unsupported electronId working point '" << electronId_ << "'";
  }
}

bool EventPreselectionFilter::passHLT(const edm::Event& event) {
  if (hltPaths_.empty()) {
    return true;
  }
  edm::Handle<edm::TriggerResults> triggerResults;
  event.getByToken(triggerToken_, triggerResults);
  if (!triggerResults.isValid()) {
    return !applyHLT_;
  }

  const edm::TriggerNames& names = event.triggerNames(*triggerResults);
  bool any_passed = false;
  for (const auto& pattern : hltPaths_) {
    const bool isPrefix = !pattern.empty() && pattern.back() == '*';
    const std::string needle = isPrefix ? pattern.substr(0, pattern.size() - 1) : pattern;
    for (unsigned int i = 0; i < names.size(); ++i) {
      const std::string& name = names.triggerName(i);
      const bool match = isPrefix ? (name.rfind(needle, 0) == 0) : (name == needle);
      if (match && triggerResults->accept(i)) {
        any_passed = true;
        break;
      }
    }
    if (any_passed) {
      break;
    }
  }
  return applyHLT_ ? any_passed : true;
}

bool EventPreselectionFilter::passJetId(const pat::Jet& jet) const {
  if (jetId_.empty() || jetId_ == "none") {
    return true;
  }
  int jetId = -1;
  if (jet.hasUserInt("jetId")) {
    jetId = jet.userInt("jetId");
  } else if (jet.hasUserInt("cutBasedJetId")) {
    jetId = jet.userInt("cutBasedJetId");
  } else if (jet.hasUserInt("cutBasedId")) {
    jetId = jet.userInt("cutBasedId");
  }
  if (jetId < 0) {
    return true;
  }
  if (jetId_ == "loose") {
    return (jetId & (1 << 0));
  }
  if (jetId_ == "tight") {
    return (jetId & (1 << 1));
  }
  if (jetId_ == "tightlepveto") {
    return (jetId & (1 << 2));
  }
  return true;
}

bool EventPreselectionFilter::filter(edm::Event& event, const edm::EventSetup&) {
  ++nProcessed_;

  if (!passHLT(event)) {
    return false;
  }
  ++nPassHLT_;

  edm::Handle<edm::View<pat::Muon>> muons;
  edm::Handle<edm::View<pat::Electron>> electrons;
  edm::Handle<reco::VertexCollection> vertices;
  event.getByToken(muonsToken_, muons);
  event.getByToken(electronsToken_, electrons);
  event.getByToken(verticesToken_, vertices);
  const reco::Vertex* primary_vertex = (vertices.isValid() && !vertices->empty()) ? &vertices->at(0) : nullptr;

  int nMuonSel = 0;
  int nElectronSel = 0;
  std::vector<int> muonCharges;
  std::vector<int> electronCharges;
  std::vector<std::pair<float, float>> selectedLeptonEtaPhi;
  selectedLeptonEtaPhi.reserve(4);
  muonCharges.reserve(4);
  electronCharges.reserve(4);

  const bool require_exactly_one_emu = (leptonMode_ == "dilepton_emu" || leptonMode_ == "dilepton_emu_os");

  if (muons.isValid()) {
    for (const auto& muon : *muons) {
      if (muon.pt() < muonMinPt_ || std::abs(muon.eta()) > muonMaxEta_) {
        continue;
      }
      auto mu_iso = muon.pfIsolationR04();
      const float mu_rel_iso = (mu_iso.sumChargedHadronPt +
                                std::max(0.0f, mu_iso.sumNeutralHadronEt + mu_iso.sumPhotonEt - 0.5f * mu_iso.sumPUPt)) /
                               muon.pt();
      bool pass_mu_id = true;
      if (muonId_ == "loose") {
        pass_mu_id = muon.isLooseMuon();
      } else if (muonId_ == "medium") {
        pass_mu_id = muon.isMediumMuon();
      } else if (muonId_ == "tight") {
        pass_mu_id = primary_vertex ? muon.isTightMuon(*primary_vertex) : false;
      }
      if (!pass_mu_id) {
        continue;
      }
      if (muonMaxRelIso04_ >= 0.0 && mu_rel_iso > muonMaxRelIso04_) {
        continue;
      }
      ++nMuonSel;
      muonCharges.push_back(muon.charge());
      selectedLeptonEtaPhi.emplace_back(static_cast<float>(muon.eta()), static_cast<float>(muon.phi()));
      if (maxNLeptons_ >= 0 && (nMuonSel + nElectronSel) > maxNLeptons_) {
        return false;
      }
      if (require_exactly_one_emu && nMuonSel > 1) {
        return false;
      }
    }
  }

  if (electrons.isValid()) {
    for (const auto& electron : *electrons) {
      if (electron.pt() < electronMinPt_ || std::abs(electron.eta()) > electronMaxEta_) {
        continue;
      }
      auto el_iso = electron.pfIsolationVariables();
      const float el_rel_iso =
          (el_iso.sumChargedHadronPt +
           std::max(0.0f, el_iso.sumNeutralHadronEt + el_iso.sumPhotonEt - 0.5f * el_iso.sumPUPt)) /
          electron.pt();
      const int cutbased = electronCutBasedValue(electron);
      const int min_el_cutbased = minElectronCutBasedForWp(electronId_);
      const bool pass_el_id = (min_el_cutbased < 0) || (cutbased >= min_el_cutbased);
      if (!pass_el_id) {
        continue;
      }
      if (electronMaxRelIso03_ >= 0.0 && el_rel_iso > electronMaxRelIso03_) {
        continue;
      }
      ++nElectronSel;
      electronCharges.push_back(electron.charge());
      selectedLeptonEtaPhi.emplace_back(static_cast<float>(electron.eta()), static_cast<float>(electron.phi()));
      if (maxNLeptons_ >= 0 && (nMuonSel + nElectronSel) > maxNLeptons_) {
        return false;
      }
      if (require_exactly_one_emu && nElectronSel > 1) {
        return false;
      }
    }
  }

  bool passLeptons = true;
  if (leptonMode_ == "hadronic") {
    passLeptons = (nMuonSel == 0 && nElectronSel == 0);
  } else if (leptonMode_ == "single_muon") {
    passLeptons = (nMuonSel >= 1);
  } else if (leptonMode_ == "single_electron") {
    passLeptons = (nElectronSel >= 1);
  } else if (leptonMode_ == "single_lepton") {
    passLeptons = (nMuonSel + nElectronSel == 1);
  } else if (leptonMode_ == "at_least_one_lepton") {
    passLeptons = (nMuonSel + nElectronSel >= 1);
  } else if (leptonMode_ == "dilepton") {
    passLeptons = (nMuonSel + nElectronSel >= 2);
  } else if (leptonMode_ == "dilepton_emu") {
    passLeptons = (nMuonSel == 1 && nElectronSel == 1);
  } else if (leptonMode_ == "dilepton_emu_os") {
    passLeptons = (nMuonSel == 1 && nElectronSel == 1 && !muonCharges.empty() && !electronCharges.empty() &&
                   (muonCharges[0] * electronCharges[0] < 0));
  } else {
    throw cms::Exception("Configuration")
        << "Unsupported leptonMode '" << leptonMode_
        << "'. Allowed modes: hadronic, single_muon, single_electron, single_lepton, at_least_one_lepton, "
           "dilepton, dilepton_emu, dilepton_emu_os";
  }
  if (!passLeptons) {
    return false;
  }
  ++nPassLeptons_;

  if (!applyJetSelection_) {
    ++nPassJets_;
    ++nPassed_;
    return true;
  }

  edm::Handle<edm::View<pat::Jet>> jets;
  edm::Handle<edm::View<pat::Jet>> jetsPuppi;
  event.getByToken(jetsToken_, jets);
  event.getByToken(jetsPuppiToken_, jetsPuppi);

  const edm::View<pat::Jet>* jets_view = jets.product();
  if (usePuppiJets_ && jetsPuppi.isValid() && !jetsPuppi->empty()) {
    jets_view = jetsPuppi.product();
  }

  const auto overlapsSelectedLepton = [&](const pat::Jet& jet) -> bool {
    if (jetLeptonOverlapDR_ <= 0.0) {
      return false;
    }
    for (const auto& lep : selectedLeptonEtaPhi) {
      if (reco::deltaR(jet.eta(), jet.phi(), lep.first, lep.second) < jetLeptonOverlapDR_) {
        return true;
      }
    }
    return false;
  };

  int nJetsPreselected = 0;
  if (jets_view) {
    for (const auto& jet : *jets_view) {
      if (jet.pt() < jetMinPt_ || std::abs(jet.eta()) > jetMaxEta_) {
        continue;
      }
      if (!passJetId(jet)) {
        continue;
      }
      if (overlapsSelectedLepton(jet)) {
        continue;
      }
      ++nJetsPreselected;
      if (maxNJets_ >= 0 && nJetsPreselected > maxNJets_) {
        return false;
      }
    }
  }
  if (nJetsPreselected < static_cast<int>(minNJets_)) {
    return false;
  }
  ++nPassJets_;
  ++nPassed_;
  return true;
}

void EventPreselectionFilter::endJob() {
  if (!verboseSummary_) {
    return;
  }
  edm::LogPrint("EventPreselectionFilter")
      << "[jet-charge-calib] EventPreselectionFilter summary: processed=" << nProcessed_ << ", pass_hlt=" << nPassHLT_
      << ", pass_leptons=" << nPassLeptons_ << ", pass_jets=" << nPassJets_ << ", accepted=" << nPassed_;
}

DEFINE_FWK_MODULE(EventPreselectionFilter);
