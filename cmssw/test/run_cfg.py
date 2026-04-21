import os

import FWCore.ParameterSet.Config as cms
from FWCore.ParameterSet.VarParsing import VarParsing
from FWCore.PythonUtilities.LumiList import LumiList

try:
    import yaml
except ImportError as exc:
    raise RuntimeError("PyYAML is required for selections.yml parsing") from exc

try:
    from JetChargeCalib.chargeNtuples_cfi import chargeNtuples
except ModuleNotFoundError:
    import importlib.util

    cmssw_base = os.environ.get("CMSSW_BASE", "")
    cfg_path = os.path.join(cmssw_base, "src", "JetChargeCalib", "python", "chargeNtuples_cfi.py")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(cmssw_base, "src", "ChargeNtuples", "python", "chargeNtuples_cfi.py")
    if not os.path.exists(cfg_path):
        raise
    spec = importlib.util.spec_from_file_location("JetChargeCalib.chargeNtuples_cfi", cfg_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chargeNtuples = module.chargeNtuples

options = VarParsing("analysis")
options.register("inputFileList", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Text file with input file names")
if options.has_key("outputFile"):
    options.setDefault("outputFile", "jetcharge_calib_ntuple.root")
else:
    options.register(
        "outputFile",
        "jetcharge_calib_ntuple.root",
        VarParsing.multiplicity.singleton,
        VarParsing.varType.string,
        "Output ROOT file",
    )
options.register("selectionsYml", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Selections YAML")
options.register("featuresYml", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Features YAML")
options.register("weightsYml", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Weights YAML")
options.register("systematicsYml", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Systematics YAML")
options.register("goldenJson", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Golden JSON path")
options.register(
    "goldenJsonsYml",
    "",
    VarParsing.multiplicity.singleton,
    VarParsing.varType.string,
    "YAML mapping of era -> golden JSON path",
)
options.register("dataEra", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Era key for golden JSON lookup")
options.register("era", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Era key for weights lookup")
options.register("globalTag", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "GlobalTag override")
options.parseArguments()

input_files = []
if options.inputFileList:
    with open(options.inputFileList, "r", encoding="utf-8") as handle:
        input_files = [line.strip() for line in handle if line.strip()]
else:
    input_files = list(options.inputFiles)

if not input_files:
    input_files = ["file:input.root"]

process = cms.Process("JETCHARGECALIB")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(options.maxEvents))
process.source = cms.Source("PoolSource", fileNames=cms.untracked.vstring(*input_files))

process.load("Configuration.StandardSequences.Services_cff")
process.load("Configuration.Geometry.GeometryRecoDB_cff")
process.load("Configuration.StandardSequences.MagneticField_cff")
process.load("Configuration.StandardSequences.FrontierConditions_GlobalTag_cff")
process.load("TrackingTools.TransientTrack.TransientTrackBuilder_cfi")
process.MessageLogger.cerr.FwkReport.reportEvery = 1000

from Configuration.AlCa.GlobalTag import GlobalTag

if options.globalTag:
    process.GlobalTag = GlobalTag(process.GlobalTag, options.globalTag, "")
else:
    default_tag = "auto:run3_mc_GRun"
    if options.dataEra:
        if options.dataEra.startswith("Run2") or options.dataEra.startswith("UL"):
            default_tag = "auto:run2_data"
        elif options.dataEra.startswith("Run3"):
            default_tag = "auto:run3_data"
    process.GlobalTag = GlobalTag(process.GlobalTag, default_tag, "")

process.TFileService = cms.Service("TFileService", fileName=cms.string(options.outputFile))

selections = {}
if options.selectionsYml:
    with open(options.selectionsYml, "r", encoding="utf-8") as handle:
        selections = yaml.safe_load(handle) or {}

features = {}
if options.featuresYml:
    with open(options.featuresYml, "r", encoding="utf-8") as handle:
        features = yaml.safe_load(handle) or {}

weights = {}
if options.weightsYml:
    with open(options.weightsYml, "r", encoding="utf-8") as handle:
        weights = yaml.safe_load(handle) or {}

def _lookup_golden_json(golden_cfg, era_key):
    if not era_key:
        return ""
    if era_key in golden_cfg:
        return golden_cfg[era_key]
    for _, maybe in golden_cfg.items():
        if isinstance(maybe, dict) and era_key in maybe:
            return maybe[era_key]
    return ""


json_path = options.goldenJson
if not json_path and options.goldenJsonsYml and options.dataEra:
    with open(options.goldenJsonsYml, "r", encoding="utf-8") as handle:
        golden_cfg = yaml.safe_load(handle) or {}
    json_path = _lookup_golden_json(golden_cfg, options.dataEra)
    if json_path:
        base_dir = os.path.dirname(os.path.abspath(options.goldenJsonsYml))
        if not os.path.isabs(json_path):
            json_path = os.path.abspath(os.path.join(base_dir, json_path))

if json_path:
    if os.path.exists(json_path):
        process.source.lumisToProcess = LumiList(filename=json_path).getVLuminosityBlockRange()
        print(f"[jet-charge-calib] Applying golden JSON: {json_path}")
    else:
        print(f"[jet-charge-calib] Golden JSON not found: {json_path}")

hlt_cfg = selections.get("hlt", {})
hlt_by_era = selections.get("hlt_by_era")
jets_cfg = selections.get("jets", {})
leptons_cfg = selections.get("leptons", {})

era_key = options.era or options.dataEra
if hlt_by_era is not None:
    if not era_key:
        raise RuntimeError("hlt_by_era is set but no era/dataEra was provided.")
    if not isinstance(hlt_by_era, dict):
        raise RuntimeError("hlt_by_era must be a mapping of era -> hlt config.")
    hlt_cfg = hlt_by_era.get(era_key)
    if not isinstance(hlt_cfg, dict):
        available = ", ".join(sorted(hlt_by_era.keys()))
        raise RuntimeError(f"Missing hlt_by_era entry for '{era_key}'. Available: {available}")

process.chargeNtuples = chargeNtuples.clone(
    triggerResults=cms.InputTag("TriggerResults", "", hlt_cfg.get("process", "HLT")),
    applyHLT=cms.bool(bool(hlt_cfg.get("apply", False))),
    hltPaths=cms.vstring(hlt_cfg.get("paths", [])),
    minNJets=cms.uint32(int(jets_cfg.get("min_njets", 0))),
    jetMinPt=cms.double(float(jets_cfg.get("min_pt", 0.0))),
    jetMaxEta=cms.double(float(jets_cfg.get("max_eta", 999.0))),
    jetId=cms.string(jets_cfg.get("jet_id", "")),
    tagInfoName=cms.string(features.get("tag_info_name", "pfDeepCSV")),
    leptonMode=cms.string(selections.get("mode", "hadronic")),
    muonMinPt=cms.double(float(leptons_cfg.get("muon_min_pt", 0.0))),
    muonMaxEta=cms.double(float(leptons_cfg.get("muon_max_eta", 999.0))),
    electronMinPt=cms.double(float(leptons_cfg.get("electron_min_pt", 0.0))),
    electronMaxEta=cms.double(float(leptons_cfg.get("electron_max_eta", 999.0))),
    maxCpfCandidates=cms.uint32(int(features.get("max_cpf_candidates", 26))),
    maxNpfCandidates=cms.uint32(int(features.get("max_npf_candidates", 25))),
    maxSvCandidates=cms.uint32(int(features.get("max_sv_candidates", 5))),
    maxPairwiseCandidates=cms.uint32(int(features.get("max_pairwise_candidates", 30))),
)

pu_cfg = {}
if isinstance(weights.get("pileup"), dict):
    if era_key and isinstance(weights["pileup"].get(era_key), dict):
        pu_cfg = weights["pileup"].get(era_key, {})
    elif isinstance(weights["pileup"].get("default"), dict):
        pu_cfg = weights["pileup"].get("default", {})

if pu_cfg:
    process.chargeNtuples.puWeightsFile = cms.string(pu_cfg.get("file", ""))
    process.chargeNtuples.puWeightsHist = cms.string(pu_cfg.get("hist", ""))
    process.chargeNtuples.puWeightsUpHist = cms.string(pu_cfg.get("hist_up", ""))
    process.chargeNtuples.puWeightsDownHist = cms.string(pu_cfg.get("hist_down", ""))

process.p = cms.Path(process.chargeNtuples)
