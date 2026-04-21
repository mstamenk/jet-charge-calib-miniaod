import FWCore.ParameterSet.Config as cms

try:
    from JetChargeCalib.btag_discriminators import BTagDiscriminatorsCHS, BTagDiscriminatorsPuppi
except ModuleNotFoundError:
    import importlib.util
    import os

    _pkg_dir = os.path.dirname(__file__)
    _labels_path = os.path.join(_pkg_dir, "btag_discriminators.py")
    _spec = importlib.util.spec_from_file_location("JetChargeCalib.btag_discriminators", _labels_path)
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    BTagDiscriminatorsCHS = _module.BTagDiscriminatorsCHS
    BTagDiscriminatorsPuppi = _module.BTagDiscriminatorsPuppi

chargeNtuples = cms.EDAnalyzer(
    "ChargeNtupleProducer",
    jets=cms.InputTag("slimmedJets"),
    jetsPuppi=cms.InputTag("slimmedJetsPuppi"),
    muons=cms.InputTag("slimmedMuons"),
    electrons=cms.InputTag("slimmedElectrons"),
    mets=cms.InputTag("slimmedMETs"),
    vertices=cms.InputTag("offlineSlimmedPrimaryVertices"),
    secondaryVertices=cms.InputTag("slimmedSecondaryVertices"),
    genParticles=cms.InputTag("packedGenParticles"),
    prunedGenParticles=cms.InputTag("prunedGenParticles"),
    genEventInfo=cms.InputTag("generator"),
    pileupSummary=cms.InputTag("slimmedAddPileupInfo"),
    lheEvent=cms.InputTag("externalLHEProducer"),
    prefireWeight=cms.InputTag("prefiringweight", "nonPrefiringProb"),
    prefireWeightUp=cms.InputTag("prefiringweight", "nonPrefiringProbUp"),
    prefireWeightDown=cms.InputTag("prefiringweight", "nonPrefiringProbDown"),
    taus=cms.InputTag("slimmedTaus"),
    rho=cms.InputTag("fixedGridRhoFastjetAll"),
    triggerResults=cms.InputTag("TriggerResults", "", "HLT"),
    applyHLT=cms.bool(False),
    hltPaths=cms.vstring(),
    minNJets=cms.uint32(2),
    jetMinPt=cms.double(30.0),
    jetMaxEta=cms.double(2.4),
    jetId=cms.string(""),
    usePuppiJets=cms.bool(True),
    tagInfoName=cms.string("pfDeepCSV"),
    leptonMode=cms.string("hadronic"),
    muonMinPt=cms.double(20.0),
    muonMaxEta=cms.double(2.4),
    electronMinPt=cms.double(20.0),
    electronMaxEta=cms.double(2.5),
    tauMinPt=cms.double(20.0),
    tauMaxEta=cms.double(2.3),
    minCandidatePt=cms.double(0.1),
    jetRadius=cms.double(0.4),
    maxCpfCandidates=cms.uint32(26),
    maxNpfCandidates=cms.uint32(25),
    maxSvCandidates=cms.uint32(5),
    maxPairwiseCandidates=cms.uint32(30),
    puWeightsFile=cms.string(""),
    puWeightsHist=cms.string(""),
    puWeightsUpHist=cms.string(""),
    puWeightsDownHist=cms.string(""),
    btagDiscriminators=cms.vstring(BTagDiscriminatorsPuppi),
    btagDiscriminatorsCHS=cms.vstring(BTagDiscriminatorsCHS),
)
