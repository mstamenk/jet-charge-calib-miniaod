#include <algorithm>
#include <cmath>
#include <cctype>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include <memory>

#include "FWCore/Framework/interface/Frameworkfwd.h"
#include "FWCore/Framework/interface/Event.h"
#include "FWCore/Framework/interface/EventSetup.h"
#include "FWCore/Framework/interface/one/EDAnalyzer.h"
#include "FWCore/Framework/interface/MakerMacros.h"
#include "FWCore/ParameterSet/interface/ParameterSet.h"
#include "FWCore/ServiceRegistry/interface/Service.h"
#include "FWCore/Utilities/interface/ESInputTag.h"
#include "CommonTools/UtilAlgos/interface/TFileService.h"

#include "DataFormats/Common/interface/TriggerResults.h"
#include "DataFormats/HepMCCandidate/interface/GenParticle.h"
#include "DataFormats/PatCandidates/interface/Electron.h"
#include "DataFormats/PatCandidates/interface/Jet.h"
#include "DataFormats/PatCandidates/interface/MET.h"
#include "DataFormats/PatCandidates/interface/Muon.h"
#include "DataFormats/PatCandidates/interface/PackedCandidate.h"
#include "DataFormats/PatCandidates/interface/Tau.h"
#include "DataFormats/TrackReco/interface/TrackBase.h"
#include "DataFormats/Math/interface/LorentzVector.h"
#include "DataFormats/Candidate/interface/Candidate.h"
#include "DataFormats/Candidate/interface/VertexCompositePtrCandidate.h"
#include "DataFormats/VertexReco/interface/Vertex.h"
#include "DataFormats/BTauReco/interface/JetTag.h"
#include "DataFormats/BTauReco/interface/ShallowTagInfo.h"
#include "DataFormats/BTauReco/interface/TaggingVariable.h"
#include "DataFormats/BTauReco/interface/TaggingVariable.h"
#include "DataFormats/Math/interface/deltaR.h"
#include "DataFormats/GeometryVector/interface/GlobalVector.h"
#include "SimDataFormats/GeneratorProducts/interface/GenEventInfoProduct.h"
#include "SimDataFormats/GeneratorProducts/interface/LHEEventProduct.h"
#include "SimDataFormats/PileupSummaryInfo/interface/PileupSummaryInfo.h"
#include "FWCore/Common/interface/TriggerNames.h"

#include "TrackingTools/TransientTrack/interface/TransientTrackBuilder.h"
#include "TrackingTools/IPTools/interface/IPTools.h"
#include "TrackingTools/PatternTools/interface/TwoTrackMinimumDistance.h"
#include "TrackingTools/Records/interface/TransientTrackRecord.h"
#include "TrackingTools/TrajectoryState/interface/TrajectoryStateOnSurface.h"
#include "TrackingTools/GeomPropagators/interface/AnalyticalImpactPointExtrapolator.h"
#include "RecoVertex/VertexTools/interface/VertexDistance3D.h"
#include "RecoVertex/VertexTools/interface/VertexDistanceXY.h"
#include "RecoVertex/VertexPrimitives/interface/ConvertToFromReco.h"
#include "RecoVertex/VertexPrimitives/interface/VertexState.h"
#include "DataFormats/GeometryCommonDetAlgo/interface/Measurement1D.h"
#include "DataFormats/GeometrySurface/interface/Line.h"

#include "TLorentzVector.h"
#include "TVector3.h"
#include "TTree.h"
#include "TH1I.h"
#include "TFile.h"

namespace {

inline float catchInfs(const float value, const float replace_value) {
  if (!std::isfinite(value)) {
    return replace_value;
  }
  if (value < -1e32f || value > 1e32f) {
    return replace_value;
  }
  return value;
}

inline float catchInfsAndBound(const float value,
                               const float replace_value,
                               const float lower,
                               const float upper,
                               const float offset = 0.0f) {
  float out = catchInfs(value, replace_value);
  if (out + offset < lower) {
    return lower;
  }
  if (out + offset > upper) {
    return upper;
  }
  return out + offset;
}

struct SortEntry {
  size_t idx = 0;
  float a = 0.0f;
  float b = 0.0f;
  float c = 0.0f;
};

inline bool isPhysValue(const float val) {
  if (!std::isfinite(val)) {
    return false;
  }
  return true;
}

inline int compareVal(const SortEntry &lhs, const SortEntry &rhs, const int which) {
  float l = lhs.a;
  float r = rhs.a;
  if (which == 1) {
    l = lhs.b;
    r = rhs.b;
  } else if (which == 2) {
    l = lhs.c;
    r = rhs.c;
  }
  if (isPhysValue(l) && isPhysValue(r) && l != r) {
    return (l > r) ? 1 : -1;
  }
  if (isPhysValue(l) && !isPhysValue(r)) {
    return 1;
  }
  if (!isPhysValue(l) && isPhysValue(r)) {
    return -1;
  }
  return 0;
}

inline bool compareByABCInv(const SortEntry &lhs, const SortEntry &rhs) {
  int res = compareVal(rhs, lhs, 0);
  if (res != 0) {
    return res < 0;
  }
  res = compareVal(rhs, lhs, 1);
  if (res != 0) {
    return res < 0;
  }
  res = compareVal(rhs, lhs, 2);
  if (res != 0) {
    return res < 0;
  }
  return false;
}

inline std::vector<size_t> invertSortingVector(const std::vector<SortEntry> &in) {
  size_t max_idx = 0;
  for (const auto &entry : in) {
    if (entry.idx > max_idx) {
      max_idx = entry.idx;
    }
  }
  std::vector<size_t> out(max_idx + 1, 0);
  for (size_t i = 0; i < in.size(); ++i) {
    out.at(in.at(i).idx) = i;
  }
  return out;
}

inline bool pdgHasQuark(const int pdgid, const int quark) {
  int apdg = std::abs(pdgid);
  if (apdg < 100) {
    return false;
  }
  int d1 = (apdg / 1000) % 10;
  int d2 = (apdg / 100) % 10;
  int d3 = (apdg / 10) % 10;
  return (d1 == quark || d2 == quark || d3 == quark);
}

inline bool isHeavyFlavorHadron(const int pdgid) {
  int apdg = std::abs(pdgid);
  if (apdg < 400) {
    return false;
  }
  return pdgHasQuark(pdgid, 5) || pdgHasQuark(pdgid, 4);
}

inline bool isBHadron(const int pdgid) { return pdgHasQuark(pdgid, 5); }

inline bool isCHadron(const int pdgid) { return pdgHasQuark(pdgid, 4); }

inline int heavyFlavorMotherPdgId(const reco::GenParticle &gp) {
  const reco::Candidate *mother = gp.mother();
  if (!mother) {
    return 0;
  }
  int pdgid = mother->pdgId();
  if (isHeavyFlavorHadron(pdgid)) {
    return pdgid;
  }
  return 0;
}

inline bool hasDaughterWithQuark(const reco::Candidate &cand, const int quark) {
  const size_t ndaughters = cand.numberOfDaughters();
  for (size_t i = 0; i < ndaughters; ++i) {
    const reco::Candidate *dau = cand.daughter(i);
    if (!dau) {
      continue;
    }
    if (pdgHasQuark(dau->pdgId(), quark)) {
      return true;
    }
  }
  return false;
}

struct HeavyAncestry {
  bool fromB = false;
  bool fromC = false;
  bool fromBviaC = false;
};

inline HeavyAncestry heavyAncestry(const reco::Candidate *cand) {
  HeavyAncestry info;
  const reco::Candidate *mom = cand ? cand->mother() : nullptr;
  int depth = 0;
  while (mom && depth < 50) {
    int pdgid = mom->pdgId();
    if (pdgHasQuark(pdgid, 4)) {
      info.fromC = true;
    }
    if (pdgHasQuark(pdgid, 5)) {
      info.fromB = true;
      if (info.fromC) {
        info.fromBviaC = true;
      }
      break;
    }
    mom = mom->mother();
    ++depth;
  }
  return info;
}

inline int pdgChargeFromId(const int pdgid) {
  int apdg = std::abs(pdgid);
  if (apdg == 511 || apdg == 531 || apdg == 421 || apdg == 111 || apdg == 311 ||
      apdg == 310 || apdg == 130 || apdg == 2112 || apdg == 3122 || apdg == 4232 ||
      apdg == 4132 || apdg == 4332 || apdg == 5232) {
    return 0;
  }
  if (pdgid > 0) {
    return 1;
  }
  if (pdgid < 0) {
    return -1;
  }
  return 0;
}

inline int hadronSpeciesFromPdgId(const int pdgid) {
  int apdg = std::abs(pdgid);
  if (apdg == 521) {
    return 1;  // B+
  }
  if (apdg == 511) {
    return 2;  // B0
  }
  if (apdg == 531) {
    return 3;  // Bs0
  }
  if (apdg == 541) {
    return 4;  // Bc
  }
  if (pdgHasQuark(pdgid, 5)) {
    return 5;  // other b-hadron (b baryon, excited states)
  }
  if (apdg == 421) {
    return 6;  // D0
  }
  if (apdg == 411) {
    return 7;  // D+
  }
  if (apdg == 431) {
    return 8;  // Ds
  }
  if (pdgHasQuark(pdgid, 4)) {
    return 9;  // other c-hadron (c baryon, excited states)
  }
  return 0;
}

inline float packedCandidatePdgCategory(const pat::PackedCandidate *cand) {
  if (!cand) {
    return 7.0f;
  }
  int apdg = std::abs(cand->pdgId());
  if (apdg == 11 && cand->charge() != 0) {
    return 0.0f;
  }
  if (apdg == 13 && cand->charge() != 0) {
    return 1.0f;
  }
  if (apdg == 22 && cand->charge() == 0) {
    return 2.0f;
  }
  if (apdg != 22 && cand->charge() == 0 && apdg != 1 && apdg != 2) {
    return 3.0f;
  }
  if (apdg != 11 && apdg != 13 && cand->charge() != 0) {
    return 4.0f;
  }
  if (cand->charge() == 0 && apdg == 1) {
    return 5.0f;
  }
  if (cand->charge() == 0 && apdg == 2) {
    return 6.0f;
  }
  return 7.0f;
}

inline std::string sanitizeBtagLabel(const std::string &label) {
  std::string out;
  out.reserve(label.size());
  for (char c : label) {
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) {
      out.push_back(c);
    } else {
      out.push_back('_');
    }
  }
  return out;
}

inline float getJetDiscriminator(const pat::Jet &jet, std::initializer_list<const char *> labels) {
  for (const auto *label : labels) {
    float val = jet.bDiscriminator(label);
    if (val > -990.0f) {
      return val;
    }
  }
  return -1.0f;
}

inline float getJetDiscriminator(const pat::Jet &jet, const std::string &label) {
  float val = jet.bDiscriminator(label);
  if (val > -990.0f) {
    return val;
  }
  return -1.0f;
}

inline bool isValidBranchChar(const char c) {
  return std::isalnum(static_cast<unsigned char>(c)) || c == '_';
}

inline float getTauId(const pat::Tau &tau, const std::string &label, float fallback) {
  if (tau.isTauIDAvailable(label)) {
    return static_cast<float>(tau.tauID(label));
  }
  return fallback;
}

class TrackInfoBuilder {
public:
  explicit TrackInfoBuilder(const TransientTrackBuilder *builder)
      : builder_(builder),
        trackMomentum_(0.0f),
        trackEta_(0.0f),
        trackEtaRel_(0.0f),
        trackPtRel_(0.0f),
        trackPPar_(0.0f),
        trackDeltaR_(0.0f),
        trackPtRatio_(0.0f),
        trackPParRatio_(0.0f),
        trackSip2dVal_(0.0f),
        trackSip2dSig_(0.0f),
        trackSip3dVal_(0.0f),
        trackSip3dSig_(0.0f),
        trackJetDecayLen_(0.0f),
        trackJetDistVal_(0.0f),
        trackJetDistSig_(0.0f) {}

  void buildTrackInfo(const pat::PackedCandidate *cand,
                      const math::XYZVector &jetDir,
                      const GlobalVector &refjetdirection,
                      const reco::Vertex &pv) {
    TVector3 jetDir3(jetDir.x(), jetDir.y(), jetDir.z());
    if (!cand) {
      trackMomentum_ = 0.0f;
      trackEta_ = 0.0f;
      trackEtaRel_ = 0.0f;
      trackPtRel_ = 0.0f;
      trackPPar_ = 0.0f;
      trackDeltaR_ = 0.0f;
      trackPtRatio_ = 0.0f;
      trackPParRatio_ = 0.0f;
      trackSip2dVal_ = 0.0f;
      trackSip2dSig_ = 0.0f;
      trackSip3dVal_ = 0.0f;
      trackSip3dSig_ = 0.0f;
      trackJetDecayLen_ = 0.0f;
      trackJetDistVal_ = 0.0f;
      trackJetDistSig_ = 0.0f;
      return;
    }
    if (!cand->hasTrackDetails() || !builder_) {
      TVector3 trackMom3(cand->momentum().x(), cand->momentum().y(), cand->momentum().z());
      trackMomentum_ = cand->p();
      trackEta_ = cand->eta();
      trackEtaRel_ = reco::btau::etaRel(jetDir, cand->momentum());
      trackPtRel_ = trackMom3.Perp(jetDir3);
      trackPPar_ = jetDir.Dot(cand->momentum());
      trackDeltaR_ = reco::deltaR(cand->momentum(), jetDir);
      trackPtRatio_ = trackMom3.Perp(jetDir3) / cand->p();
      trackPParRatio_ = jetDir.Dot(cand->momentum()) / cand->p();
      trackSip2dVal_ = 0.0f;
      trackSip2dSig_ = 0.0f;
      trackSip3dVal_ = 0.0f;
      trackSip3dSig_ = 0.0f;
      trackJetDecayLen_ = 0.0f;
      trackJetDistVal_ = 0.0f;
      trackJetDistSig_ = 0.0f;
      return;
    }

    const reco::Track &pseudoTrack = cand->pseudoTrack();
    reco::TransientTrack transientTrack = builder_->build(pseudoTrack);
    Measurement1D meas_ip2d =
        IPTools::signedTransverseImpactParameter(transientTrack, refjetdirection, pv).second;
    Measurement1D meas_ip3d =
        IPTools::signedImpactParameter3D(transientTrack, refjetdirection, pv).second;
    Measurement1D jetdist = IPTools::jetTrackDistance(transientTrack, refjetdirection, pv).second;
    Measurement1D decayl = IPTools::signedDecayLength3D(transientTrack, refjetdirection, pv).second;

    math::XYZVector trackMom = pseudoTrack.momentum();
    double trackMag = std::sqrt(trackMom.Mag2());
    TVector3 trackMom3(trackMom.x(), trackMom.y(), trackMom.z());

    trackMomentum_ = std::sqrt(trackMom.Mag2());
    trackEta_ = trackMom.Eta();
    trackEtaRel_ = reco::btau::etaRel(jetDir, trackMom);
    trackPtRel_ = trackMom3.Perp(jetDir3);
    trackPPar_ = jetDir.Dot(trackMom);
    trackDeltaR_ = reco::deltaR(trackMom, jetDir);
    trackPtRatio_ = trackMom3.Perp(jetDir3) / trackMag;
    trackPParRatio_ = jetDir.Dot(trackMom) / trackMag;

    trackSip2dVal_ = meas_ip2d.value();
    trackSip2dSig_ = meas_ip2d.significance();
    trackSip3dVal_ = meas_ip3d.value();
    trackSip3dSig_ = meas_ip3d.significance();

    trackJetDecayLen_ = decayl.value();
    trackJetDistVal_ = jetdist.value();
    trackJetDistSig_ = jetdist.significance();

    ttrack_ = transientTrack;
  }

  float getTrackDeltaR() const { return trackDeltaR_; }
  float getTrackEta() const { return trackEta_; }
  float getTrackEtaRel() const { return trackEtaRel_; }
  float getTrackJetDecayLen() const { return trackJetDecayLen_; }
  float getTrackJetDistSig() const { return trackJetDistSig_; }
  float getTrackJetDistVal() const { return trackJetDistVal_; }
  float getTrackMomentum() const { return trackMomentum_; }
  float getTrackPPar() const { return trackPPar_; }
  float getTrackPParRatio() const { return trackPParRatio_; }
  float getTrackPtRatio() const { return trackPtRatio_; }
  float getTrackPtRel() const { return trackPtRel_; }
  float getTrackSip2dSig() const { return trackSip2dSig_; }
  float getTrackSip2dVal() const { return trackSip2dVal_; }
  float getTrackSip3dSig() const { return trackSip3dSig_; }
  float getTrackSip3dVal() const { return trackSip3dVal_; }
  reco::TransientTrack getTTrack() const { return ttrack_; }

private:
  const TransientTrackBuilder *builder_;
  float trackMomentum_;
  float trackEta_;
  float trackEtaRel_;
  float trackPtRel_;
  float trackPPar_;
  float trackDeltaR_;
  float trackPtRatio_;
  float trackPParRatio_;
  float trackSip2dVal_;
  float trackSip2dSig_;
  float trackSip3dVal_;
  float trackSip3dSig_;
  float trackJetDecayLen_;
  float trackJetDistVal_;
  float trackJetDistSig_;
  reco::TransientTrack ttrack_;
};

class TrackPairInfoBuilder {
public:
  TrackPairInfoBuilder()
      : pca_distance_(0.0f),
        pca_significance_(0.0f),
        pcaSeed_x_(0.0f),
        pcaSeed_y_(0.0f),
        pcaSeed_z_(0.0f),
        pcaSeed_xerr_(0.0f),
        pcaSeed_yerr_(0.0f),
        pcaSeed_zerr_(0.0f),
        pcaTrack_x_(0.0f),
        pcaTrack_y_(0.0f),
        pcaTrack_z_(0.0f),
        pcaTrack_xerr_(0.0f),
        pcaTrack_yerr_(0.0f),
        pcaTrack_zerr_(0.0f),
        dotprodTrack_(0.0f),
        dotprodSeed_(0.0f),
        pcaSeed_dist_(0.0f),
        pcaTrack_dist_(0.0f),
        dotprodTrackSeed2D_(0.0f),
        dotprodTrackSeed2DV_(0.0f),
        dotprodTrackSeed3D_(0.0f),
        dotprodTrackSeed3DV_(0.0f),
        pca_jetAxis_dist_(0.0f),
        pca_jetAxis_dotprod_(0.0f),
        pca_jetAxis_dEta_(0.0f),
        pca_jetAxis_dPhi_(0.0f),
        pfcand_dist_vtx_12_(0.0f) {}

  void reset() {
    pca_distance_ = 0.0f;
    pca_significance_ = 0.0f;
    pcaSeed_x_ = 0.0f;
    pcaSeed_y_ = 0.0f;
    pcaSeed_z_ = 0.0f;
    pcaSeed_xerr_ = 0.0f;
    pcaSeed_yerr_ = 0.0f;
    pcaSeed_zerr_ = 0.0f;
    pcaTrack_x_ = 0.0f;
    pcaTrack_y_ = 0.0f;
    pcaTrack_z_ = 0.0f;
    pcaTrack_xerr_ = 0.0f;
    pcaTrack_yerr_ = 0.0f;
    pcaTrack_zerr_ = 0.0f;
    dotprodTrack_ = 0.0f;
    dotprodSeed_ = 0.0f;
    pcaSeed_dist_ = 0.0f;
    pcaTrack_dist_ = 0.0f;
    dotprodTrackSeed2D_ = 0.0f;
    dotprodTrackSeed2DV_ = 0.0f;
    dotprodTrackSeed3D_ = 0.0f;
    dotprodTrackSeed3DV_ = 0.0f;
    pca_jetAxis_dist_ = 0.0f;
    pca_jetAxis_dotprod_ = 0.0f;
    pca_jetAxis_dEta_ = 0.0f;
    pca_jetAxis_dPhi_ = 0.0f;
    pfcand_dist_vtx_12_ = 0.0f;
  }

  void buildTrackPairInfo(const reco::TransientTrack it,
                          const reco::TransientTrack tt,
                          const reco::Vertex &pv,
                          const pat::Jet &jet) {
    reset();
    GlobalVector jetdirection(jet.px(), jet.py(), jet.pz());
    GlobalPoint pvp(pv.x(), pv.y(), pv.z());

    VertexDistance3D distanceComputer;
    TwoTrackMinimumDistance dist;

    auto const &iImpactState = it.impactPointState();
    auto const &tImpactState = tt.impactPointState();

    if (dist.calculate(tImpactState, iImpactState)) {
      GlobalPoint ttPoint = dist.points().first;
      GlobalError ttPointErr = tImpactState.cartesianError().position();
      GlobalPoint seedPosition = dist.points().second;
      GlobalError seedPositionErr = iImpactState.cartesianError().position();

      Measurement1D m =
          distanceComputer.distance(VertexState(seedPosition, seedPositionErr), VertexState(ttPoint, ttPointErr));

      GlobalPoint cp(dist.crossingPoint());

      GlobalVector pairMomentum((Basic3DVector<float>)(it.track().momentum() + tt.track().momentum()));
      GlobalVector pvToPCA(cp - pvp);

      float pvToPCAseed = (seedPosition - pvp).mag();
      float pvToPCAtrack = (ttPoint - pvp).mag();
      float distance = dist.distance();

      GlobalVector trackDir2D(tImpactState.globalDirection().x(), tImpactState.globalDirection().y(), 0.0);
      GlobalVector seedDir2D(iImpactState.globalDirection().x(), iImpactState.globalDirection().y(), 0.0);
      GlobalVector trackPCADir2D(ttPoint.x() - pvp.x(), ttPoint.y() - pvp.y(), 0.0);
      GlobalVector seedPCADir2D(seedPosition.x() - pvp.x(), seedPosition.y() - pvp.y(), 0.0);

      float dotprodTrack = (ttPoint - pvp).unit().dot(tImpactState.globalDirection().unit());
      float dotprodSeed = (seedPosition - pvp).unit().dot(iImpactState.globalDirection().unit());

      Line::PositionType pos(pvp);
      Line::DirectionType dir(jetdirection);
      Line::DirectionType pairMomentumDir(pairMomentum);
      Line jetLine(pos, dir);
      Line PCAMomentumLine(cp, pairMomentumDir);

      pca_distance_ = distance;
      pca_significance_ = m.significance();

      pcaSeed_x_ = seedPosition.x();
      pcaSeed_y_ = seedPosition.y();
      pcaSeed_z_ = seedPosition.z();
      pcaSeed_xerr_ = seedPositionErr.cxx();
      pcaSeed_yerr_ = seedPositionErr.cyy();
      pcaSeed_zerr_ = seedPositionErr.czz();
      pcaTrack_x_ = ttPoint.x();
      pcaTrack_y_ = ttPoint.y();
      pcaTrack_z_ = ttPoint.z();
      pcaTrack_xerr_ = ttPointErr.cxx();
      pcaTrack_yerr_ = ttPointErr.cyy();
      pcaTrack_zerr_ = ttPointErr.czz();

      dotprodTrack_ = dotprodTrack;
      dotprodSeed_ = dotprodSeed;
      pcaSeed_dist_ = pvToPCAseed;
      pcaTrack_dist_ = pvToPCAtrack;

      dotprodTrackSeed2D_ = trackDir2D.unit().dot(seedDir2D.unit());
      dotprodTrackSeed3D_ = iImpactState.globalDirection().unit().dot(tImpactState.globalDirection().unit());
      dotprodTrackSeed2DV_ = trackPCADir2D.unit().dot(seedPCADir2D.unit());
      dotprodTrackSeed3DV_ = (seedPosition - pvp).unit().dot((ttPoint - pvp).unit());

      pca_jetAxis_dist_ = jetLine.distance(cp).mag();
      pca_jetAxis_dotprod_ = pairMomentum.unit().dot(jetdirection.unit());
      pca_jetAxis_dEta_ = std::fabs(pvToPCA.eta() - jetdirection.eta());
      pca_jetAxis_dPhi_ = std::fabs(pvToPCA.phi() - jetdirection.phi());
      pfcand_dist_vtx_12_ = pvToPCA.mag();
    }
  }

  float pca_distance() const { return pca_distance_; }
  float pca_significance() const { return pca_significance_; }
  float pcaSeed_x() const { return pcaSeed_x_; }
  float pcaSeed_y() const { return pcaSeed_y_; }
  float pcaSeed_z() const { return pcaSeed_z_; }
  float pcaSeed_xerr() const { return pcaSeed_xerr_; }
  float pcaSeed_yerr() const { return pcaSeed_yerr_; }
  float pcaSeed_zerr() const { return pcaSeed_zerr_; }
  float pcaTrack_x() const { return pcaTrack_x_; }
  float pcaTrack_y() const { return pcaTrack_y_; }
  float pcaTrack_z() const { return pcaTrack_z_; }
  float pcaTrack_xerr() const { return pcaTrack_xerr_; }
  float pcaTrack_yerr() const { return pcaTrack_yerr_; }
  float pcaTrack_zerr() const { return pcaTrack_zerr_; }
  float dotprodTrack() const { return dotprodTrack_; }
  float dotprodSeed() const { return dotprodSeed_; }
  float pcaSeed_dist() const { return pcaSeed_dist_; }
  float pcaTrack_dist() const { return pcaTrack_dist_; }
  float dotprodTrackSeed2D() const { return dotprodTrackSeed2D_; }
  float dotprodTrackSeed2DV() const { return dotprodTrackSeed2DV_; }
  float dotprodTrackSeed3D() const { return dotprodTrackSeed3D_; }
  float dotprodTrackSeed3DV() const { return dotprodTrackSeed3DV_; }
  float pca_jetAxis_dist() const { return pca_jetAxis_dist_; }
  float pca_jetAxis_dotprod() const { return pca_jetAxis_dotprod_; }
  float pca_jetAxis_dEta() const { return pca_jetAxis_dEta_; }
  float pca_jetAxis_dPhi() const { return pca_jetAxis_dPhi_; }
  float pfcand_dist_vtx_12() const { return pfcand_dist_vtx_12_; }

private:
  float pca_distance_;
  float pca_significance_;
  float pcaSeed_x_;
  float pcaSeed_y_;
  float pcaSeed_z_;
  float pcaSeed_xerr_;
  float pcaSeed_yerr_;
  float pcaSeed_zerr_;
  float pcaTrack_x_;
  float pcaTrack_y_;
  float pcaTrack_z_;
  float pcaTrack_xerr_;
  float pcaTrack_yerr_;
  float pcaTrack_zerr_;
  float dotprodTrack_;
  float dotprodSeed_;
  float pcaSeed_dist_;
  float pcaTrack_dist_;
  float dotprodTrackSeed2D_;
  float dotprodTrackSeed2DV_;
  float dotprodTrackSeed3D_;
  float dotprodTrackSeed3DV_;
  float pca_jetAxis_dist_;
  float pca_jetAxis_dotprod_;
  float pca_jetAxis_dEta_;
  float pca_jetAxis_dPhi_;
  float pfcand_dist_vtx_12_;
};

inline Measurement1D vertexDxy(const reco::VertexCompositePtrCandidate &svcand, const reco::Vertex &pv) {
  VertexDistanceXY dist;
  reco::Vertex::CovarianceMatrix csv;
  svcand.fillVertexCovariance(csv);
  reco::Vertex svtx(svcand.vertex(), csv);
  return dist.distance(svtx, pv);
}

inline Measurement1D vertexD3d(const reco::VertexCompositePtrCandidate &svcand, const reco::Vertex &pv) {
  VertexDistance3D dist;
  reco::Vertex::CovarianceMatrix csv;
  svcand.fillVertexCovariance(csv);
  reco::Vertex svtx(svcand.vertex(), csv);
  return dist.distance(svtx, pv);
}

inline float vertexDdotP(const reco::VertexCompositePtrCandidate &sv, const reco::Vertex &pv) {
  reco::Candidate::Vector p = sv.momentum();
  reco::Candidate::Vector d(sv.vx() - pv.x(), sv.vy() - pv.y(), sv.vz() - pv.z());
  return p.Unit().Dot(d.Unit());
}

}  // namespace

class ChargeNtupleProducer : public edm::one::EDAnalyzer<edm::one::SharedResources> {
public:
  explicit ChargeNtupleProducer(const edm::ParameterSet &);
  ~ChargeNtupleProducer() override = default;

  void beginJob() override;
  void analyze(const edm::Event &, const edm::EventSetup &) override;

private:
  bool passHLT(const edm::Event &);
  bool passJetId(const pat::Jet &) const;

  edm::EDGetTokenT<edm::View<pat::Jet>> jetsToken_;
  edm::EDGetTokenT<edm::View<pat::Jet>> jetsPuppiToken_;
  edm::EDGetTokenT<edm::View<pat::Muon>> muonsToken_;
  edm::EDGetTokenT<edm::View<pat::Electron>> electronsToken_;
  edm::EDGetTokenT<pat::METCollection> metsToken_;
  edm::EDGetTokenT<reco::VertexCollection> verticesToken_;
  edm::EDGetTokenT<reco::VertexCompositePtrCandidateCollection> secVerticesToken_;
  edm::EDGetTokenT<reco::GenParticleCollection> genParticlesToken_;
  edm::EDGetTokenT<reco::GenParticleCollection> prunedGenParticlesToken_;
  edm::EDGetTokenT<GenEventInfoProduct> genInfoToken_;
  edm::EDGetTokenT<std::vector<PileupSummaryInfo>> pileupToken_;
  edm::EDGetTokenT<LHEEventProduct> lheToken_;
  edm::EDGetTokenT<float> prefireWeightToken_;
  edm::EDGetTokenT<float> prefireWeightUpToken_;
  edm::EDGetTokenT<float> prefireWeightDownToken_;
  edm::EDGetTokenT<pat::TauCollection> tausToken_;
  edm::EDGetTokenT<double> rhoToken_;
  edm::EDGetTokenT<edm::TriggerResults> triggerToken_;
  edm::ESGetToken<TransientTrackBuilder, TransientTrackRecord> trackBuilderToken_;

  bool applyHLT_;
  std::vector<std::string> hltPaths_;
  std::vector<int> hlt_bits_;

  unsigned int minNJets_;
  double jetMinPt_;
  double jetMaxEta_;
  std::string jetId_;
  bool usePuppiJets_;
  std::string tagInfoName_;

  std::string leptonMode_;
  double muonMinPt_;
  double muonMaxEta_;
  double electronMinPt_;
  double electronMaxEta_;
  double tauMinPt_;
  double tauMaxEta_;
  double minCandidatePt_;
  double jetRadius_;
  unsigned int maxCpfCandidates_;
  unsigned int maxNpfCandidates_;
  unsigned int maxSvCandidates_;
  unsigned int maxPairwiseCandidates_;

  std::string puWeightsFile_;
  std::string puWeightsHist_;
  std::string puWeightsUpHist_;
  std::string puWeightsDownHist_;
  std::unique_ptr<TH1> puWeights_;
  std::unique_ptr<TH1> puWeightsUp_;
  std::unique_ptr<TH1> puWeightsDown_;

  TTree *tree_;
  TH1I *cutflow_;

  uint32_t run_;
  uint32_t lumi_;
  uint64_t event_;
  int npv_;
  float rho_;
  bool pass_hlt_;
  int nJetSel_;
  int nMuonSel_;
  int nElectronSel_;
  int nTauSel_;
  float met_pt_;
  float met_phi_;
  float met_sumEt_;
  float top_mass_proxy_;
  float genWeight_;
  float puWeight_;
  float puWeightUp_;
  float puWeightDown_;
  float pu_nTrueInt_;
  float prefireWeight_;
  float prefireWeightUp_;
  float prefireWeightDown_;
  std::vector<float> lheWeights_;
  std::vector<std::string> lheWeightIds_;
  std::vector<float> pdfWeights_;
  std::vector<std::string> pdfWeightIds_;
  float lepton_pt_;
  float lepton_eta_;
  float lepton_phi_;
  float lepton_mass_;
  int lepton_charge_;
  int lepton_pdgid_;
  std::vector<float> muon_pt_;
  std::vector<float> muon_eta_;
  std::vector<float> muon_phi_;
  std::vector<float> muon_mass_;
  std::vector<int> muon_charge_;
  std::vector<float> muon_relIso04_;
  std::vector<int> muon_isLoose_;
  std::vector<int> muon_isMedium_;
  std::vector<int> muon_isTight_;
  std::vector<float> electron_pt_;
  std::vector<float> electron_eta_;
  std::vector<float> electron_phi_;
  std::vector<float> electron_mass_;
  std::vector<int> electron_charge_;
  std::vector<float> electron_relIso03_;
  std::vector<int> electron_isEB_;
  std::vector<int> electron_cutBased_;
  std::vector<float> tau_pt_;
  std::vector<float> tau_eta_;
  std::vector<float> tau_phi_;
  std::vector<float> tau_mass_;
  std::vector<int> tau_charge_;
  std::vector<int> tau_decayMode_;
  std::vector<float> tau_idDecayModeNewDMs_;
  std::vector<float> tau_idDeepTauVSjet_;
  std::vector<float> tau_idDeepTauVSe_;
  std::vector<float> tau_idDeepTauVSmu_;
  std::vector<float> tau_rawDeepTauVSjet_;
  std::vector<float> tau_rawDeepTauVSe_;
  std::vector<float> tau_rawDeepTauVSmu_;
  std::vector<float> jet_pt_;
  std::vector<float> jet_eta_;
  std::vector<float> jet_phi_;
  std::vector<float> jet_mass_;
  std::vector<float> charged_fraction_;
  std::vector<float> neutral_fraction_;
  std::vector<float> jet_charge_k03_;
  std::vector<float> jet_charge_k05_;
  std::vector<float> jet_charge_k10_;
  std::vector<float> jet_charge_k20_;
  std::vector<int> n_Cpfcand_;
  std::vector<int> n_Npfcand_;
  std::vector<int> nsv_;
  std::vector<float> jet_partonFlavour_;
  std::vector<float> jet_btagDeepCSV_probb_;
  std::vector<float> jet_btagDeepCSV_probbb_;
  std::vector<float> jet_btagDeepCSV_probc_;
  std::vector<float> jet_btagDeepCSV_probudsg_;
  std::vector<float> jet_btagDeepB_;
  std::vector<float> jet_btagDeepC_;
  std::vector<float> jet_btagPNetB_;
  std::vector<float> jet_btagPNetCvB_;
  std::vector<float> jet_btagPNetCvL_;
  std::vector<float> jet_btagPNetQvG_;
  std::vector<float> jet_pnet_BvsAll_;
  std::vector<float> jet_pnet_CvsB_;
  std::vector<float> jet_pnet_CvsL_;
  std::vector<float> jet_pnet_QvsG_;
  std::vector<float> jet_pnet_TauVsEle_;
  std::vector<float> jet_pnet_TauVsJet_;
  std::vector<float> jet_pnet_TauVsMu_;
  std::vector<float> jet_pnet_probb_;
  std::vector<float> jet_pnet_probc_;
  std::vector<float> jet_pnet_probele_;
  std::vector<float> jet_pnet_probg_;
  std::vector<float> jet_pnet_probmu_;
  std::vector<float> jet_pnet_probtaum1h0p_;
  std::vector<float> jet_pnet_probtaum1h1p_;
  std::vector<float> jet_pnet_probtaum1h2p_;
  std::vector<float> jet_pnet_probtaum3h0p_;
  std::vector<float> jet_pnet_probtaum3h1p_;
  std::vector<float> jet_pnet_probtaup1h0p_;
  std::vector<float> jet_pnet_probtaup1h1p_;
  std::vector<float> jet_pnet_probtaup1h2p_;
  std::vector<float> jet_pnet_probtaup3h0p_;
  std::vector<float> jet_pnet_probtaup3h1p_;
  std::vector<float> jet_pnet_probuds_;
  std::vector<float> jet_pnet_ptcorr_;
  std::vector<float> jet_pnet_ptnu_;
  std::vector<float> jet_pnet_ptreshigh_;
  std::vector<float> jet_pnet_ptreslow_;
  std::vector<float> jet_btagRobustParTAK4B_;
  std::vector<float> jet_btagRobustParTAK4CvB_;
  std::vector<float> jet_btagRobustParTAK4CvL_;
  std::vector<float> jet_btagRobustParTAK4QG_;
  std::vector<float> jet_ParTPosvsAll_;
  std::vector<float> jet_ParTNegvsAll_;
  std::vector<float> jet_ParTZerovsAll_;
  std::vector<float> jet_ParTPosvsNeg_;
  std::vector<float> jet_charge_score_;
  std::vector<float> jet_pflavCharge_;
  std::vector<float> jet_hflav_;
  std::vector<float> jet_CHS_pt_;
  std::vector<float> jet_CHS_eta_;
  std::vector<float> jet_CHS_phi_;
  std::vector<float> jet_CHS_mass_;
  std::vector<float> jet_CHS_charged_fraction_;
  std::vector<float> jet_CHS_neutral_fraction_;
  std::vector<float> jet_CHS_charge_k03_;
  std::vector<float> jet_CHS_charge_k05_;
  std::vector<float> jet_CHS_charge_k10_;
  std::vector<float> jet_CHS_charge_k20_;
  std::vector<float> jet_CHS_partonFlavour_;
  std::vector<float> jet_CHS_pflavCharge_;
  std::vector<float> jet_CHS_hflav_;
  std::vector<std::string> btagLabels_;
  std::vector<std::string> btagLabelsCHS_;
  std::vector<std::vector<float>> btagValues_;
  std::vector<std::vector<float>> btagValuesCHS_;
  std::vector<float> hadron_species_;
  std::vector<float> hadron_species_pdgid_;
  std::vector<float> hadron_species_fallback_pdgid_;
  std::vector<float> hadron_charge_;
  std::vector<float> hadron_mixing_;
  std::vector<float> isB_;
  std::vector<float> isBB_;
  std::vector<float> isGBB_;
  std::vector<float> isLeptonicB_;
  std::vector<float> isLeptonicB_C_;
  std::vector<float> isC_;
  std::vector<float> isCC_;
  std::vector<float> isGCC_;
  std::vector<float> isU_;
  std::vector<float> isD_;
  std::vector<float> isS_;
  std::vector<float> isG_;
  std::vector<float> TagVarCSV_trackSumJetEtRatio_;
  std::vector<float> TagVarCSV_trackSumJetDeltaR_;
  std::vector<float> TagVarCSV_vertexCategory_;
  std::vector<float> TagVarCSV_trackSip2dValAboveCharm_;
  std::vector<float> TagVarCSV_trackSip2dSigAboveCharm_;
  std::vector<float> TagVarCSV_trackSip3dValAboveCharm_;
  std::vector<float> TagVarCSV_trackSip3dSigAboveCharm_;
  std::vector<float> TagVarCSV_jetNSelectedTracks_;
  std::vector<float> TagVarCSV_jetNTracksEtaRel_;
  std::vector<int> n_Cpfpairs_;
  std::vector<float> nCpfpairs_;
  std::vector<int> has_soft_mu_;
  std::vector<float> soft_mu_charge_;
  std::vector<float> soft_mu_ptrel_;
  std::vector<float> soft_mu_ip_sig_;
  std::vector<float> soft_mu_dR_jet_;
  std::vector<float> mass_2trk_pi_;
  std::vector<float> mass_2trk_kpi_;
  std::vector<float> mass_3trk_pi_;
  std::vector<float> mass_3trk_kpipi_;
  std::vector<float> mass_2trk_pi_pi0_;
  std::vector<float> mass_2trk_kpi_pi0_;
  std::vector<float> mass_3trk_pi_pi0_;
  std::vector<float> mass_3trk_kpipi_pi0_;
  std::vector<float> pi0_mass_;
  std::vector<float> pi0_pt_;
  std::vector<int> pi0_found_;
  std::vector<int> hadPi0_;
  std::vector<int> nPi0_;

  std::vector<float> Cpfcan_eta_;
  std::vector<float> Cpfcan_phi_;
  std::vector<float> Cpfcan_BtagPf_trackEtaRel_;
  std::vector<float> Cpfcan_BtagPf_trackPtRel_;
  std::vector<float> Cpfcan_BtagPf_trackPPar_;
  std::vector<float> Cpfcan_BtagPf_trackDeltaR_;
  std::vector<float> Cpfcan_BtagPf_trackPParRatio_;
  std::vector<float> Cpfcan_BtagPf_trackSip2dVal_;
  std::vector<float> Cpfcan_BtagPf_trackSip2dSig_;
  std::vector<float> Cpfcan_BtagPf_trackSip3dVal_;
  std::vector<float> Cpfcan_BtagPf_trackSip3dSig_;
  std::vector<float> Cpfcan_BtagPf_trackJetDistVal_;
  std::vector<float> Cpfcan_ptrel_;
  std::vector<float> Cpfcan_drminsv_;
  std::vector<float> Cpfcan_VTX_ass_;
  std::vector<float> Cpfcan_fromPV_;
  std::vector<float> Cpfcan_puppiw_;
  std::vector<float> Cpfcan_chi2_;
  std::vector<float> Cpfcan_quality_;
  std::vector<float> Cpfcan_pt_;
  std::vector<float> Cpfcan_charge_;
  std::vector<float> Cpfcan_dz_;
  std::vector<float> Cpfcan_dxy_;
  std::vector<float> Cpfcan_dxysig_;
  std::vector<float> Cpfcan_BtagPf_trackDecayLen_;
  std::vector<float> Cpfcan_HadFrac_;
  std::vector<float> Cpfcan_CaloFrac_;
  std::vector<float> Cpfcan_pdgID_;
  std::vector<float> Cpfcan_lostInnerHits_;
  std::vector<float> Cpfcan_numberOfPixelHits_;
  std::vector<float> Cpfcan_numberOfStripHits_;
  std::vector<float> Cpfcan_tau_signal_;
  std::vector<float> Cpfcan_px_;
  std::vector<float> Cpfcan_py_;
  std::vector<float> Cpfcan_pz_;
  std::vector<float> Cpfcan_e_;
  std::vector<float> Cpfcan_isKaon_;
  std::vector<float> Cpfcan_kaon_genCharge_;
  std::vector<float> Cpfcan_kaon_motherPdgId_;
  std::vector<float> Cpfcan_kaon_motherCharge_;

  std::vector<float> Npfcan_pt_;
  std::vector<float> Npfcan_ptrel_;
  std::vector<float> Npfcan_etarel_;
  std::vector<float> Npfcan_phirel_;
  std::vector<float> Npfcan_deltaR_;
  std::vector<float> Npfcan_isGamma_;
  std::vector<float> Npfcan_HadFrac_;
  std::vector<float> Npfcan_drminsv_;
  std::vector<float> Npfcan_puppiw_;
  std::vector<float> Npfcan_tau_signal_;
  std::vector<float> Npfcan_px_;
  std::vector<float> Npfcan_py_;
  std::vector<float> Npfcan_pz_;
  std::vector<float> Npfcan_e_;

  std::vector<float> sv_pt_;
  std::vector<float> sv_deltaR_;
  std::vector<float> sv_mass_;
  std::vector<float> sv_ntracks_;
  std::vector<float> sv_etarel_;
  std::vector<float> sv_phirel_;
  std::vector<float> sv_chi2_;
  std::vector<float> sv_normchi2_;
  std::vector<float> sv_dxy_;
  std::vector<float> sv_dxysig_;
  std::vector<float> sv_d3d_;
  std::vector<float> sv_d3dsig_;
  std::vector<float> sv_costhetasvpv_;
  std::vector<float> sv_enratio_;
  std::vector<float> sv_charge_sum_;
  std::vector<float> sv_px_;
  std::vector<float> sv_py_;
  std::vector<float> sv_pz_;
  std::vector<float> sv_e_;

  std::vector<float> pair_pca_distance_;
  std::vector<float> pair_pca_significance_;
  std::vector<float> pair_pcaSeed_x1_;
  std::vector<float> pair_pcaSeed_y1_;
  std::vector<float> pair_pcaSeed_z1_;
  std::vector<float> pair_pcaSeed_x2_;
  std::vector<float> pair_pcaSeed_y2_;
  std::vector<float> pair_pcaSeed_z2_;
  std::vector<float> pair_pcaSeed_xerr1_;
  std::vector<float> pair_pcaSeed_yerr1_;
  std::vector<float> pair_pcaSeed_zerr1_;
  std::vector<float> pair_pcaSeed_xerr2_;
  std::vector<float> pair_pcaSeed_yerr2_;
  std::vector<float> pair_pcaSeed_zerr2_;
  std::vector<float> pair_dotprod1_;
  std::vector<float> pair_dotprod2_;
  std::vector<float> pair_pca_dist1_;
  std::vector<float> pair_pca_dist2_;
  std::vector<float> pair_dotprod12_2D_;
  std::vector<float> pair_dotprod12_2DV_;
  std::vector<float> pair_dotprod12_3D_;
  std::vector<float> pair_dotprod12_3DV_;
  std::vector<float> pair_pca_jetAxis_dist_;
  std::vector<float> pair_pca_jetAxis_dotprod_;
  std::vector<float> pair_pca_jetAxis_dEta_;
  std::vector<float> pair_pca_jetAxis_dPhi_;
  std::vector<float> pfcand_dist_vtx_12_;
};

ChargeNtupleProducer::ChargeNtupleProducer(const edm::ParameterSet &cfg)
    : jetsToken_(consumes<edm::View<pat::Jet>>(cfg.getParameter<edm::InputTag>("jets"))),
      jetsPuppiToken_(consumes<edm::View<pat::Jet>>(cfg.getParameter<edm::InputTag>("jetsPuppi"))),
      muonsToken_(consumes<edm::View<pat::Muon>>(cfg.getParameter<edm::InputTag>("muons"))),
      electronsToken_(consumes<edm::View<pat::Electron>>(cfg.getParameter<edm::InputTag>("electrons"))),
      metsToken_(consumes<pat::METCollection>(cfg.getParameter<edm::InputTag>("mets"))),
      verticesToken_(consumes<reco::VertexCollection>(cfg.getParameter<edm::InputTag>("vertices"))),
      secVerticesToken_(consumes<reco::VertexCompositePtrCandidateCollection>(
          cfg.getParameter<edm::InputTag>("secondaryVertices"))),
      genParticlesToken_(consumes<reco::GenParticleCollection>(
          cfg.getParameter<edm::InputTag>("genParticles"))),
      prunedGenParticlesToken_(consumes<reco::GenParticleCollection>(
          cfg.getParameter<edm::InputTag>("prunedGenParticles"))),
      genInfoToken_(consumes<GenEventInfoProduct>(cfg.getParameter<edm::InputTag>("genEventInfo"))),
      pileupToken_(consumes<std::vector<PileupSummaryInfo>>(cfg.getParameter<edm::InputTag>("pileupSummary"))),
      lheToken_(consumes<LHEEventProduct>(cfg.getParameter<edm::InputTag>("lheEvent"))),
      prefireWeightToken_(consumes<float>(cfg.getParameter<edm::InputTag>("prefireWeight"))),
      prefireWeightUpToken_(consumes<float>(cfg.getParameter<edm::InputTag>("prefireWeightUp"))),
      prefireWeightDownToken_(consumes<float>(cfg.getParameter<edm::InputTag>("prefireWeightDown"))),
      tausToken_(consumes<pat::TauCollection>(cfg.getParameter<edm::InputTag>("taus"))),
      rhoToken_(consumes<double>(cfg.getParameter<edm::InputTag>("rho"))),
      triggerToken_(consumes<edm::TriggerResults>(cfg.getParameter<edm::InputTag>("triggerResults"))),
      trackBuilderToken_(
          esConsumes<TransientTrackBuilder, TransientTrackRecord>(edm::ESInputTag("", "TransientTrackBuilder"))),
      applyHLT_(cfg.getParameter<bool>("applyHLT")),
      hltPaths_(cfg.getParameter<std::vector<std::string>>("hltPaths")),
      minNJets_(cfg.getParameter<unsigned int>("minNJets")),
      jetMinPt_(cfg.getParameter<double>("jetMinPt")),
      jetMaxEta_(cfg.getParameter<double>("jetMaxEta")),
      jetId_(cfg.getParameter<std::string>("jetId")),
      usePuppiJets_(cfg.getParameter<bool>("usePuppiJets")),
      tagInfoName_(cfg.getParameter<std::string>("tagInfoName")),
      leptonMode_(cfg.getParameter<std::string>("leptonMode")),
      muonMinPt_(cfg.getParameter<double>("muonMinPt")),
      muonMaxEta_(cfg.getParameter<double>("muonMaxEta")),
      electronMinPt_(cfg.getParameter<double>("electronMinPt")),
      electronMaxEta_(cfg.getParameter<double>("electronMaxEta")),
      tauMinPt_(cfg.getParameter<double>("tauMinPt")),
      tauMaxEta_(cfg.getParameter<double>("tauMaxEta")),
      minCandidatePt_(cfg.getParameter<double>("minCandidatePt")),
      jetRadius_(cfg.getParameter<double>("jetRadius")),
      maxCpfCandidates_(cfg.getParameter<unsigned int>("maxCpfCandidates")),
      maxNpfCandidates_(cfg.getParameter<unsigned int>("maxNpfCandidates")),
      maxSvCandidates_(cfg.getParameter<unsigned int>("maxSvCandidates")),
      maxPairwiseCandidates_(cfg.getParameter<unsigned int>("maxPairwiseCandidates")),
      puWeightsFile_(cfg.getParameter<std::string>("puWeightsFile")),
      puWeightsHist_(cfg.getParameter<std::string>("puWeightsHist")),
      puWeightsUpHist_(cfg.getParameter<std::string>("puWeightsUpHist")),
      puWeightsDownHist_(cfg.getParameter<std::string>("puWeightsDownHist")),
      tree_(nullptr),
      cutflow_(nullptr),
      run_(0),
      lumi_(0),
      event_(0),
      npv_(0),
      rho_(0.0f),
      pass_hlt_(false),
      nJetSel_(0),
      nMuonSel_(0),
      nElectronSel_(0),
      nTauSel_(0),
      met_pt_(0.0f),
      met_phi_(0.0f),
      met_sumEt_(0.0f),
      top_mass_proxy_(0.0f),
      genWeight_(1.0f),
      puWeight_(1.0f),
      puWeightUp_(1.0f),
      puWeightDown_(1.0f),
      pu_nTrueInt_(-1.0f),
      prefireWeight_(1.0f),
      prefireWeightUp_(1.0f),
      prefireWeightDown_(1.0f),
      btagLabels_(cfg.getParameter<std::vector<std::string>>("btagDiscriminators")),
      btagLabelsCHS_(cfg.getParameter<std::vector<std::string>>("btagDiscriminatorsCHS")) {
  usesResource("TFileService");
  if (leptonMode_.empty()) {
    leptonMode_ = "hadronic";
  }

  if (!puWeightsFile_.empty() && !puWeightsHist_.empty()) {
    std::unique_ptr<TFile> weightFile(TFile::Open(puWeightsFile_.c_str(), "READ"));
    if (weightFile && !weightFile->IsZombie()) {
      if (auto *hist = weightFile->Get(puWeightsHist_.c_str())) {
        puWeights_.reset(static_cast<TH1 *>(hist->Clone()));
        puWeights_->SetDirectory(nullptr);
      }
      if (!puWeightsUpHist_.empty()) {
        if (auto *hist = weightFile->Get(puWeightsUpHist_.c_str())) {
          puWeightsUp_.reset(static_cast<TH1 *>(hist->Clone()));
          puWeightsUp_->SetDirectory(nullptr);
        }
      }
      if (!puWeightsDownHist_.empty()) {
        if (auto *hist = weightFile->Get(puWeightsDownHist_.c_str())) {
          puWeightsDown_.reset(static_cast<TH1 *>(hist->Clone()));
          puWeightsDown_->SetDirectory(nullptr);
        }
      }
    }
  }
}

void ChargeNtupleProducer::beginJob() {
  edm::Service<TFileService> fs;
  TFile &output_file = fs->file();
  output_file.cd();
  tree_ = new TTree("Events", "Events");
  tree_->SetDirectory(&output_file);
  tree_->Branch("run", &run_, "run/i");
  tree_->Branch("lumi", &lumi_, "lumi/i");
  tree_->Branch("event", &event_, "event/l");
  tree_->Branch("npv", &npv_, "npv/I");
  tree_->Branch("rho", &rho_, "rho/F");
  tree_->Branch("met_pt", &met_pt_, "met_pt/F");
  tree_->Branch("met_phi", &met_phi_, "met_phi/F");
  tree_->Branch("met_sumEt", &met_sumEt_, "met_sumEt/F");
  tree_->Branch("top_mass_proxy", &top_mass_proxy_, "top_mass_proxy/F");
  tree_->Branch("genWeight", &genWeight_, "genWeight/F");
  tree_->Branch("puWeight", &puWeight_, "puWeight/F");
  tree_->Branch("puWeightUp", &puWeightUp_, "puWeightUp/F");
  tree_->Branch("puWeightDown", &puWeightDown_, "puWeightDown/F");
  tree_->Branch("pu_nTrueInt", &pu_nTrueInt_, "pu_nTrueInt/F");
  tree_->Branch("prefireWeight", &prefireWeight_, "prefireWeight/F");
  tree_->Branch("prefireWeightUp", &prefireWeightUp_, "prefireWeightUp/F");
  tree_->Branch("prefireWeightDown", &prefireWeightDown_, "prefireWeightDown/F");
  tree_->Branch("lheWeights", &lheWeights_);
  tree_->Branch("lheWeightIds", &lheWeightIds_);
  tree_->Branch("pdfWeights", &pdfWeights_);
  tree_->Branch("pdfWeightIds", &pdfWeightIds_);
  tree_->Branch("lepton_pt", &lepton_pt_, "lepton_pt/F");
  tree_->Branch("lepton_eta", &lepton_eta_, "lepton_eta/F");
  tree_->Branch("lepton_phi", &lepton_phi_, "lepton_phi/F");
  tree_->Branch("lepton_mass", &lepton_mass_, "lepton_mass/F");
  tree_->Branch("lepton_charge", &lepton_charge_, "lepton_charge/I");
  tree_->Branch("lepton_pdgid", &lepton_pdgid_, "lepton_pdgid/I");
  tree_->Branch("muon_pt", &muon_pt_);
  tree_->Branch("muon_eta", &muon_eta_);
  tree_->Branch("muon_phi", &muon_phi_);
  tree_->Branch("muon_mass", &muon_mass_);
  tree_->Branch("muon_charge", &muon_charge_);
  tree_->Branch("muon_relIso04", &muon_relIso04_);
  tree_->Branch("muon_isLoose", &muon_isLoose_);
  tree_->Branch("muon_isMedium", &muon_isMedium_);
  tree_->Branch("muon_isTight", &muon_isTight_);
  tree_->Branch("electron_pt", &electron_pt_);
  tree_->Branch("electron_eta", &electron_eta_);
  tree_->Branch("electron_phi", &electron_phi_);
  tree_->Branch("electron_mass", &electron_mass_);
  tree_->Branch("electron_charge", &electron_charge_);
  tree_->Branch("electron_relIso03", &electron_relIso03_);
  tree_->Branch("electron_isEB", &electron_isEB_);
  tree_->Branch("electron_cutBased", &electron_cutBased_);
  tree_->Branch("tau_pt", &tau_pt_);
  tree_->Branch("tau_eta", &tau_eta_);
  tree_->Branch("tau_phi", &tau_phi_);
  tree_->Branch("tau_mass", &tau_mass_);
  tree_->Branch("tau_charge", &tau_charge_);
  tree_->Branch("tau_decayMode", &tau_decayMode_);
  tree_->Branch("tau_idDecayModeNewDMs", &tau_idDecayModeNewDMs_);
  tree_->Branch("tau_idDeepTauVSjet", &tau_idDeepTauVSjet_);
  tree_->Branch("tau_idDeepTauVSe", &tau_idDeepTauVSe_);
  tree_->Branch("tau_idDeepTauVSmu", &tau_idDeepTauVSmu_);
  tree_->Branch("tau_rawDeepTauVSjet", &tau_rawDeepTauVSjet_);
  tree_->Branch("tau_rawDeepTauVSe", &tau_rawDeepTauVSe_);
  tree_->Branch("tau_rawDeepTauVSmu", &tau_rawDeepTauVSmu_);

  hlt_bits_.assign(hltPaths_.size(), 0);
  for (size_t i = 0; i < hltPaths_.size(); ++i) {
    std::string branch_name = hltPaths_[i];
    bool needs_sanitize = branch_name.empty();
    for (char c : branch_name) {
      if (!isValidBranchChar(c)) {
        needs_sanitize = true;
        break;
      }
    }
    if (needs_sanitize || (!branch_name.empty() && std::isdigit(static_cast<unsigned char>(branch_name[0])))) {
      branch_name = "hlt_" + sanitizeBtagLabel(branch_name);
    }
    if (branch_name.empty()) {
      branch_name = "hlt_path_" + std::to_string(i);
    }
    std::string leaf = branch_name + "/I";
    tree_->Branch(branch_name.c_str(), &hlt_bits_[i], leaf.c_str());
  }
  tree_->Branch("pass_hlt", &pass_hlt_, "pass_hlt/O");
  tree_->Branch("nJetSel", &nJetSel_, "nJetSel/I");
  tree_->Branch("nMuonSel", &nMuonSel_, "nMuonSel/I");
  tree_->Branch("nElectronSel", &nElectronSel_, "nElectronSel/I");
  tree_->Branch("nTauSel", &nTauSel_, "nTauSel/I");
  tree_->Branch("jet_pt", &jet_pt_);
  tree_->Branch("jet_eta", &jet_eta_);
  tree_->Branch("jet_phi", &jet_phi_);
  tree_->Branch("jet_mass", &jet_mass_);
  tree_->Branch("charged_fraction", &charged_fraction_);
  tree_->Branch("neutral_fraction", &neutral_fraction_);
  tree_->Branch("jet_charge_k03", &jet_charge_k03_);
  tree_->Branch("jet_charge_k05", &jet_charge_k05_);
  tree_->Branch("jet_charge_k10", &jet_charge_k10_);
  tree_->Branch("jet_charge_k20", &jet_charge_k20_);
  tree_->Branch("n_Cpfcand", &n_Cpfcand_);
  tree_->Branch("n_Npfcand", &n_Npfcand_);
  tree_->Branch("nsv", &nsv_);
  tree_->Branch("jet_partonFlavour", &jet_partonFlavour_);
  tree_->Branch("jet_btagDeepCSV_probb", &jet_btagDeepCSV_probb_);
  tree_->Branch("jet_btagDeepCSV_probbb", &jet_btagDeepCSV_probbb_);
  tree_->Branch("jet_btagDeepCSV_probc", &jet_btagDeepCSV_probc_);
  tree_->Branch("jet_btagDeepCSV_probudsg", &jet_btagDeepCSV_probudsg_);
  tree_->Branch("jet_btagDeepB", &jet_btagDeepB_);
  tree_->Branch("jet_btagDeepC", &jet_btagDeepC_);
  tree_->Branch("jet_btagPNetB", &jet_btagPNetB_);
  tree_->Branch("jet_btagPNetCvB", &jet_btagPNetCvB_);
  tree_->Branch("jet_btagPNetCvL", &jet_btagPNetCvL_);
  tree_->Branch("jet_btagPNetQvG", &jet_btagPNetQvG_);
  tree_->Branch("jet_pnet_BvsAll", &jet_pnet_BvsAll_);
  tree_->Branch("jet_pnet_CvsB", &jet_pnet_CvsB_);
  tree_->Branch("jet_pnet_CvsL", &jet_pnet_CvsL_);
  tree_->Branch("jet_pnet_QvsG", &jet_pnet_QvsG_);
  tree_->Branch("jet_pnet_TauVsEle", &jet_pnet_TauVsEle_);
  tree_->Branch("jet_pnet_TauVsJet", &jet_pnet_TauVsJet_);
  tree_->Branch("jet_pnet_TauVsMu", &jet_pnet_TauVsMu_);
  tree_->Branch("jet_pnet_probb", &jet_pnet_probb_);
  tree_->Branch("jet_pnet_probc", &jet_pnet_probc_);
  tree_->Branch("jet_pnet_probele", &jet_pnet_probele_);
  tree_->Branch("jet_pnet_probg", &jet_pnet_probg_);
  tree_->Branch("jet_pnet_probmu", &jet_pnet_probmu_);
  tree_->Branch("jet_pnet_probtaum1h0p", &jet_pnet_probtaum1h0p_);
  tree_->Branch("jet_pnet_probtaum1h1p", &jet_pnet_probtaum1h1p_);
  tree_->Branch("jet_pnet_probtaum1h2p", &jet_pnet_probtaum1h2p_);
  tree_->Branch("jet_pnet_probtaum3h0p", &jet_pnet_probtaum3h0p_);
  tree_->Branch("jet_pnet_probtaum3h1p", &jet_pnet_probtaum3h1p_);
  tree_->Branch("jet_pnet_probtaup1h0p", &jet_pnet_probtaup1h0p_);
  tree_->Branch("jet_pnet_probtaup1h1p", &jet_pnet_probtaup1h1p_);
  tree_->Branch("jet_pnet_probtaup1h2p", &jet_pnet_probtaup1h2p_);
  tree_->Branch("jet_pnet_probtaup3h0p", &jet_pnet_probtaup3h0p_);
  tree_->Branch("jet_pnet_probtaup3h1p", &jet_pnet_probtaup3h1p_);
  tree_->Branch("jet_pnet_probuds", &jet_pnet_probuds_);
  tree_->Branch("jet_pnet_ptcorr", &jet_pnet_ptcorr_);
  tree_->Branch("jet_pnet_ptnu", &jet_pnet_ptnu_);
  tree_->Branch("jet_pnet_ptreshigh", &jet_pnet_ptreshigh_);
  tree_->Branch("jet_pnet_ptreslow", &jet_pnet_ptreslow_);
  tree_->Branch("jet_btagRobustParTAK4B", &jet_btagRobustParTAK4B_);
  tree_->Branch("jet_btagRobustParTAK4CvB", &jet_btagRobustParTAK4CvB_);
  tree_->Branch("jet_btagRobustParTAK4CvL", &jet_btagRobustParTAK4CvL_);
  tree_->Branch("jet_btagRobustParTAK4QG", &jet_btagRobustParTAK4QG_);
  tree_->Branch("jet_ParTPosvsAll", &jet_ParTPosvsAll_);
  tree_->Branch("jet_ParTNegvsAll", &jet_ParTNegvsAll_);
  tree_->Branch("jet_ParTZerovsAll", &jet_ParTZerovsAll_);
  tree_->Branch("jet_ParTPosvsNeg", &jet_ParTPosvsNeg_);
  tree_->Branch("jet_charge_score", &jet_charge_score_);
  tree_->Branch("jet_pflavCharge", &jet_pflavCharge_);
  tree_->Branch("jet_hflav", &jet_hflav_);
  tree_->Branch("jet_CHS_pt", &jet_CHS_pt_);
  tree_->Branch("jet_CHS_eta", &jet_CHS_eta_);
  tree_->Branch("jet_CHS_phi", &jet_CHS_phi_);
  tree_->Branch("jet_CHS_mass", &jet_CHS_mass_);
  tree_->Branch("jet_CHS_charged_fraction", &jet_CHS_charged_fraction_);
  tree_->Branch("jet_CHS_neutral_fraction", &jet_CHS_neutral_fraction_);
  tree_->Branch("jet_CHS_charge_k03", &jet_CHS_charge_k03_);
  tree_->Branch("jet_CHS_charge_k05", &jet_CHS_charge_k05_);
  tree_->Branch("jet_CHS_charge_k10", &jet_CHS_charge_k10_);
  tree_->Branch("jet_CHS_charge_k20", &jet_CHS_charge_k20_);
  tree_->Branch("jet_CHS_partonFlavour", &jet_CHS_partonFlavour_);
  tree_->Branch("jet_CHS_pflavCharge", &jet_CHS_pflavCharge_);
  tree_->Branch("jet_CHS_hflav", &jet_CHS_hflav_);

  btagValues_.resize(btagLabels_.size());
  for (size_t i = 0; i < btagLabels_.size(); ++i) {
    std::string branch_name = "jet_btag_" + sanitizeBtagLabel(btagLabels_[i]);
    tree_->Branch(branch_name.c_str(), &btagValues_[i]);
  }

  btagValuesCHS_.resize(btagLabelsCHS_.size());
  for (size_t i = 0; i < btagLabelsCHS_.size(); ++i) {
    std::string branch_name = "jet_CHS_btag_" + sanitizeBtagLabel(btagLabelsCHS_[i]);
    tree_->Branch(branch_name.c_str(), &btagValuesCHS_[i]);
  }
  tree_->Branch("hadron_species", &hadron_species_);
  tree_->Branch("hadron_species_pdgid", &hadron_species_pdgid_);
  tree_->Branch("hadron_species_fallback_pdgid", &hadron_species_fallback_pdgid_);
  tree_->Branch("hadron_charge", &hadron_charge_);
  tree_->Branch("hadron_mixing", &hadron_mixing_);
  tree_->Branch("isB", &isB_);
  tree_->Branch("isBB", &isBB_);
  tree_->Branch("isGBB", &isGBB_);
  tree_->Branch("isLeptonicB", &isLeptonicB_);
  tree_->Branch("isLeptonicB_C", &isLeptonicB_C_);
  tree_->Branch("isC", &isC_);
  tree_->Branch("isCC", &isCC_);
  tree_->Branch("isGCC", &isGCC_);
  tree_->Branch("isU", &isU_);
  tree_->Branch("isD", &isD_);
  tree_->Branch("isS", &isS_);
  tree_->Branch("isG", &isG_);
  tree_->Branch("TagVarCSV_trackSumJetEtRatio", &TagVarCSV_trackSumJetEtRatio_);
  tree_->Branch("TagVarCSV_trackSumJetDeltaR", &TagVarCSV_trackSumJetDeltaR_);
  tree_->Branch("TagVarCSV_vertexCategory", &TagVarCSV_vertexCategory_);
  tree_->Branch("TagVarCSV_trackSip2dValAboveCharm", &TagVarCSV_trackSip2dValAboveCharm_);
  tree_->Branch("TagVarCSV_trackSip2dSigAboveCharm", &TagVarCSV_trackSip2dSigAboveCharm_);
  tree_->Branch("TagVarCSV_trackSip3dValAboveCharm", &TagVarCSV_trackSip3dValAboveCharm_);
  tree_->Branch("TagVarCSV_trackSip3dSigAboveCharm", &TagVarCSV_trackSip3dSigAboveCharm_);
  tree_->Branch("TagVarCSV_jetNSelectedTracks", &TagVarCSV_jetNSelectedTracks_);
  tree_->Branch("TagVarCSV_jetNTracksEtaRel", &TagVarCSV_jetNTracksEtaRel_);
  tree_->Branch("n_Cpfpairs", &n_Cpfpairs_);
  tree_->Branch("nCpfpairs", &nCpfpairs_);
  tree_->Branch("has_soft_mu", &has_soft_mu_);
  tree_->Branch("soft_mu_charge", &soft_mu_charge_);
  tree_->Branch("soft_mu_ptrel", &soft_mu_ptrel_);
  tree_->Branch("soft_mu_ip_sig", &soft_mu_ip_sig_);
  tree_->Branch("soft_mu_dR_jet", &soft_mu_dR_jet_);
  tree_->Branch("mass_2trk_pi", &mass_2trk_pi_);
  tree_->Branch("mass_2trk_kpi", &mass_2trk_kpi_);
  tree_->Branch("mass_3trk_pi", &mass_3trk_pi_);
  tree_->Branch("mass_3trk_kpipi", &mass_3trk_kpipi_);
  tree_->Branch("mass_2trk_pi_pi0", &mass_2trk_pi_pi0_);
  tree_->Branch("mass_2trk_kpi_pi0", &mass_2trk_kpi_pi0_);
  tree_->Branch("mass_3trk_pi_pi0", &mass_3trk_pi_pi0_);
  tree_->Branch("mass_3trk_kpipi_pi0", &mass_3trk_kpipi_pi0_);
  tree_->Branch("pi0_mass", &pi0_mass_);
  tree_->Branch("pi0_pt", &pi0_pt_);
  tree_->Branch("pi0_found", &pi0_found_);
  tree_->Branch("hadPi0", &hadPi0_);
  tree_->Branch("nPi0", &nPi0_);

  tree_->Branch("Cpfcan_eta", &Cpfcan_eta_);
  tree_->Branch("Cpfcan_phi", &Cpfcan_phi_);
  tree_->Branch("Cpfcan_BtagPf_trackEtaRel", &Cpfcan_BtagPf_trackEtaRel_);
  tree_->Branch("Cpfcan_BtagPf_trackPtRel", &Cpfcan_BtagPf_trackPtRel_);
  tree_->Branch("Cpfcan_BtagPf_trackPPar", &Cpfcan_BtagPf_trackPPar_);
  tree_->Branch("Cpfcan_BtagPf_trackDeltaR", &Cpfcan_BtagPf_trackDeltaR_);
  tree_->Branch("Cpfcan_BtagPf_trackPParRatio", &Cpfcan_BtagPf_trackPParRatio_);
  tree_->Branch("Cpfcan_BtagPf_trackSip2dVal", &Cpfcan_BtagPf_trackSip2dVal_);
  tree_->Branch("Cpfcan_BtagPf_trackSip2dSig", &Cpfcan_BtagPf_trackSip2dSig_);
  tree_->Branch("Cpfcan_BtagPf_trackSip3dVal", &Cpfcan_BtagPf_trackSip3dVal_);
  tree_->Branch("Cpfcan_BtagPf_trackSip3dSig", &Cpfcan_BtagPf_trackSip3dSig_);
  tree_->Branch("Cpfcan_BtagPf_trackJetDistVal", &Cpfcan_BtagPf_trackJetDistVal_);
  tree_->Branch("Cpfcan_ptrel", &Cpfcan_ptrel_);
  tree_->Branch("Cpfcan_drminsv", &Cpfcan_drminsv_);
  tree_->Branch("Cpfcan_VTX_ass", &Cpfcan_VTX_ass_);
  tree_->Branch("Cpfcan_fromPV", &Cpfcan_fromPV_);
  tree_->Branch("Cpfcan_puppiw", &Cpfcan_puppiw_);
  tree_->Branch("Cpfcan_chi2", &Cpfcan_chi2_);
  tree_->Branch("Cpfcan_quality", &Cpfcan_quality_);
  tree_->Branch("Cpfcan_pt", &Cpfcan_pt_);
  tree_->Branch("Cpfcan_charge", &Cpfcan_charge_);
  tree_->Branch("Cpfcan_dz", &Cpfcan_dz_);
  tree_->Branch("Cpfcan_dxy", &Cpfcan_dxy_);
  tree_->Branch("Cpfcan_dxysig", &Cpfcan_dxysig_);
  tree_->Branch("Cpfcan_BtagPf_trackDecayLen", &Cpfcan_BtagPf_trackDecayLen_);
  tree_->Branch("Cpfcan_HadFrac", &Cpfcan_HadFrac_);
  tree_->Branch("Cpfcan_CaloFrac", &Cpfcan_CaloFrac_);
  tree_->Branch("Cpfcan_pdgID", &Cpfcan_pdgID_);
  tree_->Branch("Cpfcan_lostInnerHits", &Cpfcan_lostInnerHits_);
  tree_->Branch("Cpfcan_numberOfPixelHits", &Cpfcan_numberOfPixelHits_);
  tree_->Branch("Cpfcan_numberOfStripHits", &Cpfcan_numberOfStripHits_);
  tree_->Branch("Cpfcan_tau_signal", &Cpfcan_tau_signal_);
  tree_->Branch("Cpfcan_px", &Cpfcan_px_);
  tree_->Branch("Cpfcan_py", &Cpfcan_py_);
  tree_->Branch("Cpfcan_pz", &Cpfcan_pz_);
  tree_->Branch("Cpfcan_e", &Cpfcan_e_);
  tree_->Branch("Cpfcan_isKaon", &Cpfcan_isKaon_);
  tree_->Branch("Cpfcan_kaon_genCharge", &Cpfcan_kaon_genCharge_);
  tree_->Branch("Cpfcan_kaon_motherPdgId", &Cpfcan_kaon_motherPdgId_);
  tree_->Branch("Cpfcan_kaon_motherCharge", &Cpfcan_kaon_motherCharge_);

  tree_->Branch("Npfcan_pt", &Npfcan_pt_);
  tree_->Branch("Npfcan_ptrel", &Npfcan_ptrel_);
  tree_->Branch("Npfcan_etarel", &Npfcan_etarel_);
  tree_->Branch("Npfcan_phirel", &Npfcan_phirel_);
  tree_->Branch("Npfcan_deltaR", &Npfcan_deltaR_);
  tree_->Branch("Npfcan_isGamma", &Npfcan_isGamma_);
  tree_->Branch("Npfcan_HadFrac", &Npfcan_HadFrac_);
  tree_->Branch("Npfcan_drminsv", &Npfcan_drminsv_);
  tree_->Branch("Npfcan_puppiw", &Npfcan_puppiw_);
  tree_->Branch("Npfcan_tau_signal", &Npfcan_tau_signal_);
  tree_->Branch("Npfcan_px", &Npfcan_px_);
  tree_->Branch("Npfcan_py", &Npfcan_py_);
  tree_->Branch("Npfcan_pz", &Npfcan_pz_);
  tree_->Branch("Npfcan_e", &Npfcan_e_);

  tree_->Branch("sv_pt", &sv_pt_);
  tree_->Branch("sv_deltaR", &sv_deltaR_);
  tree_->Branch("sv_mass", &sv_mass_);
  tree_->Branch("sv_ntracks", &sv_ntracks_);
  tree_->Branch("sv_etarel", &sv_etarel_);
  tree_->Branch("sv_phirel", &sv_phirel_);
  tree_->Branch("sv_chi2", &sv_chi2_);
  tree_->Branch("sv_normchi2", &sv_normchi2_);
  tree_->Branch("sv_dxy", &sv_dxy_);
  tree_->Branch("sv_dxysig", &sv_dxysig_);
  tree_->Branch("sv_d3d", &sv_d3d_);
  tree_->Branch("sv_d3dsig", &sv_d3dsig_);
  tree_->Branch("sv_costhetasvpv", &sv_costhetasvpv_);
  tree_->Branch("sv_enratio", &sv_enratio_);
  tree_->Branch("sv_charge_sum", &sv_charge_sum_);
  tree_->Branch("sv_px", &sv_px_);
  tree_->Branch("sv_py", &sv_py_);
  tree_->Branch("sv_pz", &sv_pz_);
  tree_->Branch("sv_e", &sv_e_);

  tree_->Branch("pair_pca_distance", &pair_pca_distance_);
  tree_->Branch("pair_pca_significance", &pair_pca_significance_);
  tree_->Branch("pair_pcaSeed_x1", &pair_pcaSeed_x1_);
  tree_->Branch("pair_pcaSeed_y1", &pair_pcaSeed_y1_);
  tree_->Branch("pair_pcaSeed_z1", &pair_pcaSeed_z1_);
  tree_->Branch("pair_pcaSeed_x2", &pair_pcaSeed_x2_);
  tree_->Branch("pair_pcaSeed_y2", &pair_pcaSeed_y2_);
  tree_->Branch("pair_pcaSeed_z2", &pair_pcaSeed_z2_);
  tree_->Branch("pair_pcaSeed_xerr1", &pair_pcaSeed_xerr1_);
  tree_->Branch("pair_pcaSeed_yerr1", &pair_pcaSeed_yerr1_);
  tree_->Branch("pair_pcaSeed_zerr1", &pair_pcaSeed_zerr1_);
  tree_->Branch("pair_pcaSeed_xerr2", &pair_pcaSeed_xerr2_);
  tree_->Branch("pair_pcaSeed_yerr2", &pair_pcaSeed_yerr2_);
  tree_->Branch("pair_pcaSeed_zerr2", &pair_pcaSeed_zerr2_);
  tree_->Branch("pair_dotprod1", &pair_dotprod1_);
  tree_->Branch("pair_dotprod2", &pair_dotprod2_);
  tree_->Branch("pair_pca_dist1", &pair_pca_dist1_);
  tree_->Branch("pair_pca_dist2", &pair_pca_dist2_);
  tree_->Branch("pair_dotprod12_2D", &pair_dotprod12_2D_);
  tree_->Branch("pair_dotprod12_2DV", &pair_dotprod12_2DV_);
  tree_->Branch("pair_dotprod12_3D", &pair_dotprod12_3D_);
  tree_->Branch("pair_dotprod12_3DV", &pair_dotprod12_3DV_);
  tree_->Branch("pair_pca_jetAxis_dist", &pair_pca_jetAxis_dist_);
  tree_->Branch("pair_pca_jetAxis_dotprod", &pair_pca_jetAxis_dotprod_);
  tree_->Branch("pair_pca_jetAxis_dEta", &pair_pca_jetAxis_dEta_);
  tree_->Branch("pair_pca_jetAxis_dPhi", &pair_pca_jetAxis_dPhi_);
  tree_->Branch("pfcand_dist_vtx_12", &pfcand_dist_vtx_12_);

  cutflow_ = new TH1I("cutflow", "cutflow", 4, 0.5, 4.5);
  cutflow_->SetDirectory(&output_file);
  cutflow_->GetXaxis()->SetBinLabel(1, "total");
  cutflow_->GetXaxis()->SetBinLabel(2, "pass_hlt");
  cutflow_->GetXaxis()->SetBinLabel(3, "pass_objects");
  cutflow_->GetXaxis()->SetBinLabel(4, "written");
}

bool ChargeNtupleProducer::passJetId(const pat::Jet &jet) const {
  if (jetId_.empty()) {
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
    return jetId & (1 << 0);
  }
  if (jetId_ == "tight") {
    return jetId & (1 << 1);
  }
  if (jetId_ == "tightLepVeto") {
    return jetId & (1 << 2);
  }
  return true;
}

bool ChargeNtupleProducer::passHLT(const edm::Event &event) {
  edm::Handle<edm::TriggerResults> triggerResults;
  if (!hlt_bits_.empty()) {
    std::fill(hlt_bits_.begin(), hlt_bits_.end(), 0);
  }
  if (hltPaths_.empty()) {
    return true;
  }

  event.getByToken(triggerToken_, triggerResults);
  if (!triggerResults.isValid()) {
    return !applyHLT_;
  }

  const edm::TriggerNames &names = event.triggerNames(*triggerResults);
  bool any_passed = false;
  for (size_t idx = 0; idx < hltPaths_.size(); ++idx) {
    const auto &pattern = hltPaths_[idx];
    bool isPrefix = !pattern.empty() && pattern.back() == '*';
    std::string needle = isPrefix ? pattern.substr(0, pattern.size() - 1) : pattern;

    for (unsigned int i = 0; i < names.size(); ++i) {
      const std::string &name = names.triggerName(i);
      bool match = isPrefix ? (name.rfind(needle, 0) == 0) : (name == needle);
      if (match && triggerResults->accept(i)) {
        hlt_bits_[idx] = 1;
        any_passed = true;
        break;
      }
    }
  }
  if (applyHLT_) {
    return any_passed;
  }
  return true;
}

void ChargeNtupleProducer::analyze(const edm::Event &event, const edm::EventSetup &setup) {
  cutflow_->Fill(1);

  pass_hlt_ = passHLT(event);
  if (!pass_hlt_) {
    return;
  }
  cutflow_->Fill(2);

  const auto &trackBuilder = setup.getData(trackBuilderToken_);

  edm::Handle<edm::View<pat::Jet>> jets;
  edm::Handle<edm::View<pat::Jet>> jetsPuppi;
  edm::Handle<edm::View<pat::Muon>> muons;
  edm::Handle<edm::View<pat::Electron>> electrons;
  edm::Handle<pat::METCollection> mets;
  edm::Handle<pat::TauCollection> taus;
  edm::Handle<reco::VertexCollection> vertices;
  edm::Handle<reco::VertexCompositePtrCandidateCollection> secVertices;
  edm::Handle<reco::GenParticleCollection> genParticles;
  edm::Handle<reco::GenParticleCollection> prunedGenParticles;
  edm::Handle<GenEventInfoProduct> genInfo;
  edm::Handle<std::vector<PileupSummaryInfo>> pileupInfos;
  edm::Handle<LHEEventProduct> lheInfo;
  edm::Handle<float> prefireWeight;
  edm::Handle<float> prefireWeightUp;
  edm::Handle<float> prefireWeightDown;
  edm::Handle<double> rho;

  event.getByToken(jetsToken_, jets);
  event.getByToken(jetsPuppiToken_, jetsPuppi);
  event.getByToken(muonsToken_, muons);
  event.getByToken(electronsToken_, electrons);
  event.getByToken(metsToken_, mets);
  event.getByToken(tausToken_, taus);
  event.getByToken(verticesToken_, vertices);
  event.getByToken(secVerticesToken_, secVertices);
  event.getByToken(genParticlesToken_, genParticles);
  event.getByToken(prunedGenParticlesToken_, prunedGenParticles);
  event.getByToken(genInfoToken_, genInfo);
  event.getByToken(pileupToken_, pileupInfos);
  event.getByToken(lheToken_, lheInfo);
  event.getByToken(prefireWeightToken_, prefireWeight);
  event.getByToken(prefireWeightUpToken_, prefireWeightUp);
  event.getByToken(prefireWeightDownToken_, prefireWeightDown);
  event.getByToken(rhoToken_, rho);

  run_ = event.id().run();
  lumi_ = event.luminosityBlock();
  event_ = event.id().event();
  npv_ = vertices.isValid() ? static_cast<int>(vertices->size()) : 0;
  rho_ = rho.isValid() ? static_cast<float>(*rho) : 0.0f;
  met_pt_ = 0.0f;
  met_phi_ = 0.0f;
  met_sumEt_ = 0.0f;
  top_mass_proxy_ = 0.0f;
  if (mets.isValid() && !mets->empty()) {
    const auto &met = mets->front();
    met_pt_ = static_cast<float>(met.pt());
    met_phi_ = static_cast<float>(met.phi());
    met_sumEt_ = static_cast<float>(met.sumEt());
  }
  const reco::Vertex *primary_vertex = (vertices.isValid() && !vertices->empty()) ? &vertices->at(0) : nullptr;
  genWeight_ = genInfo.isValid() ? static_cast<float>(genInfo->weight()) : 1.0f;
  puWeight_ = 1.0f;
  puWeightUp_ = 1.0f;
  puWeightDown_ = 1.0f;
  pu_nTrueInt_ = -1.0f;
  if (pileupInfos.isValid()) {
    for (const auto &pu : *pileupInfos) {
      if (pu.getBunchCrossing() == 0) {
        pu_nTrueInt_ = static_cast<float>(pu.getTrueNumInteractions());
        break;
      }
    }
    if (puWeights_ && pu_nTrueInt_ >= 0.0f) {
      int bin = puWeights_->GetXaxis()->FindBin(pu_nTrueInt_);
      puWeight_ = static_cast<float>(puWeights_->GetBinContent(bin));
      if (puWeightsUp_) {
        puWeightUp_ = static_cast<float>(puWeightsUp_->GetBinContent(bin));
      } else {
        puWeightUp_ = puWeight_;
      }
      if (puWeightsDown_) {
        puWeightDown_ = static_cast<float>(puWeightsDown_->GetBinContent(bin));
      } else {
        puWeightDown_ = puWeight_;
      }
    }
  }
  prefireWeight_ = prefireWeight.isValid() ? *prefireWeight : 1.0f;
  prefireWeightUp_ = prefireWeightUp.isValid() ? *prefireWeightUp : 1.0f;
  prefireWeightDown_ = prefireWeightDown.isValid() ? *prefireWeightDown : 1.0f;
  lheWeights_.clear();
  lheWeightIds_.clear();
  pdfWeights_.clear();
  pdfWeightIds_.clear();
  if (lheInfo.isValid()) {
    for (const auto &w : lheInfo->weights()) {
      lheWeights_.push_back(static_cast<float>(w.wgt));
      lheWeightIds_.push_back(w.id);
      std::string id_lower = w.id;
      std::transform(id_lower.begin(), id_lower.end(), id_lower.begin(), [](unsigned char c) { return std::tolower(c); });
      if (id_lower.find("pdf") != std::string::npos) {
        pdfWeights_.push_back(static_cast<float>(w.wgt));
        pdfWeightIds_.push_back(w.id);
      }
    }
  }
  lepton_pt_ = 0.0f;
  lepton_eta_ = 0.0f;
  lepton_phi_ = 0.0f;
  lepton_mass_ = 0.0f;
  lepton_charge_ = 0;
  lepton_pdgid_ = 0;
  muon_pt_.clear();
  muon_eta_.clear();
  muon_phi_.clear();
  muon_mass_.clear();
  muon_charge_.clear();
  muon_relIso04_.clear();
  muon_isLoose_.clear();
  muon_isMedium_.clear();
  muon_isTight_.clear();
  electron_pt_.clear();
  electron_eta_.clear();
  electron_phi_.clear();
  electron_mass_.clear();
  electron_charge_.clear();
  electron_relIso03_.clear();
  electron_isEB_.clear();
  electron_cutBased_.clear();
  tau_pt_.clear();
  tau_eta_.clear();
  tau_phi_.clear();
  tau_mass_.clear();
  tau_charge_.clear();
  tau_decayMode_.clear();
  tau_idDecayModeNewDMs_.clear();
  tau_idDeepTauVSjet_.clear();
  tau_idDeepTauVSe_.clear();
  tau_idDeepTauVSmu_.clear();
  tau_rawDeepTauVSjet_.clear();
  tau_rawDeepTauVSe_.clear();
  tau_rawDeepTauVSmu_.clear();

  const edm::View<pat::Jet> *jets_view = jets.product();
  const bool default_is_puppi = (usePuppiJets_ && jetsPuppi.isValid() && !jetsPuppi->empty());
  if (default_is_puppi) {
    jets_view = jetsPuppi.product();
  }

  nMuonSel_ = 0;
  nTauSel_ = 0;
  float best_lepton_pt = -1.0f;
  if (muons.isValid()) {
    for (const auto &muon : *muons) {
      if (muon.pt() < muonMinPt_ || std::abs(muon.eta()) > muonMaxEta_) {
        continue;
      }
      ++nMuonSel_;
      muon_pt_.push_back(static_cast<float>(muon.pt()));
      muon_eta_.push_back(static_cast<float>(muon.eta()));
      muon_phi_.push_back(static_cast<float>(muon.phi()));
      muon_mass_.push_back(static_cast<float>(muon.mass()));
      muon_charge_.push_back(muon.charge());
      auto mu_iso = muon.pfIsolationR04();
      float mu_rel_iso = (mu_iso.sumChargedHadronPt +
                          std::max(0.0f, mu_iso.sumNeutralHadronEt + mu_iso.sumPhotonEt - 0.5f * mu_iso.sumPUPt)) /
                         muon.pt();
      muon_relIso04_.push_back(mu_rel_iso);
      muon_isLoose_.push_back(muon.isLooseMuon() ? 1 : 0);
      muon_isMedium_.push_back(muon.isMediumMuon() ? 1 : 0);
      bool is_tight = primary_vertex ? muon.isTightMuon(*primary_vertex) : false;
      muon_isTight_.push_back(is_tight ? 1 : 0);
      if (muon.pt() > best_lepton_pt) {
        best_lepton_pt = muon.pt();
        lepton_pt_ = muon.pt();
        lepton_eta_ = muon.eta();
        lepton_phi_ = muon.phi();
        lepton_mass_ = muon.mass();
        lepton_charge_ = muon.charge();
        lepton_pdgid_ = 13 * (muon.charge() > 0 ? -1 : 1);
      }
    }
  }

  nElectronSel_ = 0;
  if (electrons.isValid()) {
    for (const auto &electron : *electrons) {
      if (electron.pt() < electronMinPt_ || std::abs(electron.eta()) > electronMaxEta_) {
        continue;
      }
      ++nElectronSel_;
      electron_pt_.push_back(static_cast<float>(electron.pt()));
      electron_eta_.push_back(static_cast<float>(electron.eta()));
      electron_phi_.push_back(static_cast<float>(electron.phi()));
      electron_mass_.push_back(static_cast<float>(electron.mass()));
      electron_charge_.push_back(electron.charge());
      auto el_iso = electron.pfIsolationVariables();
      float el_rel_iso =
          (el_iso.sumChargedHadronPt +
           std::max(0.0f, el_iso.sumNeutralHadronEt + el_iso.sumPhotonEt - 0.5f * el_iso.sumPUPt)) /
          electron.pt();
      electron_relIso03_.push_back(el_rel_iso);
      electron_isEB_.push_back(electron.isEB() ? 1 : 0);
      int cutbased = -1;
      if (electron.hasUserInt("cutBased")) {
        cutbased = electron.userInt("cutBased");
      } else if (electron.hasUserFloat("cutBased")) {
        cutbased = static_cast<int>(electron.userFloat("cutBased"));
      }
      electron_cutBased_.push_back(cutbased);
      if (electron.pt() > best_lepton_pt) {
        best_lepton_pt = electron.pt();
        lepton_pt_ = electron.pt();
        lepton_eta_ = electron.eta();
        lepton_phi_ = electron.phi();
        lepton_mass_ = electron.mass();
        lepton_charge_ = electron.charge();
        lepton_pdgid_ = 11 * (electron.charge() > 0 ? -1 : 1);
      }
    }
  }

  bool passLeptons = true;
  if (leptonMode_ == "hadronic") {
    passLeptons = (nMuonSel_ == 0 && nElectronSel_ == 0);
  } else if (leptonMode_ == "single_muon") {
    passLeptons = (nMuonSel_ >= 1);
  } else if (leptonMode_ == "single_electron") {
    passLeptons = (nElectronSel_ >= 1);
  } else if (leptonMode_ == "single_lepton") {
    passLeptons = (nMuonSel_ + nElectronSel_ == 1);
  } else if (leptonMode_ == "at_least_one_lepton") {
    passLeptons = (nMuonSel_ + nElectronSel_ >= 1);
  } else if (leptonMode_ == "dilepton") {
    passLeptons = (nMuonSel_ + nElectronSel_ >= 2);
  }

  if (!passLeptons) {
    return;
  }

  jet_pt_.clear();
  jet_eta_.clear();
  jet_phi_.clear();
  jet_mass_.clear();
  charged_fraction_.clear();
  neutral_fraction_.clear();
  jet_charge_k03_.clear();
  jet_charge_k05_.clear();
  jet_charge_k10_.clear();
  jet_charge_k20_.clear();
  n_Cpfcand_.clear();
  n_Npfcand_.clear();
  nsv_.clear();
  jet_partonFlavour_.clear();
  jet_btagDeepCSV_probb_.clear();
  jet_btagDeepCSV_probbb_.clear();
  jet_btagDeepCSV_probc_.clear();
  jet_btagDeepCSV_probudsg_.clear();
  jet_btagDeepB_.clear();
  jet_btagDeepC_.clear();
  jet_btagPNetB_.clear();
  jet_btagPNetCvB_.clear();
  jet_btagPNetCvL_.clear();
  jet_btagPNetQvG_.clear();
  jet_pnet_BvsAll_.clear();
  jet_pnet_CvsB_.clear();
  jet_pnet_CvsL_.clear();
  jet_pnet_QvsG_.clear();
  jet_pnet_TauVsEle_.clear();
  jet_pnet_TauVsJet_.clear();
  jet_pnet_TauVsMu_.clear();
  jet_pnet_probb_.clear();
  jet_pnet_probc_.clear();
  jet_pnet_probele_.clear();
  jet_pnet_probg_.clear();
  jet_pnet_probmu_.clear();
  jet_pnet_probtaum1h0p_.clear();
  jet_pnet_probtaum1h1p_.clear();
  jet_pnet_probtaum1h2p_.clear();
  jet_pnet_probtaum3h0p_.clear();
  jet_pnet_probtaum3h1p_.clear();
  jet_pnet_probtaup1h0p_.clear();
  jet_pnet_probtaup1h1p_.clear();
  jet_pnet_probtaup1h2p_.clear();
  jet_pnet_probtaup3h0p_.clear();
  jet_pnet_probtaup3h1p_.clear();
  jet_pnet_probuds_.clear();
  jet_pnet_ptcorr_.clear();
  jet_pnet_ptnu_.clear();
  jet_pnet_ptreshigh_.clear();
  jet_pnet_ptreslow_.clear();
  jet_btagRobustParTAK4B_.clear();
  jet_btagRobustParTAK4CvB_.clear();
  jet_btagRobustParTAK4CvL_.clear();
  jet_btagRobustParTAK4QG_.clear();
  jet_ParTPosvsAll_.clear();
  jet_ParTNegvsAll_.clear();
  jet_ParTZerovsAll_.clear();
  jet_ParTPosvsNeg_.clear();
  jet_charge_score_.clear();
  jet_pflavCharge_.clear();
  jet_hflav_.clear();
  jet_CHS_pt_.clear();
  jet_CHS_eta_.clear();
  jet_CHS_phi_.clear();
  jet_CHS_mass_.clear();
  jet_CHS_charged_fraction_.clear();
  jet_CHS_neutral_fraction_.clear();
  jet_CHS_charge_k03_.clear();
  jet_CHS_charge_k05_.clear();
  jet_CHS_charge_k10_.clear();
  jet_CHS_charge_k20_.clear();
  jet_CHS_partonFlavour_.clear();
  jet_CHS_pflavCharge_.clear();
  jet_CHS_hflav_.clear();
  for (auto &values : btagValues_) {
    values.clear();
  }
  for (auto &values : btagValuesCHS_) {
    values.clear();
  }
  hadron_species_.clear();
  hadron_species_pdgid_.clear();
  hadron_species_fallback_pdgid_.clear();
  hadron_charge_.clear();
  hadron_mixing_.clear();
  isB_.clear();
  isBB_.clear();
  isGBB_.clear();
  isLeptonicB_.clear();
  isLeptonicB_C_.clear();
  isC_.clear();
  isCC_.clear();
  isGCC_.clear();
  isU_.clear();
  isD_.clear();
  isS_.clear();
  isG_.clear();
  TagVarCSV_trackSumJetEtRatio_.clear();
  TagVarCSV_trackSumJetDeltaR_.clear();
  TagVarCSV_vertexCategory_.clear();
  TagVarCSV_trackSip2dValAboveCharm_.clear();
  TagVarCSV_trackSip2dSigAboveCharm_.clear();
  TagVarCSV_trackSip3dValAboveCharm_.clear();
  TagVarCSV_trackSip3dSigAboveCharm_.clear();
  TagVarCSV_jetNSelectedTracks_.clear();
  TagVarCSV_jetNTracksEtaRel_.clear();
  n_Cpfpairs_.clear();
  nCpfpairs_.clear();
  has_soft_mu_.clear();
  soft_mu_charge_.clear();
  soft_mu_ptrel_.clear();
  soft_mu_ip_sig_.clear();
  soft_mu_dR_jet_.clear();
  mass_2trk_pi_.clear();
  mass_2trk_kpi_.clear();
  mass_3trk_pi_.clear();
  mass_3trk_kpipi_.clear();
  mass_2trk_pi_pi0_.clear();
  mass_2trk_kpi_pi0_.clear();
  mass_3trk_pi_pi0_.clear();
  mass_3trk_kpipi_pi0_.clear();
  pi0_mass_.clear();
  pi0_pt_.clear();
  pi0_found_.clear();
  hadPi0_.clear();
  nPi0_.clear();

  Cpfcan_eta_.clear();
  Cpfcan_phi_.clear();
  Cpfcan_BtagPf_trackEtaRel_.clear();
  Cpfcan_BtagPf_trackPtRel_.clear();
  Cpfcan_BtagPf_trackPPar_.clear();
  Cpfcan_BtagPf_trackDeltaR_.clear();
  Cpfcan_BtagPf_trackPParRatio_.clear();
  Cpfcan_BtagPf_trackSip2dVal_.clear();
  Cpfcan_BtagPf_trackSip2dSig_.clear();
  Cpfcan_BtagPf_trackSip3dVal_.clear();
  Cpfcan_BtagPf_trackSip3dSig_.clear();
  Cpfcan_BtagPf_trackJetDistVal_.clear();
  Cpfcan_ptrel_.clear();
  Cpfcan_drminsv_.clear();
  Cpfcan_VTX_ass_.clear();
  Cpfcan_fromPV_.clear();
  Cpfcan_puppiw_.clear();
  Cpfcan_chi2_.clear();
  Cpfcan_quality_.clear();
  Cpfcan_pt_.clear();
  Cpfcan_charge_.clear();
  Cpfcan_dz_.clear();
  Cpfcan_dxy_.clear();
  Cpfcan_dxysig_.clear();
  Cpfcan_BtagPf_trackDecayLen_.clear();
  Cpfcan_HadFrac_.clear();
  Cpfcan_CaloFrac_.clear();
  Cpfcan_pdgID_.clear();
  Cpfcan_lostInnerHits_.clear();
  Cpfcan_numberOfPixelHits_.clear();
  Cpfcan_numberOfStripHits_.clear();
  Cpfcan_tau_signal_.clear();
  Cpfcan_px_.clear();
  Cpfcan_py_.clear();
  Cpfcan_pz_.clear();
  Cpfcan_e_.clear();
  Cpfcan_isKaon_.clear();
  Cpfcan_kaon_genCharge_.clear();
  Cpfcan_kaon_motherPdgId_.clear();
  Cpfcan_kaon_motherCharge_.clear();

  Npfcan_pt_.clear();
  Npfcan_ptrel_.clear();
  Npfcan_etarel_.clear();
  Npfcan_phirel_.clear();
  Npfcan_deltaR_.clear();
  Npfcan_isGamma_.clear();
  Npfcan_HadFrac_.clear();
  Npfcan_drminsv_.clear();
  Npfcan_puppiw_.clear();
  Npfcan_tau_signal_.clear();
  Npfcan_px_.clear();
  Npfcan_py_.clear();
  Npfcan_pz_.clear();
  Npfcan_e_.clear();

  sv_pt_.clear();
  sv_deltaR_.clear();
  sv_mass_.clear();
  sv_ntracks_.clear();
  sv_etarel_.clear();
  sv_phirel_.clear();
  sv_chi2_.clear();
  sv_normchi2_.clear();
  sv_dxy_.clear();
  sv_dxysig_.clear();
  sv_d3d_.clear();
  sv_d3dsig_.clear();
  sv_costhetasvpv_.clear();
  sv_enratio_.clear();
  sv_charge_sum_.clear();
  sv_px_.clear();
  sv_py_.clear();
  sv_pz_.clear();
  sv_e_.clear();

  pair_pca_distance_.clear();
  pair_pca_significance_.clear();
  pair_pcaSeed_x1_.clear();
  pair_pcaSeed_y1_.clear();
  pair_pcaSeed_z1_.clear();
  pair_pcaSeed_x2_.clear();
  pair_pcaSeed_y2_.clear();
  pair_pcaSeed_z2_.clear();
  pair_pcaSeed_xerr1_.clear();
  pair_pcaSeed_yerr1_.clear();
  pair_pcaSeed_zerr1_.clear();
  pair_pcaSeed_xerr2_.clear();
  pair_pcaSeed_yerr2_.clear();
  pair_pcaSeed_zerr2_.clear();
  pair_dotprod1_.clear();
  pair_dotprod2_.clear();
  pair_pca_dist1_.clear();
  pair_pca_dist2_.clear();
  pair_dotprod12_2D_.clear();
  pair_dotprod12_2DV_.clear();
  pair_dotprod12_3D_.clear();
  pair_dotprod12_3DV_.clear();
  pair_pca_jetAxis_dist_.clear();
  pair_pca_jetAxis_dotprod_.clear();
  pair_pca_jetAxis_dEta_.clear();
  pair_pca_jetAxis_dPhi_.clear();
  pfcand_dist_vtx_12_.clear();

  std::vector<math::XYZTLorentzVector> tau_pfcandidates;
  if (taus.isValid()) {
    constexpr float min_pt_for_taus = 5.0f;
    constexpr float max_eta_for_taus = 2.5f;
    const std::string id_decay_mode_new = "decayModeFindingNewDMs";
    const std::string id_deeptau_vsjet = "byDeepTau2018v2p5VSjet";
    const std::string id_deeptau_vse = "byDeepTau2018v2p5VSe";
    const std::string id_deeptau_vsmu = "byDeepTau2018v2p5VSmu";
    const std::string id_deeptau_vsjet_raw = "byDeepTau2018v2p5VSjetraw";
    const std::string id_deeptau_vse_raw = "byDeepTau2018v2p5VSeraw";
    const std::string id_deeptau_vsmu_raw = "byDeepTau2018v2p5VSmuraw";
    for (const auto &tau : *taus) {
      bool pass_tau_sel = true;
      if (tau.pt() < tauMinPt_ || std::abs(tau.eta()) > tauMaxEta_) {
        pass_tau_sel = false;
      }
      if (pass_tau_sel) {
        ++nTauSel_;
        tau_pt_.push_back(static_cast<float>(tau.pt()));
        tau_eta_.push_back(static_cast<float>(tau.eta()));
        tau_phi_.push_back(static_cast<float>(tau.phi()));
        tau_mass_.push_back(static_cast<float>(tau.mass()));
        tau_charge_.push_back(tau.charge());
        tau_decayMode_.push_back(static_cast<int>(tau.decayMode()));
        tau_idDecayModeNewDMs_.push_back(getTauId(tau, id_decay_mode_new, -1.0f));
        tau_idDeepTauVSjet_.push_back(getTauId(tau, id_deeptau_vsjet, -1.0f));
        tau_idDeepTauVSe_.push_back(getTauId(tau, id_deeptau_vse, -1.0f));
        tau_idDeepTauVSmu_.push_back(getTauId(tau, id_deeptau_vsmu, -1.0f));
        tau_rawDeepTauVSjet_.push_back(getTauId(tau, id_deeptau_vsjet_raw, -1.0f));
        tau_rawDeepTauVSe_.push_back(getTauId(tau, id_deeptau_vse_raw, -1.0f));
        tau_rawDeepTauVSmu_.push_back(getTauId(tau, id_deeptau_vsmu_raw, -1.0f));
      }

      if (tau.pt() < min_pt_for_taus) {
        continue;
      }
      if (std::abs(tau.eta()) > max_eta_for_taus) {
        continue;
      }
      for (unsigned ipart = 0; ipart < tau.signalCands().size(); ++ipart) {
        const auto *cand = dynamic_cast<const pat::PackedCandidate *>(tau.signalCands()[ipart].get());
        if (!cand) {
          continue;
        }
        tau_pfcandidates.push_back(cand->p4());
      }
    }
  }

  if (jets_view) {
    const reco::Vertex *pv = (vertices.isValid() && !vertices->empty()) ? &vertices->at(0) : nullptr;
    const reco::Vertex dummy_vertex;
    const reco::Vertex &pv_ref = pv ? *pv : dummy_vertex;
    constexpr float kPionMass = 0.13957039f;
    constexpr float kKaonMass = 0.493677f;
    constexpr float kPi0Mass = 0.1349768f;
    constexpr float kPi0Window = 0.03f;
    const std::string pnet_disc_prefix = default_is_puppi
                                             ? "pfParticleNetFromMiniAODAK4PuppiCentralDiscriminatorsJetTags"
                                             : "pfParticleNetFromMiniAODAK4CHSCentralDiscriminatorsJetTags";
    const std::string pnet_tag_prefix = default_is_puppi ? "pfParticleNetFromMiniAODAK4PuppiCentralJetTags"
                                                         : "pfParticleNetFromMiniAODAK4CHSCentralJetTags";
    const std::string pnet_BvsAll_label = pnet_disc_prefix + ":BvsAll";
    const std::string pnet_CvsB_label = pnet_disc_prefix + ":CvsB";
    const std::string pnet_CvsL_label = pnet_disc_prefix + ":CvsL";
    const std::string pnet_QvsG_label = pnet_disc_prefix + ":QvsG";
    const std::string pnet_TauVsEle_label = pnet_disc_prefix + ":TauVsEle";
    const std::string pnet_TauVsJet_label = pnet_disc_prefix + ":TauVsJet";
    const std::string pnet_TauVsMu_label = pnet_disc_prefix + ":TauVsMu";
    const std::string pnet_probb_label = pnet_tag_prefix + ":probb";
    const std::string pnet_probc_label = pnet_tag_prefix + ":probc";
    const std::string pnet_probele_label = pnet_tag_prefix + ":probele";
    const std::string pnet_probg_label = pnet_tag_prefix + ":probg";
    const std::string pnet_probmu_label = pnet_tag_prefix + ":probmu";
    const std::string pnet_probtaum1h0p_label = pnet_tag_prefix + ":probtaum1h0p";
    const std::string pnet_probtaum1h1p_label = pnet_tag_prefix + ":probtaum1h1p";
    const std::string pnet_probtaum1h2p_label = pnet_tag_prefix + ":probtaum1h2p";
    const std::string pnet_probtaum3h0p_label = pnet_tag_prefix + ":probtaum3h0p";
    const std::string pnet_probtaum3h1p_label = pnet_tag_prefix + ":probtaum3h1p";
    const std::string pnet_probtaup1h0p_label = pnet_tag_prefix + ":probtaup1h0p";
    const std::string pnet_probtaup1h1p_label = pnet_tag_prefix + ":probtaup1h1p";
    const std::string pnet_probtaup1h2p_label = pnet_tag_prefix + ":probtaup1h2p";
    const std::string pnet_probtaup3h0p_label = pnet_tag_prefix + ":probtaup3h0p";
    const std::string pnet_probtaup3h1p_label = pnet_tag_prefix + ":probtaup3h1p";
    const std::string pnet_probuds_label = pnet_tag_prefix + ":probuds";
    const std::string pnet_ptcorr_label = pnet_tag_prefix + ":ptcorr";
    const std::string pnet_ptnu_label = pnet_tag_prefix + ":ptnu";
    const std::string pnet_ptreshigh_label = pnet_tag_prefix + ":ptreshigh";
    const std::string pnet_ptreslow_label = pnet_tag_prefix + ":ptreslow";
    for (const auto &jet : *jets_view) {
      if (jet.pt() < jetMinPt_ || std::abs(jet.eta()) > jetMaxEta_) {
        continue;
      }
      if (!passJetId(jet)) {
        continue;
      }

      jet_pt_.push_back(jet.pt());
      jet_eta_.push_back(jet.eta());
      jet_phi_.push_back(jet.phi());
      jet_mass_.push_back(jet.mass());

      float charged_frac = -1.0f;
      float neutral_frac = -1.0f;
      try {
        charged_frac = jet.chargedHadronEnergyFraction() + jet.chargedEmEnergyFraction();
        neutral_frac = jet.neutralHadronEnergyFraction() + jet.neutralEmEnergyFraction();
      } catch (...) {
        charged_frac = -1.0f;
        neutral_frac = -1.0f;
      }
      charged_fraction_.push_back(charged_frac);
      neutral_fraction_.push_back(neutral_frac);

      double charge_k03 = 0.0;
      double charge_k05 = 0.0;
      double charge_k10 = 0.0;
      double charge_k20 = 0.0;

      std::vector<const pat::PackedCandidate *> charged;
      std::vector<const pat::PackedCandidate *> photons;
      charged.reserve(jet.numberOfDaughters());
      photons.reserve(jet.numberOfDaughters());

      std::vector<SortEntry> sortedcharged;
      std::vector<SortEntry> sortedneutrals;
      sortedcharged.reserve(jet.numberOfDaughters());
      sortedneutrals.reserve(jet.numberOfDaughters());

      const auto &daughters = jet.daughterPtrVector();
      const float jet_uncorr_pt = jet.correctedJet("Uncorrected").pt();
      math::XYZVector jetDir = jet.momentum().Unit();
      GlobalVector jetRefTrackDir(jet.px(), jet.py(), jet.pz());

      auto mindrsvpfcand = [&](const pat::PackedCandidate *cand) -> float {
        float mindr = static_cast<float>(jetRadius_);
        if (!cand) {
          return mindr;
        }
        if (!secVertices.isValid()) {
          return mindr;
        }
        for (const auto &sv : *secVertices) {
          float dr = reco::deltaR(sv, *cand);
          if (dr < mindr) {
            mindr = dr;
          }
        }
        return mindr;
      };

      TrackInfoBuilder trackinfo(&trackBuilder);

      for (size_t i = 0; i < daughters.size(); ++i) {
        const auto &daughter = daughters[i];
        if (!daughter.isNonnull()) {
          continue;
        }
        const auto *packed = dynamic_cast<const pat::PackedCandidate *>(daughter.get());
        if (!packed) {
          continue;
        }
        if (packed->pt() < minCandidatePt_) {
          continue;
        }
        float drmin = mindrsvpfcand(packed);
        if (packed->charge() != 0) {
          double pt = packed->pt();
          double q = packed->charge();
          charge_k03 += q * std::pow(pt, 0.3);
          charge_k05 += q * std::pow(pt, 0.5);
          charge_k10 += q * std::pow(pt, 1.0);
          charge_k20 += q * std::pow(pt, 2.0);
          charged.push_back(packed);
          trackinfo.buildTrackInfo(packed, jetDir, jetRefTrackDir, pv_ref);
          sortedcharged.push_back({i,
                                   trackinfo.getTrackSip2dSig(),
                                   -drmin,
                                   static_cast<float>(packed->pt() / jet_uncorr_pt)});
        } else {
          if (std::abs(packed->pdgId()) == 22) {
            photons.push_back(packed);
          }
          sortedneutrals.push_back({i, -1.0f, -drmin, static_cast<float>(packed->pt() / jet_uncorr_pt)});
        }
      }

      if (jet.pt() > 0) {
        charge_k03 /= std::pow(jet.pt(), 0.3);
        charge_k05 /= std::pow(jet.pt(), 0.5);
        charge_k10 /= std::pow(jet.pt(), 1.0);
        charge_k20 /= std::pow(jet.pt(), 2.0);
      } else {
        charge_k03 = 0.0;
        charge_k05 = 0.0;
        charge_k10 = 0.0;
        charge_k20 = 0.0;
      }

      jet_charge_k03_.push_back(static_cast<float>(charge_k03));
      jet_charge_k05_.push_back(static_cast<float>(charge_k05));
      jet_charge_k10_.push_back(static_cast<float>(charge_k10));
      jet_charge_k20_.push_back(static_cast<float>(charge_k20));

      std::sort(sortedcharged.begin(), sortedcharged.end(), compareByABCInv);
      std::sort(sortedneutrals.begin(), sortedneutrals.end(), compareByABCInv);
      const size_t n_cpf = std::min(sortedcharged.size(), static_cast<size_t>(maxCpfCandidates_));
      const size_t n_npf = std::min(sortedneutrals.size(), static_cast<size_t>(maxNpfCandidates_));
      n_Cpfcand_.push_back(static_cast<int>(n_cpf));
      n_Npfcand_.push_back(static_cast<int>(n_npf));

      float tag_trackSumJetEtRatio = -1.0f;
      float tag_trackSumJetDeltaR = -1.0f;
      float tag_vertexCategory = -1.0f;
      float tag_trackSip2dValAboveCharm = -1.0f;
      float tag_trackSip2dSigAboveCharm = -1.0f;
      float tag_trackSip3dValAboveCharm = -1.0f;
      float tag_trackSip3dSigAboveCharm = -1.0f;
      float tag_jetNSelectedTracks = -1.0f;
      float tag_jetNTracksEtaRel = -1.0f;

      if (!tagInfoName_.empty()) {
        const auto *taginfo = dynamic_cast<const reco::ShallowTagInfo *>(jet.tagInfo(tagInfoName_));
        if (taginfo) {
          const reco::TaggingVariableList &tagvars = taginfo->taggingVariables();
          auto get_tagvar = [&](reco::btau::TaggingVariableName name, float fallback) -> float {
            return tagvars.get(name, fallback);
          };
          tag_trackSumJetEtRatio =
              get_tagvar(reco::btau::trackSumJetEtRatio, tag_trackSumJetEtRatio);
          tag_trackSumJetDeltaR =
              get_tagvar(reco::btau::trackSumJetDeltaR, tag_trackSumJetDeltaR);
          tag_vertexCategory = get_tagvar(reco::btau::vertexCategory, tag_vertexCategory);
          tag_trackSip2dValAboveCharm =
              get_tagvar(reco::btau::trackSip2dValAboveCharm, tag_trackSip2dValAboveCharm);
          tag_trackSip2dSigAboveCharm =
              get_tagvar(reco::btau::trackSip2dSigAboveCharm, tag_trackSip2dSigAboveCharm);
          tag_trackSip3dValAboveCharm =
              get_tagvar(reco::btau::trackSip3dValAboveCharm, tag_trackSip3dValAboveCharm);
          tag_trackSip3dSigAboveCharm =
              get_tagvar(reco::btau::trackSip3dSigAboveCharm, tag_trackSip3dSigAboveCharm);
          tag_jetNSelectedTracks =
              get_tagvar(reco::btau::jetNSelectedTracks, tag_jetNSelectedTracks);
          tag_jetNTracksEtaRel =
              get_tagvar(reco::btau::jetNTracksEtaRel, tag_jetNTracksEtaRel);
        }
      }

      TagVarCSV_trackSumJetEtRatio_.push_back(tag_trackSumJetEtRatio);
      TagVarCSV_trackSumJetDeltaR_.push_back(tag_trackSumJetDeltaR);
      TagVarCSV_vertexCategory_.push_back(tag_vertexCategory);
      TagVarCSV_trackSip2dValAboveCharm_.push_back(tag_trackSip2dValAboveCharm);
      TagVarCSV_trackSip2dSigAboveCharm_.push_back(tag_trackSip2dSigAboveCharm);
      TagVarCSV_trackSip3dValAboveCharm_.push_back(tag_trackSip3dValAboveCharm);
      TagVarCSV_trackSip3dSigAboveCharm_.push_back(tag_trackSip3dSigAboveCharm);
      TagVarCSV_jetNSelectedTracks_.push_back(tag_jetNSelectedTracks);
      TagVarCSV_jetNTracksEtaRel_.push_back(tag_jetNTracksEtaRel);

      int hadron_flavour = jet.hadronFlavour();
      int parton_flavour = jet.partonFlavour();
      jet_partonFlavour_.push_back(static_cast<float>(parton_flavour));
      float deepcsv_probb = getJetDiscriminator(jet, {"pfDeepCSVJetTags:probb"});
      float deepcsv_probbb = getJetDiscriminator(jet, {"pfDeepCSVJetTags:probbb"});
      float deepcsv_probc = getJetDiscriminator(jet, {"pfDeepCSVJetTags:probc"});
      float deepcsv_probudsg = getJetDiscriminator(jet, {"pfDeepCSVJetTags:probudsg"});
      jet_btagDeepCSV_probb_.push_back(deepcsv_probb);
      jet_btagDeepCSV_probbb_.push_back(deepcsv_probbb);
      jet_btagDeepCSV_probc_.push_back(deepcsv_probc);
      jet_btagDeepCSV_probudsg_.push_back(deepcsv_probudsg);
      float deepB = (deepcsv_probb >= 0.0f && deepcsv_probbb >= 0.0f) ? deepcsv_probb + deepcsv_probbb : -1.0f;
      float deepC = (deepcsv_probc >= 0.0f) ? deepcsv_probc : -1.0f;
      jet_btagDeepB_.push_back(deepB);
      jet_btagDeepC_.push_back(deepC);
      float pnet_BvsAll = getJetDiscriminator(jet, pnet_BvsAll_label);
      float pnet_CvsB = getJetDiscriminator(jet, pnet_CvsB_label);
      float pnet_CvsL = getJetDiscriminator(jet, pnet_CvsL_label);
      float pnet_QvsG = getJetDiscriminator(jet, pnet_QvsG_label);
      jet_btagPNetB_.push_back(pnet_BvsAll);
      jet_btagPNetCvB_.push_back(pnet_CvsB);
      jet_btagPNetCvL_.push_back(pnet_CvsL);
      jet_btagPNetQvG_.push_back(pnet_QvsG);
      jet_pnet_BvsAll_.push_back(pnet_BvsAll);
      jet_pnet_CvsB_.push_back(pnet_CvsB);
      jet_pnet_CvsL_.push_back(pnet_CvsL);
      jet_pnet_QvsG_.push_back(pnet_QvsG);
      jet_pnet_TauVsEle_.push_back(getJetDiscriminator(jet, pnet_TauVsEle_label));
      jet_pnet_TauVsJet_.push_back(getJetDiscriminator(jet, pnet_TauVsJet_label));
      jet_pnet_TauVsMu_.push_back(getJetDiscriminator(jet, pnet_TauVsMu_label));
      jet_pnet_probb_.push_back(getJetDiscriminator(jet, pnet_probb_label));
      jet_pnet_probc_.push_back(getJetDiscriminator(jet, pnet_probc_label));
      jet_pnet_probele_.push_back(getJetDiscriminator(jet, pnet_probele_label));
      jet_pnet_probg_.push_back(getJetDiscriminator(jet, pnet_probg_label));
      jet_pnet_probmu_.push_back(getJetDiscriminator(jet, pnet_probmu_label));
      jet_pnet_probtaum1h0p_.push_back(getJetDiscriminator(jet, pnet_probtaum1h0p_label));
      jet_pnet_probtaum1h1p_.push_back(getJetDiscriminator(jet, pnet_probtaum1h1p_label));
      jet_pnet_probtaum1h2p_.push_back(getJetDiscriminator(jet, pnet_probtaum1h2p_label));
      jet_pnet_probtaum3h0p_.push_back(getJetDiscriminator(jet, pnet_probtaum3h0p_label));
      jet_pnet_probtaum3h1p_.push_back(getJetDiscriminator(jet, pnet_probtaum3h1p_label));
      jet_pnet_probtaup1h0p_.push_back(getJetDiscriminator(jet, pnet_probtaup1h0p_label));
      jet_pnet_probtaup1h1p_.push_back(getJetDiscriminator(jet, pnet_probtaup1h1p_label));
      jet_pnet_probtaup1h2p_.push_back(getJetDiscriminator(jet, pnet_probtaup1h2p_label));
      jet_pnet_probtaup3h0p_.push_back(getJetDiscriminator(jet, pnet_probtaup3h0p_label));
      jet_pnet_probtaup3h1p_.push_back(getJetDiscriminator(jet, pnet_probtaup3h1p_label));
      jet_pnet_probuds_.push_back(getJetDiscriminator(jet, pnet_probuds_label));
      jet_pnet_ptcorr_.push_back(getJetDiscriminator(jet, pnet_ptcorr_label));
      jet_pnet_ptnu_.push_back(getJetDiscriminator(jet, pnet_ptnu_label));
      jet_pnet_ptreshigh_.push_back(getJetDiscriminator(jet, pnet_ptreshigh_label));
      jet_pnet_ptreslow_.push_back(getJetDiscriminator(jet, pnet_ptreslow_label));
      float robust_b = getJetDiscriminator(jet,
                                           {"pfRobustParTAK4BJetTags",
                                            "pfRobustParTAK4DiscriminatorsJetTags:BvsAll",
                                            "pfUnifiedParticleTransformerAK4DiscriminatorsJetTags:BvsAll"});
      float robust_cvb = getJetDiscriminator(jet,
                                             {"pfRobustParTAK4CvBJetTags",
                                              "pfRobustParTAK4DiscriminatorsJetTags:CvsB",
                                              "pfUnifiedParticleTransformerAK4DiscriminatorsJetTags:CvsB"});
      float robust_cvl = getJetDiscriminator(jet,
                                             {"pfRobustParTAK4CvLJetTags",
                                              "pfRobustParTAK4DiscriminatorsJetTags:CvsL",
                                              "pfUnifiedParticleTransformerAK4DiscriminatorsJetTags:CvsL"});
      float robust_qg = getJetDiscriminator(jet,
                                            {"pfRobustParTAK4QGJetTags",
                                             "pfRobustParTAK4DiscriminatorsJetTags:QvsG",
                                             "pfUnifiedParticleTransformerAK4DiscriminatorsJetTags:QvsG"});
      float part_pos = getJetDiscriminator(
          jet, {"pfRobustParTAK4JetTags:ParTPosvsAll", "pfRobustParTAK4JetTags:part_pos_vs_all"});
      float part_neg = getJetDiscriminator(
          jet, {"pfRobustParTAK4JetTags:ParTNegvsAll", "pfRobustParTAK4JetTags:part_neg_vs_all"});
      float part_zero = getJetDiscriminator(
          jet, {"pfRobustParTAK4JetTags:ParTZerovsAll", "pfRobustParTAK4JetTags:part_zero_vs_all"});
      float part_pos_neg =
          getJetDiscriminator(jet, {"pfRobustParTAK4JetTags:ParTPosvsNeg", "pfRobustParTAK4JetTags:part_pos_vs_neg"});
      float charge_score = part_pos_neg;
      if (charge_score <= -990.0f) {
        if (part_pos > -990.0f && part_neg > -990.0f) {
          charge_score = part_pos - part_neg;
        } else {
          charge_score = static_cast<float>(charge_k05);
        }
      }
      jet_btagRobustParTAK4B_.push_back(robust_b);
      jet_btagRobustParTAK4CvB_.push_back(robust_cvb);
      jet_btagRobustParTAK4CvL_.push_back(robust_cvl);
      jet_btagRobustParTAK4QG_.push_back(robust_qg);
      jet_ParTPosvsAll_.push_back(part_pos);
      jet_ParTNegvsAll_.push_back(part_neg);
      jet_ParTZerovsAll_.push_back(part_zero);
      jet_ParTPosvsNeg_.push_back(part_pos_neg);
      jet_charge_score_.push_back(charge_score);
      for (size_t i = 0; i < btagLabels_.size(); ++i) {
        btagValues_[i].push_back(getJetDiscriminator(jet, btagLabels_[i]));
      }
      float jet_pflav_charge = 0.0f;
      int apf = std::abs(parton_flavour);
      if (apf == 4 || apf == 5) {
        jet_pflav_charge = (parton_flavour >= 0) ? 1.0f : -1.0f;
      }

      jet_pflavCharge_.push_back(jet_pflav_charge);
      jet_hflav_.push_back(static_cast<float>(hadron_flavour));

      int hadron_pdgid = 0;
      int hadron_fallback_pdgid = 0;
      int hadron_species = 0;
      int hadron_charge = 0;
      int hadron_mixing = 0;
      const reco::GenParticle *best_b_hadron = nullptr;
      const reco::GenParticle *best_c_hadron = nullptr;

      if (prunedGenParticles.isValid()) {
        for (const auto &gp : *prunedGenParticles) {
          if (reco::deltaR(gp, jet) >= jetRadius_) {
            continue;
          }
          int pdgid = gp.pdgId();
          if (isBHadron(pdgid)) {
            if (hasDaughterWithQuark(gp, 5)) {
              continue;
            }
            if (!best_b_hadron || gp.pt() > best_b_hadron->pt()) {
              best_b_hadron = &gp;
            }
          } else if (isCHadron(pdgid)) {
            if (hasDaughterWithQuark(gp, 4)) {
              continue;
            }
            if (!best_c_hadron || gp.pt() > best_c_hadron->pt()) {
              best_c_hadron = &gp;
            }
          }
        }
      }

      const reco::GenParticle *best_hadron = best_b_hadron ? best_b_hadron : best_c_hadron;
      if (best_hadron) {
        hadron_pdgid = best_hadron->pdgId();
        hadron_species = hadronSpeciesFromPdgId(hadron_pdgid);
        hadron_charge = pdgChargeFromId(hadron_pdgid);
        if (std::abs(hadron_pdgid) == 511 || std::abs(hadron_pdgid) == 531) {
          if (apf == 5) {
            bool same_sign = (hadron_pdgid > 0) == (parton_flavour > 0);
            hadron_mixing = same_sign ? 1 : 0;
          }
        }
      } else {
        if (apf == 4 || apf == 5) {
          hadron_fallback_pdgid = parton_flavour;
        }
      }

      hadron_species_.push_back(static_cast<float>(hadron_species));
      hadron_species_pdgid_.push_back(static_cast<float>(hadron_pdgid));
      hadron_species_fallback_pdgid_.push_back(static_cast<float>(hadron_fallback_pdgid));
      hadron_charge_.push_back(static_cast<float>(hadron_charge));
      hadron_mixing_.push_back(static_cast<float>(hadron_mixing));

      int n_b = 0;
      int n_c = 0;
      if (prunedGenParticles.isValid()) {
        for (const auto &gp : *prunedGenParticles) {
          if (reco::deltaR(gp, jet) >= jetRadius_) {
            continue;
          }
          int pdgid = gp.pdgId();
          if (isBHadron(pdgid)) {
            if (hasDaughterWithQuark(gp, 5)) {
              continue;
            }
            ++n_b;
          } else if (isCHadron(pdgid)) {
            if (hasDaughterWithQuark(gp, 4)) {
              continue;
            }
            ++n_c;
          }
        }
      } else {
        if (hadron_flavour == 5) {
          n_b = 1;
        } else if (hadron_flavour == 4) {
          n_c = 1;
        }
      }

      bool isB = false;
      bool isBB = false;
      bool isGBB = false;
      bool isLeptonicB = false;
      bool isLeptonicB_C = false;
      bool isC = false;
      bool isCC = false;
      bool isGCC = false;
      bool isU = false;
      bool isD = false;
      bool isS = false;
      bool isG = false;

      if (n_b > 0) {
        if (n_b > 1) {
          if (apf == 21) {
            isGBB = true;
          } else {
            isBB = true;
          }
        } else {
          isB = true;
        }
      } else if (n_c > 0) {
        if (n_c > 1) {
          if (apf == 21) {
            isGCC = true;
          } else {
            isCC = true;
          }
        } else {
          isC = true;
        }
      } else {
        if (apf == 1) {
          isD = true;
        } else if (apf == 2) {
          isU = true;
        } else if (apf == 3) {
          isS = true;
        } else if (apf == 21) {
          isG = true;
        }
      }

      if (n_b > 0 && genParticles.isValid()) {
        for (const auto &gp : *genParticles) {
          int leppdg = std::abs(gp.pdgId());
          if (leppdg != 11 && leppdg != 13) {
            continue;
          }
          if (reco::deltaR(gp, jet) >= jetRadius_) {
            continue;
          }
          HeavyAncestry ancestry = heavyAncestry(&gp);
          if (ancestry.fromB) {
            isLeptonicB = true;
            if (ancestry.fromBviaC) {
              isLeptonicB_C = true;
            }
          }
          if (isLeptonicB && isLeptonicB_C) {
            break;
          }
        }
      }

      isB_.push_back(isB ? 1.0f : 0.0f);
      isBB_.push_back(isBB ? 1.0f : 0.0f);
      isGBB_.push_back(isGBB ? 1.0f : 0.0f);
      isLeptonicB_.push_back(isLeptonicB ? 1.0f : 0.0f);
      isLeptonicB_C_.push_back(isLeptonicB_C ? 1.0f : 0.0f);
      isC_.push_back(isC ? 1.0f : 0.0f);
      isCC_.push_back(isCC ? 1.0f : 0.0f);
      isGCC_.push_back(isGCC ? 1.0f : 0.0f);
      isU_.push_back(isU ? 1.0f : 0.0f);
      isD_.push_back(isD ? 1.0f : 0.0f);
      isS_.push_back(isS ? 1.0f : 0.0f);
      isG_.push_back(isG ? 1.0f : 0.0f);

      std::vector<size_t> sortedchargedindices = invertSortingVector(sortedcharged);
      std::vector<size_t> sortedneutralsindices = invertSortingVector(sortedneutrals);

      const size_t cpf_base = Cpfcan_eta_.size();
      auto append_cpf_defaults = [&](size_t n) {
        Cpfcan_eta_.insert(Cpfcan_eta_.end(), n, 0.0f);
        Cpfcan_phi_.insert(Cpfcan_phi_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackEtaRel_.insert(Cpfcan_BtagPf_trackEtaRel_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackPtRel_.insert(Cpfcan_BtagPf_trackPtRel_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackPPar_.insert(Cpfcan_BtagPf_trackPPar_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackDeltaR_.insert(Cpfcan_BtagPf_trackDeltaR_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackPParRatio_.insert(Cpfcan_BtagPf_trackPParRatio_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackSip2dVal_.insert(Cpfcan_BtagPf_trackSip2dVal_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackSip2dSig_.insert(Cpfcan_BtagPf_trackSip2dSig_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackSip3dVal_.insert(Cpfcan_BtagPf_trackSip3dVal_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackSip3dSig_.insert(Cpfcan_BtagPf_trackSip3dSig_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackJetDistVal_.insert(Cpfcan_BtagPf_trackJetDistVal_.end(), n, 0.0f);
        Cpfcan_ptrel_.insert(Cpfcan_ptrel_.end(), n, 0.0f);
        Cpfcan_drminsv_.insert(Cpfcan_drminsv_.end(), n, 0.0f);
        Cpfcan_VTX_ass_.insert(Cpfcan_VTX_ass_.end(), n, 0.0f);
        Cpfcan_fromPV_.insert(Cpfcan_fromPV_.end(), n, 0.0f);
        Cpfcan_puppiw_.insert(Cpfcan_puppiw_.end(), n, 0.0f);
        Cpfcan_chi2_.insert(Cpfcan_chi2_.end(), n, 0.0f);
        Cpfcan_quality_.insert(Cpfcan_quality_.end(), n, 0.0f);
        Cpfcan_pt_.insert(Cpfcan_pt_.end(), n, 0.0f);
        Cpfcan_charge_.insert(Cpfcan_charge_.end(), n, 0.0f);
        Cpfcan_dz_.insert(Cpfcan_dz_.end(), n, 0.0f);
        Cpfcan_dxy_.insert(Cpfcan_dxy_.end(), n, 0.0f);
        Cpfcan_dxysig_.insert(Cpfcan_dxysig_.end(), n, 0.0f);
        Cpfcan_BtagPf_trackDecayLen_.insert(Cpfcan_BtagPf_trackDecayLen_.end(), n, 0.0f);
        Cpfcan_HadFrac_.insert(Cpfcan_HadFrac_.end(), n, 0.0f);
        Cpfcan_CaloFrac_.insert(Cpfcan_CaloFrac_.end(), n, 0.0f);
        Cpfcan_pdgID_.insert(Cpfcan_pdgID_.end(), n, 0.0f);
        Cpfcan_lostInnerHits_.insert(Cpfcan_lostInnerHits_.end(), n, 0.0f);
        Cpfcan_numberOfPixelHits_.insert(Cpfcan_numberOfPixelHits_.end(), n, 0.0f);
        Cpfcan_numberOfStripHits_.insert(Cpfcan_numberOfStripHits_.end(), n, 0.0f);
        Cpfcan_tau_signal_.insert(Cpfcan_tau_signal_.end(), n, 0.0f);
        Cpfcan_px_.insert(Cpfcan_px_.end(), n, 0.0f);
        Cpfcan_py_.insert(Cpfcan_py_.end(), n, 0.0f);
        Cpfcan_pz_.insert(Cpfcan_pz_.end(), n, 0.0f);
        Cpfcan_e_.insert(Cpfcan_e_.end(), n, 0.0f);
        Cpfcan_isKaon_.insert(Cpfcan_isKaon_.end(), n, 0.0f);
        Cpfcan_kaon_genCharge_.insert(Cpfcan_kaon_genCharge_.end(), n, 0.0f);
        Cpfcan_kaon_motherPdgId_.insert(Cpfcan_kaon_motherPdgId_.end(), n, 0.0f);
        Cpfcan_kaon_motherCharge_.insert(Cpfcan_kaon_motherCharge_.end(), n, 0.0f);
      };

      const size_t npf_base = Npfcan_pt_.size();
      auto append_npf_defaults = [&](size_t n) {
        Npfcan_pt_.insert(Npfcan_pt_.end(), n, 0.0f);
        Npfcan_ptrel_.insert(Npfcan_ptrel_.end(), n, 0.0f);
        Npfcan_etarel_.insert(Npfcan_etarel_.end(), n, 0.0f);
        Npfcan_phirel_.insert(Npfcan_phirel_.end(), n, 0.0f);
        Npfcan_deltaR_.insert(Npfcan_deltaR_.end(), n, 0.0f);
        Npfcan_isGamma_.insert(Npfcan_isGamma_.end(), n, 0.0f);
        Npfcan_HadFrac_.insert(Npfcan_HadFrac_.end(), n, 0.0f);
        Npfcan_drminsv_.insert(Npfcan_drminsv_.end(), n, 0.0f);
        Npfcan_puppiw_.insert(Npfcan_puppiw_.end(), n, 0.0f);
        Npfcan_tau_signal_.insert(Npfcan_tau_signal_.end(), n, 0.0f);
        Npfcan_px_.insert(Npfcan_px_.end(), n, 0.0f);
        Npfcan_py_.insert(Npfcan_py_.end(), n, 0.0f);
        Npfcan_pz_.insert(Npfcan_pz_.end(), n, 0.0f);
        Npfcan_e_.insert(Npfcan_e_.end(), n, 0.0f);
      };

      append_cpf_defaults(maxCpfCandidates_);
      append_npf_defaults(maxNpfCandidates_);

      std::vector<int> is_kaon_for_entry(maxCpfCandidates_, 0);
      std::vector<int> kaon_gen_charge_for_entry(maxCpfCandidates_, 0);
      std::vector<int> kaon_mother_pdg_for_entry(maxCpfCandidates_, 0);
      std::vector<int> kaon_mother_charge_for_entry(maxCpfCandidates_, 0);
      const float kaon_match_dr = 0.1f;
      const float kaon_pt_rel_diff_max = 0.5f;

      if (genParticles.isValid()) {
        std::unordered_map<const reco::Candidate *, const reco::GenParticle *> best_kaon_by_mother;
        for (const auto &gen : *genParticles) {
          if (gen.status() != 1) {
            continue;
          }
          if (std::abs(gen.pdgId()) != 321) {
            continue;
          }
          int mother_pdg = heavyFlavorMotherPdgId(gen);
          if (mother_pdg == 0) {
            continue;
          }
          const reco::Candidate *mother_ptr = gen.mother();
          if (!mother_ptr) {
            continue;
          }
          auto it = best_kaon_by_mother.find(mother_ptr);
          if (it == best_kaon_by_mother.end() || gen.pt() > it->second->pt()) {
            best_kaon_by_mother[mother_ptr] = &gen;
          }
        }

        for (const auto &entry : best_kaon_by_mother) {
          const reco::GenParticle &gen = *(entry.second);
          float best_dr = kaon_match_dr;
          size_t best_entry = maxCpfCandidates_;
          for (size_t i = 0; i < daughters.size(); ++i) {
            const auto *packed = dynamic_cast<const pat::PackedCandidate *>(daughters[i].get());
            if (!packed) {
              continue;
            }
            if (packed->charge() == 0) {
              continue;
            }
            if (packed->pt() < minCandidatePt_) {
              continue;
            }
            if (packed->charge() != gen.charge()) {
              continue;
            }
            float dr = reco::deltaR(gen, *packed);
            if (dr >= best_dr) {
              continue;
            }
            float rel_diff = std::fabs(packed->pt() - gen.pt()) / gen.pt();
            if (rel_diff > kaon_pt_rel_diff_max) {
              continue;
            }
            if (i >= sortedchargedindices.size()) {
              continue;
            }
            size_t fillntupleentry = sortedchargedindices.at(i);
            if (fillntupleentry >= maxCpfCandidates_) {
              continue;
            }
            best_dr = dr;
            best_entry = fillntupleentry;
          }
          if (best_entry < maxCpfCandidates_) {
            is_kaon_for_entry[best_entry] = 1;
            kaon_gen_charge_for_entry[best_entry] = gen.charge();
            int mother_pdg = heavyFlavorMotherPdgId(gen);
            kaon_mother_pdg_for_entry[best_entry] = mother_pdg;
            kaon_mother_charge_for_entry[best_entry] = pdgChargeFromId(mother_pdg);
          }
        }
      } else {
        std::fill(is_kaon_for_entry.begin(), is_kaon_for_entry.end(), -1);
        std::fill(kaon_gen_charge_for_entry.begin(), kaon_gen_charge_for_entry.end(), 0);
        std::fill(kaon_mother_pdg_for_entry.begin(), kaon_mother_pdg_for_entry.end(), 0);
        std::fill(kaon_mother_charge_for_entry.begin(), kaon_mother_charge_for_entry.end(), 0);
      }

      for (size_t i = 0; i < daughters.size(); ++i) {
        const auto *packed = dynamic_cast<const pat::PackedCandidate *>(daughters[i].get());
        if (!packed) {
          continue;
        }
        if (packed->pt() < minCandidatePt_) {
          continue;
        }

        float drminpfcandsv = mindrsvpfcand(packed);
        float pdgid_category = packedCandidatePdgCategory(packed);

        if (packed->charge() != 0) {
          if (i >= sortedchargedindices.size()) {
            continue;
          }
          size_t fillntupleentry = sortedchargedindices.at(i);
          if (fillntupleentry >= maxCpfCandidates_) {
            continue;
          }
          size_t idx = cpf_base + fillntupleentry;

          Cpfcan_pdgID_[idx] = pdgid_category;
          Cpfcan_pt_[idx] = packed->pt();
          Cpfcan_px_[idx] = packed->px();
          Cpfcan_py_[idx] = packed->py();
          Cpfcan_pz_[idx] = packed->pz();
          Cpfcan_eta_[idx] = packed->eta();
          Cpfcan_phi_[idx] = packed->phi();
          Cpfcan_ptrel_[idx] = catchInfsAndBound(packed->pt() / jet_uncorr_pt, 0, -1, 0, -1);
          Cpfcan_e_[idx] = packed->energy();
          Cpfcan_dxy_[idx] = catchInfsAndBound(std::fabs(packed->dxy()), 0, -50, 50);
          Cpfcan_dxysig_[idx] = packed->hasTrackDetails()
                                     ? catchInfsAndBound(std::fabs(packed->dxy() / packed->dxyError()),
                                                         0, -2000, 2000)
                                     : 0.0f;
          Cpfcan_dz_[idx] = packed->dz();
          Cpfcan_VTX_ass_[idx] = packed->pvAssociationQuality();
          Cpfcan_fromPV_[idx] = packed->fromPV();
          Cpfcan_puppiw_[idx] = packed->puppiWeight();
          Cpfcan_HadFrac_[idx] = packed->hcalFraction();
          Cpfcan_CaloFrac_[idx] = packed->caloFraction();
          Cpfcan_charge_[idx] = packed->charge();
          Cpfcan_lostInnerHits_[idx] = catchInfs(packed->lostInnerHits(), 2);
          Cpfcan_numberOfPixelHits_[idx] = catchInfs(packed->numberOfPixelHits(), -1);
          Cpfcan_numberOfStripHits_[idx] = catchInfs(packed->stripLayersWithMeasurement(), -1);
          Cpfcan_chi2_[idx] = packed->hasTrackDetails()
                                  ? catchInfsAndBound(packed->pseudoTrack().normalizedChi2(), 300, -1, 300)
                                  : -1.0f;
          Cpfcan_quality_[idx] = packed->hasTrackDetails()
                                     ? static_cast<float>(packed->pseudoTrack().qualityMask())
                                     : static_cast<float>(1 << reco::TrackBase::loose);

          Cpfcan_tau_signal_[idx] =
              std::find(tau_pfcandidates.begin(), tau_pfcandidates.end(), packed->p4()) !=
                      tau_pfcandidates.end()
                  ? 1.0f
                  : 0.0f;

          trackinfo.buildTrackInfo(packed, jetDir, jetRefTrackDir, pv_ref);
          Cpfcan_BtagPf_trackEtaRel_[idx] = catchInfsAndBound(trackinfo.getTrackEtaRel(), 0, -5, 15);
          Cpfcan_BtagPf_trackPtRel_[idx] = catchInfsAndBound(trackinfo.getTrackPtRel(), 0, -1, 4);
          Cpfcan_BtagPf_trackPPar_[idx] = catchInfsAndBound(trackinfo.getTrackPPar(), 0, -1e5, 1e5);
          Cpfcan_BtagPf_trackDeltaR_[idx] = catchInfsAndBound(trackinfo.getTrackDeltaR(), 0, -5, 5);
          Cpfcan_BtagPf_trackPParRatio_[idx] = catchInfsAndBound(trackinfo.getTrackPParRatio(), 0, -10, 100);
          Cpfcan_BtagPf_trackSip2dVal_[idx] = catchInfsAndBound(trackinfo.getTrackSip2dVal(), 0, -1, 70);
          Cpfcan_BtagPf_trackSip2dSig_[idx] = catchInfsAndBound(trackinfo.getTrackSip2dSig(), 0, -1, 4e4);
          Cpfcan_BtagPf_trackSip3dVal_[idx] = catchInfsAndBound(trackinfo.getTrackSip3dVal(), 0, -1, 1e5);
          Cpfcan_BtagPf_trackSip3dSig_[idx] = catchInfsAndBound(trackinfo.getTrackSip3dSig(), 0, -1, 4e4);
          Cpfcan_BtagPf_trackDecayLen_[idx] = trackinfo.getTrackJetDecayLen();
          Cpfcan_BtagPf_trackJetDistVal_[idx] =
              catchInfsAndBound(trackinfo.getTrackJetDistVal(), 0, -20, 1);
          Cpfcan_drminsv_[idx] = catchInfsAndBound(drminpfcandsv, 0, -0.4, 0, -0.4);

          Cpfcan_isKaon_[idx] = is_kaon_for_entry.at(fillntupleentry);
          Cpfcan_kaon_genCharge_[idx] = kaon_gen_charge_for_entry.at(fillntupleentry);
          Cpfcan_kaon_motherPdgId_[idx] = kaon_mother_pdg_for_entry.at(fillntupleentry);
          Cpfcan_kaon_motherCharge_[idx] = kaon_mother_charge_for_entry.at(fillntupleentry);
        } else {
          if (i >= sortedneutralsindices.size()) {
            continue;
          }
          size_t fillntupleentry = sortedneutralsindices.at(i);
          if (fillntupleentry >= maxNpfCandidates_) {
            continue;
          }
          size_t idx = npf_base + fillntupleentry;
          Npfcan_pt_[idx] = packed->pt();
          Npfcan_px_[idx] = packed->px();
          Npfcan_py_[idx] = packed->py();
          Npfcan_pz_[idx] = packed->pz();
          Npfcan_ptrel_[idx] = catchInfsAndBound(packed->pt() / jet_uncorr_pt, 0, -1, 0, -1);
          Npfcan_e_[idx] = packed->energy();
          Npfcan_puppiw_[idx] = packed->puppiWeight();
          Npfcan_phirel_[idx] =
              catchInfsAndBound(std::fabs(reco::deltaPhi(packed->phi(), jet.phi())), 0, -2, 0, -0.5);
          Npfcan_etarel_[idx] =
              catchInfsAndBound(std::fabs(packed->eta() - jet.eta()), 0, -2, 0, -0.5);
          Npfcan_deltaR_[idx] =
              catchInfsAndBound(reco::deltaR(*packed, jet), 0, -0.6, 0, -0.6);
          Npfcan_isGamma_[idx] = (std::abs(packed->pdgId()) == 22) ? 1.0f : 0.0f;
          Npfcan_HadFrac_[idx] = packed->hcalFraction();
          Npfcan_drminsv_[idx] = catchInfsAndBound(drminpfcandsv, 0, -0.4, 0, -0.4);
          Npfcan_tau_signal_[idx] = 0.0f;
        }
      }

      const size_t sv_base = sv_pt_.size();
      auto append_sv_defaults = [&](size_t n) {
        sv_pt_.insert(sv_pt_.end(), n, 0.0f);
        sv_deltaR_.insert(sv_deltaR_.end(), n, 0.0f);
        sv_mass_.insert(sv_mass_.end(), n, 0.0f);
        sv_ntracks_.insert(sv_ntracks_.end(), n, 0.0f);
        sv_etarel_.insert(sv_etarel_.end(), n, 0.0f);
        sv_phirel_.insert(sv_phirel_.end(), n, 0.0f);
        sv_chi2_.insert(sv_chi2_.end(), n, 0.0f);
        sv_normchi2_.insert(sv_normchi2_.end(), n, 0.0f);
        sv_dxy_.insert(sv_dxy_.end(), n, 0.0f);
        sv_dxysig_.insert(sv_dxysig_.end(), n, 0.0f);
        sv_d3d_.insert(sv_d3d_.end(), n, 0.0f);
        sv_d3dsig_.insert(sv_d3dsig_.end(), n, 0.0f);
        sv_costhetasvpv_.insert(sv_costhetasvpv_.end(), n, 0.0f);
        sv_enratio_.insert(sv_enratio_.end(), n, 0.0f);
        sv_charge_sum_.insert(sv_charge_sum_.end(), n, 0.0f);
        sv_px_.insert(sv_px_.end(), n, 0.0f);
        sv_py_.insert(sv_py_.end(), n, 0.0f);
        sv_pz_.insert(sv_pz_.end(), n, 0.0f);
        sv_e_.insert(sv_e_.end(), n, 0.0f);
      };

      const size_t pairwise_base = pair_pca_distance_.size();
      auto append_pairwise_defaults = [&](size_t n) {
        pair_pca_distance_.insert(pair_pca_distance_.end(), n, 0.0f);
        pair_pca_significance_.insert(pair_pca_significance_.end(), n, 0.0f);
        pair_pcaSeed_x1_.insert(pair_pcaSeed_x1_.end(), n, 0.0f);
        pair_pcaSeed_y1_.insert(pair_pcaSeed_y1_.end(), n, 0.0f);
        pair_pcaSeed_z1_.insert(pair_pcaSeed_z1_.end(), n, 0.0f);
        pair_pcaSeed_x2_.insert(pair_pcaSeed_x2_.end(), n, 0.0f);
        pair_pcaSeed_y2_.insert(pair_pcaSeed_y2_.end(), n, 0.0f);
        pair_pcaSeed_z2_.insert(pair_pcaSeed_z2_.end(), n, 0.0f);
        pair_pcaSeed_xerr1_.insert(pair_pcaSeed_xerr1_.end(), n, 0.0f);
        pair_pcaSeed_yerr1_.insert(pair_pcaSeed_yerr1_.end(), n, 0.0f);
        pair_pcaSeed_zerr1_.insert(pair_pcaSeed_zerr1_.end(), n, 0.0f);
        pair_pcaSeed_xerr2_.insert(pair_pcaSeed_xerr2_.end(), n, 0.0f);
        pair_pcaSeed_yerr2_.insert(pair_pcaSeed_yerr2_.end(), n, 0.0f);
        pair_pcaSeed_zerr2_.insert(pair_pcaSeed_zerr2_.end(), n, 0.0f);
        pair_dotprod1_.insert(pair_dotprod1_.end(), n, 0.0f);
        pair_dotprod2_.insert(pair_dotprod2_.end(), n, 0.0f);
        pair_pca_dist1_.insert(pair_pca_dist1_.end(), n, 0.0f);
        pair_pca_dist2_.insert(pair_pca_dist2_.end(), n, 0.0f);
        pair_dotprod12_2D_.insert(pair_dotprod12_2D_.end(), n, 0.0f);
        pair_dotprod12_2DV_.insert(pair_dotprod12_2DV_.end(), n, 0.0f);
        pair_dotprod12_3D_.insert(pair_dotprod12_3D_.end(), n, 0.0f);
        pair_dotprod12_3DV_.insert(pair_dotprod12_3DV_.end(), n, 0.0f);
        pair_pca_jetAxis_dist_.insert(pair_pca_jetAxis_dist_.end(), n, 0.0f);
        pair_pca_jetAxis_dotprod_.insert(pair_pca_jetAxis_dotprod_.end(), n, 0.0f);
        pair_pca_jetAxis_dEta_.insert(pair_pca_jetAxis_dEta_.end(), n, 0.0f);
        pair_pca_jetAxis_dPhi_.insert(pair_pca_jetAxis_dPhi_.end(), n, 0.0f);
        pfcand_dist_vtx_12_.insert(pfcand_dist_vtx_12_.end(), n, 0.0f);
      };

      append_sv_defaults(maxSvCandidates_);
      append_pairwise_defaults(maxPairwiseCandidates_);

      std::vector<std::pair<float, const reco::VertexCompositePtrCandidate *>> sortedsv;
      if (secVertices.isValid()) {
        for (const auto &sv : *secVertices) {
          if (reco::deltaR(sv, jet) >= jetRadius_) {
            continue;
          }
          Measurement1D dxy = vertexDxy(sv, pv_ref);
          sortedsv.emplace_back(dxy.significance(), &sv);
        }
      }

      std::sort(sortedsv.begin(), sortedsv.end(),
                [](const auto &lhs, const auto &rhs) { return lhs.first > rhs.first; });
      nsv_.push_back(static_cast<int>(sortedsv.size()));

      const size_t n_sv = std::min(sortedsv.size(), static_cast<size_t>(maxSvCandidates_));
      for (size_t i = 0; i < n_sv; ++i) {
        const auto &sv = *(sortedsv[i].second);
        const size_t idx = sv_base + i;
        Measurement1D dxy = vertexDxy(sv, pv_ref);
        Measurement1D d3d = vertexD3d(sv, pv_ref);
        sv_pt_[idx] = catchInfs(sv.pt(), 0.0f);
        sv_deltaR_[idx] = catchInfs(reco::deltaR(sv, jet), 0.0f);
        sv_mass_[idx] = catchInfs(sv.mass(), 0.0f);
        sv_ntracks_[idx] = catchInfs(static_cast<float>(sv.numberOfDaughters()), 0.0f);
        sv_etarel_[idx] = catchInfs(reco::btau::etaRel(jetDir, sv.momentum()), 0.0f);
        sv_phirel_[idx] = catchInfs(std::fabs(reco::deltaPhi(sv.phi(), jet.phi())), 0.0f);
        const float sv_chi2 = sv.vertexChi2();
        const float sv_ndof = sv.vertexNdof();
        sv_chi2_[idx] = catchInfs(sv_chi2, 0.0f);
        sv_normchi2_[idx] =
            (sv_ndof > 0.0f) ? catchInfs(sv_chi2 / sv_ndof, 0.0f) : 0.0f;
        sv_dxy_[idx] = catchInfs(dxy.value(), 0.0f);
        sv_dxysig_[idx] = catchInfs(dxy.significance(), 0.0f);
        sv_d3d_[idx] = catchInfs(d3d.value(), 0.0f);
        sv_d3dsig_[idx] = catchInfs(d3d.significance(), 0.0f);
        sv_costhetasvpv_[idx] = catchInfs(vertexDdotP(sv, pv_ref), 0.0f);
        sv_enratio_[idx] = (jet.energy() > 0.0) ? catchInfs(sv.energy() / jet.energy(), 0.0f) : 0.0f;
        sv_charge_sum_[idx] = catchInfs(sv.charge(), 0.0f);
        sv_px_[idx] = catchInfs(sv.px(), 0.0f);
        sv_py_[idx] = catchInfs(sv.py(), 0.0f);
        sv_pz_[idx] = catchInfs(sv.pz(), 0.0f);
        sv_e_[idx] = catchInfs(sv.energy(), 0.0f);
      }

      std::vector<reco::TransientTrack> pair_tracks;
      const size_t max_pair_cands =
          std::min(sortedcharged.size(), static_cast<size_t>(maxCpfCandidates_));
      pair_tracks.reserve(max_pair_cands);
      for (size_t i = 0; i < max_pair_cands; ++i) {
        const auto &entry = sortedcharged[i];
        if (entry.idx >= daughters.size()) {
          continue;
        }
        const auto *packed = dynamic_cast<const pat::PackedCandidate *>(daughters[entry.idx].get());
        if (!packed || !packed->hasTrackDetails()) {
          continue;
        }
        reco::TransientTrack ttrack = trackBuilder.build(packed->pseudoTrack());
        if (!ttrack.isValid()) {
          continue;
        }
        pair_tracks.push_back(ttrack);
      }

      int n_pairs = 0;
      for (size_t i = 0; i < pair_tracks.size(); ++i) {
        for (size_t j = i + 1; j < pair_tracks.size(); ++j) {
          if (n_pairs >= static_cast<int>(maxPairwiseCandidates_)) {
            break;
          }
          TrackPairInfoBuilder pairinfo;
          pairinfo.buildTrackPairInfo(pair_tracks[i], pair_tracks[j], pv_ref, jet);
          const size_t idx = pairwise_base + static_cast<size_t>(n_pairs);
          pair_pca_distance_[idx] = catchInfs(pairinfo.pca_distance(), 0.0f);
          pair_pca_significance_[idx] = catchInfs(pairinfo.pca_significance(), 0.0f);
          pair_pcaSeed_x1_[idx] = catchInfs(pairinfo.pcaSeed_x(), 0.0f);
          pair_pcaSeed_y1_[idx] = catchInfs(pairinfo.pcaSeed_y(), 0.0f);
          pair_pcaSeed_z1_[idx] = catchInfs(pairinfo.pcaSeed_z(), 0.0f);
          pair_pcaSeed_x2_[idx] = catchInfs(pairinfo.pcaTrack_x(), 0.0f);
          pair_pcaSeed_y2_[idx] = catchInfs(pairinfo.pcaTrack_y(), 0.0f);
          pair_pcaSeed_z2_[idx] = catchInfs(pairinfo.pcaTrack_z(), 0.0f);
          pair_pcaSeed_xerr1_[idx] = catchInfs(pairinfo.pcaSeed_xerr(), 0.0f);
          pair_pcaSeed_yerr1_[idx] = catchInfs(pairinfo.pcaSeed_yerr(), 0.0f);
          pair_pcaSeed_zerr1_[idx] = catchInfs(pairinfo.pcaSeed_zerr(), 0.0f);
          pair_pcaSeed_xerr2_[idx] = catchInfs(pairinfo.pcaTrack_xerr(), 0.0f);
          pair_pcaSeed_yerr2_[idx] = catchInfs(pairinfo.pcaTrack_yerr(), 0.0f);
          pair_pcaSeed_zerr2_[idx] = catchInfs(pairinfo.pcaTrack_zerr(), 0.0f);
          pair_dotprod1_[idx] = catchInfs(pairinfo.dotprodSeed(), 0.0f);
          pair_dotprod2_[idx] = catchInfs(pairinfo.dotprodTrack(), 0.0f);
          pair_pca_dist1_[idx] = catchInfs(pairinfo.pcaSeed_dist(), 0.0f);
          pair_pca_dist2_[idx] = catchInfs(pairinfo.pcaTrack_dist(), 0.0f);
          pair_dotprod12_2D_[idx] = catchInfs(pairinfo.dotprodTrackSeed2D(), 0.0f);
          pair_dotprod12_2DV_[idx] = catchInfs(pairinfo.dotprodTrackSeed2DV(), 0.0f);
          pair_dotprod12_3D_[idx] = catchInfs(pairinfo.dotprodTrackSeed3D(), 0.0f);
          pair_dotprod12_3DV_[idx] = catchInfs(pairinfo.dotprodTrackSeed3DV(), 0.0f);
          pair_pca_jetAxis_dist_[idx] = catchInfs(pairinfo.pca_jetAxis_dist(), 0.0f);
          pair_pca_jetAxis_dotprod_[idx] = catchInfs(pairinfo.pca_jetAxis_dotprod(), 0.0f);
          pair_pca_jetAxis_dEta_[idx] = catchInfs(pairinfo.pca_jetAxis_dEta(), 0.0f);
          pair_pca_jetAxis_dPhi_[idx] = catchInfs(pairinfo.pca_jetAxis_dPhi(), 0.0f);
          pfcand_dist_vtx_12_[idx] = catchInfs(pairinfo.pfcand_dist_vtx_12(), 0.0f);
          ++n_pairs;
        }
        if (n_pairs >= static_cast<int>(maxPairwiseCandidates_)) {
          break;
        }
      }

      n_Cpfpairs_.push_back(n_pairs);
      nCpfpairs_.push_back(static_cast<float>(n_pairs));

      int has_soft = 0;
      float soft_charge = 0.0f;
      float soft_ptrel = -1.0f;
      float soft_ip_sig = -1.0f;
      float soft_dr = -1.0f;

      if (muons.isValid() && pv) {
        const pat::Muon *best_mu = nullptr;
        float best_pt = -1.0f;
        for (const auto &muon : *muons) {
          if (reco::deltaR(muon, jet) > jetRadius_) {
            continue;
          }
          if (muon.pt() > best_pt) {
            best_pt = muon.pt();
            best_mu = &muon;
          }
        }
        if (best_mu) {
          has_soft = 1;
          soft_charge = best_mu->charge();
          soft_dr = reco::deltaR(*best_mu, jet);
          TVector3 jet_dir(jet.px(), jet.py(), jet.pz());
          TVector3 mu_dir(best_mu->px(), best_mu->py(), best_mu->pz());
          soft_ptrel = mu_dir.Perp(jet_dir);
          if (best_mu->muonBestTrack().isNonnull()) {
            const auto &trk = best_mu->muonBestTrack();
            double dxy = trk->dxy(pv->position());
            double dxy_err = trk->dxyError();
            if (dxy_err > 0) {
              soft_ip_sig = std::abs(dxy / dxy_err);
            }
          }
        }
      }

      has_soft_mu_.push_back(has_soft);
      soft_mu_charge_.push_back(soft_charge);
      soft_mu_ptrel_.push_back(soft_ptrel);
      soft_mu_ip_sig_.push_back(soft_ip_sig);
      soft_mu_dR_jet_.push_back(soft_dr);

      std::sort(charged.begin(), charged.end(), [](const pat::PackedCandidate *a, const pat::PackedCandidate *b) {
        return a->pt() > b->pt();
      });
      std::sort(photons.begin(), photons.end(), [](const pat::PackedCandidate *a, const pat::PackedCandidate *b) {
        return a->pt() > b->pt();
      });

      auto build_p4 = [](const pat::PackedCandidate *cand, float mass) -> TLorentzVector {
        TLorentzVector p4;
        p4.SetPtEtaPhiM(cand->pt(), cand->eta(), cand->phi(), mass);
        return p4;
      };

      float mass_2trk_pi = 0.0f;
      float mass_2trk_kpi = 0.0f;
      float mass_3trk_pi = 0.0f;
      float mass_3trk_kpipi = 0.0f;
      float mass_2trk_pi_pi0 = 0.0f;
      float mass_2trk_kpi_pi0 = 0.0f;
      float mass_3trk_pi_pi0 = 0.0f;
      float mass_3trk_kpipi_pi0 = 0.0f;
      float pi0_mass = 0.0f;
      float pi0_pt = 0.0f;
      int pi0_found = 0;
      int had_pi0 = 0;
      int n_pi0 = 0;

      TLorentzVector pi0_p4;
      float best_pi0_delta = 1e9f;
      if (photons.size() >= 2) {
        for (size_t i = 0; i < photons.size(); ++i) {
          for (size_t j = i + 1; j < photons.size(); ++j) {
            TLorentzVector g1 = build_p4(photons[i], 0.0f);
            TLorentzVector g2 = build_p4(photons[j], 0.0f);
            TLorentzVector gg = g1 + g2;
            float mgg = gg.M();
            float delta = std::abs(mgg - kPi0Mass);
            if (delta < kPi0Window) {
              n_pi0 += 1;
              if (delta < best_pi0_delta) {
                best_pi0_delta = delta;
                pi0_found = 1;
                pi0_mass = mgg;
                pi0_pt = gg.Pt();
                pi0_p4 = gg;
              }
            }
          }
        }
      }
      had_pi0 = (n_pi0 > 0) ? 1 : 0;

      if (charged.size() >= 2) {
        TLorentzVector p1_pi = build_p4(charged[0], kPionMass);
        TLorentzVector p2_pi = build_p4(charged[1], kPionMass);
        TLorentzVector p1_k = build_p4(charged[0], kKaonMass);
        mass_2trk_pi = (p1_pi + p2_pi).M();
        mass_2trk_kpi = (p1_k + p2_pi).M();
        if (pi0_found) {
          mass_2trk_pi_pi0 = (p1_pi + p2_pi + pi0_p4).M();
          mass_2trk_kpi_pi0 = (p1_k + p2_pi + pi0_p4).M();
        }
        if (charged.size() >= 3) {
          TLorentzVector p3_pi = build_p4(charged[2], kPionMass);
          mass_3trk_pi = (p1_pi + p2_pi + p3_pi).M();
          mass_3trk_kpipi = (p1_k + p2_pi + p3_pi).M();
          if (pi0_found) {
            mass_3trk_pi_pi0 = (p1_pi + p2_pi + p3_pi + pi0_p4).M();
            mass_3trk_kpipi_pi0 = (p1_k + p2_pi + p3_pi + pi0_p4).M();
          }
        }
      }

      mass_2trk_pi_.push_back(mass_2trk_pi);
      mass_2trk_kpi_.push_back(mass_2trk_kpi);
      mass_3trk_pi_.push_back(mass_3trk_pi);
      mass_3trk_kpipi_.push_back(mass_3trk_kpipi);
      mass_2trk_pi_pi0_.push_back(mass_2trk_pi_pi0);
      mass_2trk_kpi_pi0_.push_back(mass_2trk_kpi_pi0);
      mass_3trk_pi_pi0_.push_back(mass_3trk_pi_pi0);
      mass_3trk_kpipi_pi0_.push_back(mass_3trk_kpipi_pi0);
      pi0_mass_.push_back(pi0_mass);
      pi0_pt_.push_back(pi0_pt);
      pi0_found_.push_back(pi0_found);
      hadPi0_.push_back(had_pi0);
      nPi0_.push_back(n_pi0);
    }
  }

  if (jets.isValid()) {
    for (const auto &jet : *jets) {
      if (jet.pt() < jetMinPt_ || std::abs(jet.eta()) > jetMaxEta_) {
        continue;
      }
      if (!passJetId(jet)) {
        continue;
      }

      jet_CHS_pt_.push_back(jet.pt());
      jet_CHS_eta_.push_back(jet.eta());
      jet_CHS_phi_.push_back(jet.phi());
      jet_CHS_mass_.push_back(jet.mass());

      float charged_frac = -1.0f;
      float neutral_frac = -1.0f;
      try {
        charged_frac = jet.chargedHadronEnergyFraction() + jet.chargedEmEnergyFraction();
        neutral_frac = jet.neutralHadronEnergyFraction() + jet.neutralEmEnergyFraction();
      } catch (...) {
        charged_frac = -1.0f;
        neutral_frac = -1.0f;
      }
      jet_CHS_charged_fraction_.push_back(charged_frac);
      jet_CHS_neutral_fraction_.push_back(neutral_frac);

      double charge_k03 = 0.0;
      double charge_k05 = 0.0;
      double charge_k10 = 0.0;
      double charge_k20 = 0.0;
      const auto &daughters = jet.daughterPtrVector();
      for (const auto &daughter : daughters) {
        if (!daughter.isNonnull()) {
          continue;
        }
        const auto *packed = dynamic_cast<const pat::PackedCandidate *>(daughter.get());
        if (!packed) {
          continue;
        }
        if (packed->pt() < minCandidatePt_) {
          continue;
        }
        if (packed->charge() == 0) {
          continue;
        }
        double pt = packed->pt();
        double q = packed->charge();
        charge_k03 += q * std::pow(pt, 0.3);
        charge_k05 += q * std::pow(pt, 0.5);
        charge_k10 += q * std::pow(pt, 1.0);
        charge_k20 += q * std::pow(pt, 2.0);
      }
      if (jet.pt() > 0) {
        charge_k03 /= std::pow(jet.pt(), 0.3);
        charge_k05 /= std::pow(jet.pt(), 0.5);
        charge_k10 /= std::pow(jet.pt(), 1.0);
        charge_k20 /= std::pow(jet.pt(), 2.0);
      } else {
        charge_k03 = 0.0;
        charge_k05 = 0.0;
        charge_k10 = 0.0;
        charge_k20 = 0.0;
      }
      jet_CHS_charge_k03_.push_back(static_cast<float>(charge_k03));
      jet_CHS_charge_k05_.push_back(static_cast<float>(charge_k05));
      jet_CHS_charge_k10_.push_back(static_cast<float>(charge_k10));
      jet_CHS_charge_k20_.push_back(static_cast<float>(charge_k20));

      int hadron_flavour = jet.hadronFlavour();
      int parton_flavour = jet.partonFlavour();
      jet_CHS_partonFlavour_.push_back(static_cast<float>(parton_flavour));
      float jet_pflav_charge = 0.0f;
      int apf = std::abs(parton_flavour);
      if (apf == 4 || apf == 5) {
        jet_pflav_charge = (parton_flavour >= 0) ? 1.0f : -1.0f;
      }
      jet_CHS_pflavCharge_.push_back(jet_pflav_charge);
      jet_CHS_hflav_.push_back(static_cast<float>(hadron_flavour));

      for (size_t i = 0; i < btagLabelsCHS_.size(); ++i) {
        btagValuesCHS_[i].push_back(getJetDiscriminator(jet, btagLabelsCHS_[i]));
      }
    }
  }

  nJetSel_ = static_cast<int>(jet_pt_.size());
  if (nJetSel_ < static_cast<int>(minNJets_)) {
    return;
  }

  if (nJetSel_ > 0 && (nMuonSel_ + nElectronSel_) > 0) {
    TLorentzVector lep_p4;
    TLorentzVector jet_p4;
    TLorentzVector met_p4;
    lep_p4.SetPtEtaPhiM(lepton_pt_, lepton_eta_, lepton_phi_, lepton_mass_);
    jet_p4.SetPtEtaPhiM(jet_pt_[0], jet_eta_[0], jet_phi_[0], jet_mass_[0]);
    met_p4.SetPtEtaPhiM(met_pt_, 0.0, met_phi_, 0.0);
    top_mass_proxy_ = static_cast<float>((lep_p4 + jet_p4 + met_p4).M());
  }

  cutflow_->Fill(3);
  tree_->Fill();
  cutflow_->Fill(4);
}

DEFINE_FWK_MODULE(ChargeNtupleProducer);
