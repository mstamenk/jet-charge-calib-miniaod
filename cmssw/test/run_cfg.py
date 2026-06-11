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
options.register(
    "sampleType",
    "auto",
    VarParsing.multiplicity.singleton,
    VarParsing.varType.string,
    "Sample type: auto, data, or mc",
)
options.register(
    "debugPrintFirstNEvents",
    0,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "Print jet-charge debug information for the first N accepted events",
)
options.register(
    "requireOnnxChargeInference",
    1,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "Require ONNX charge inference branches and fail if missing (1=true, 0=false)",
)
options.register(
    "enableOnnxChargeInference",
    1,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "Run RobustParTAK4 ONNX inference sequence on MiniAOD before the analyzer (1=true, 0=false)",
)
options.register(
    "enableEventPreselectionFilter",
    1,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "Run a fast event preselection filter before ChargeNtupleProducer to skip non-selected events early (1=true, 0=false)",
)
options.register(
    "prefilterApplyJetSelection",
    0,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "Apply jet multiplicity/overlap cuts in EventPreselectionFilter (1=true, 0=false). Default is 0 to keep prefilter as a safe superset.",
)
options.register(
    "wantSummary",
    0,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.int,
    "Enable CMSSW framework summary/TimeReport at end of job (1=true, 0=false)",
)
options.register("sampleName", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Sample name label")
options.register("datasetName", "", VarParsing.multiplicity.singleton, VarParsing.varType.string, "Dataset path label")
options.register(
    "sampleXsecPb",
    -1.0,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.float,
    "Sample cross section in pb (MC normalization metadata)",
)
options.register(
    "sampleSumWeights",
    0.0,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.float,
    "Total generator sum of weights for the full sample (MC normalization metadata)",
)
options.register(
    "targetLumiPb",
    0.0,
    VarParsing.multiplicity.singleton,
    VarParsing.varType.float,
    "Target integrated luminosity in /pb for MC normalization metadata",
)
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


def _infer_is_data(file_names):
    sim_tokens = ("MINIAODSIM", "NANOAODSIM", "AODSIM")
    data_tokens = ("/MINIAOD", "/NANOAOD", "/AOD")
    upper_names = [name.upper() for name in file_names]
    if any(any(token in name for token in sim_tokens) for name in upper_names):
        return False
    if any(any(token in name for token in data_tokens) for name in upper_names):
        return True
    # Conservative default for ambiguous local file paths.
    return False


sample_type = (options.sampleType or "auto").strip().lower()
if sample_type not in {"auto", "data", "mc"}:
    raise RuntimeError(f"Invalid sampleType '{options.sampleType}'. Allowed values: auto, data, mc")

is_data = _infer_is_data(input_files) if sample_type == "auto" else (sample_type == "data")
print(f"[jet-charge-calib] Sample type resolved to {'data' if is_data else 'mc'} (mode={sample_type})")

process = cms.Process("JETCHARGECALIB")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(options.maxEvents))
process.source = cms.Source("PoolSource", fileNames=cms.untracked.vstring(*input_files))
process.options = cms.untracked.PSet(wantSummary=cms.untracked.bool(bool(int(options.wantSummary))))

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
    era_for_tag = options.dataEra or options.era
    if is_data and era_for_tag:
        if era_for_tag.startswith("Run2") or era_for_tag.startswith("UL"):
            default_tag = "auto:run2_data"
        elif era_for_tag.startswith("Run3"):
            default_tag = "auto:run3_data"
    process.GlobalTag = GlobalTag(process.GlobalTag, default_tag, "")

pat_task_for_onnx_inference = None
if bool(int(options.enableOnnxChargeInference)):
    from PhysicsTools.NanoAOD.jetsAK4_Puppi_cff import nanoAOD_addDeepInfoAK4
    from PhysicsTools.PatAlgos.tools.helpers import getPatAlgosToolsTask

    # Recompute AK4 PUPPI discriminators from MiniAOD, including ParT charge outputs.
    process = nanoAOD_addDeepInfoAK4(
        process,
        addParticleNet=False,
        addRobustParTAK4=True,
        addUnifiedParTAK4=False,
    )
    jec_levels = ("L2Relative", "L3Absolute", "L2L3Residual") if is_data else ("L2Relative", "L3Absolute")
    configured_jec_modules = 0
    for mod_name in ("patJetCorrFactorsPuppiWithDeepInfo", "patJetCorrFactorsTransientCorrectedPuppiWithDeepInfo"):
        if hasattr(process, mod_name):
            getattr(process, mod_name).levels = cms.vstring(*jec_levels)
            configured_jec_modules += 1
    if configured_jec_modules:
        print(
            "[jet-charge-calib] Re-running AK4 PUPPI DeepInfo with JEC levels "
            f"{list(jec_levels)} on {configured_jec_modules} module(s)."
        )
    if not is_data and hasattr(process, "patSmearedJetsPuppiWithDeepInfo"):
        print("[jet-charge-calib] MC mode: patSmearedJetsPuppiWithDeepInfo present (JER smearing active).")
    pat_task_for_onnx_inference = getPatAlgosToolsTask(process)
    print("[jet-charge-calib] Enabled on-the-fly RobustParTAK4 ONNX inference on slimmedJetsPuppi.")

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


if is_data:
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
else:
    if options.goldenJson or options.goldenJsonsYml:
        print("[jet-charge-calib] Skipping golden JSON because sample type is MC.")

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
    maxNJets=cms.int32(int(jets_cfg.get("max_njets", -1))),
    jetMinPt=cms.double(float(jets_cfg.get("min_pt", 0.0))),
    jetMaxEta=cms.double(float(jets_cfg.get("max_eta", 999.0))),
    jetId=cms.string(jets_cfg.get("jet_id", "")),
    jetLeptonOverlapDR=cms.double(float(jets_cfg.get("jet_lepton_overlap_dr", -1.0))),
    tagInfoName=cms.string(features.get("tag_info_name", "pfDeepCSV")),
    leptonMode=cms.string(selections.get("mode", "hadronic")),
    maxNLeptons=cms.int32(int(leptons_cfg.get("max_nleptons", -1))),
    muonMinPt=cms.double(float(leptons_cfg.get("muon_min_pt", 0.0))),
    muonMaxEta=cms.double(float(leptons_cfg.get("muon_max_eta", 999.0))),
    muonId=cms.string(str(leptons_cfg.get("muon_id", "none"))),
    muonMaxRelIso04=cms.double(float(leptons_cfg.get("muon_max_rel_iso04", -1.0))),
    electronMinPt=cms.double(float(leptons_cfg.get("electron_min_pt", 0.0))),
    electronMaxEta=cms.double(float(leptons_cfg.get("electron_max_eta", 999.0))),
    electronId=cms.string(str(leptons_cfg.get("electron_id", "none"))),
    electronMaxRelIso03=cms.double(float(leptons_cfg.get("electron_max_rel_iso03", -1.0))),
    maxCpfCandidates=cms.uint32(int(features.get("max_cpf_candidates", 26))),
    maxNpfCandidates=cms.uint32(int(features.get("max_npf_candidates", 25))),
    maxSvCandidates=cms.uint32(int(features.get("max_sv_candidates", 5))),
    maxPairwiseCandidates=cms.uint32(int(features.get("max_pairwise_candidates", 30))),
    writeLowLevelFeatures=cms.bool(bool(features.get("write_low_level_features", True))),
    sampleName=cms.string(options.sampleName),
    datasetName=cms.string(options.datasetName),
    sampleXsecPb=cms.double(float(options.sampleXsecPb)),
    sampleSumWeights=cms.double(float(options.sampleSumWeights)),
    targetLumiPb=cms.double(float(options.targetLumiPb)),
    requireChargeInference=cms.bool(bool(int(options.requireOnnxChargeInference))),
    debugPrintFirstNEvents=cms.int32(int(options.debugPrintFirstNEvents)),
)

process.inputEventWeightCounter = cms.EDAnalyzer(
    "InputEventWeightCounter",
    genEventInfo=process.chargeNtuples.genEventInfo,
    isData=cms.bool(is_data),
)

if bool(int(options.enableEventPreselectionFilter)):
    process.eventPreselectionFilter = cms.EDFilter(
        "EventPreselectionFilter",
        jets=process.chargeNtuples.jets,
        jetsPuppi=process.chargeNtuples.jetsPuppi,
        muons=process.chargeNtuples.muons,
        electrons=process.chargeNtuples.electrons,
        vertices=process.chargeNtuples.vertices,
        triggerResults=process.chargeNtuples.triggerResults,
        applyHLT=process.chargeNtuples.applyHLT,
        hltPaths=process.chargeNtuples.hltPaths,
        applyJetSelection=cms.bool(bool(int(options.prefilterApplyJetSelection))),
        minNJets=process.chargeNtuples.minNJets,
        maxNJets=process.chargeNtuples.maxNJets,
        jetMinPt=process.chargeNtuples.jetMinPt,
        jetMaxEta=process.chargeNtuples.jetMaxEta,
        jetId=process.chargeNtuples.jetId,
        jetLeptonOverlapDR=process.chargeNtuples.jetLeptonOverlapDR,
        usePuppiJets=process.chargeNtuples.usePuppiJets,
        leptonMode=process.chargeNtuples.leptonMode,
        maxNLeptons=process.chargeNtuples.maxNLeptons,
        muonMinPt=process.chargeNtuples.muonMinPt,
        muonMaxEta=process.chargeNtuples.muonMaxEta,
        muonId=process.chargeNtuples.muonId,
        muonMaxRelIso04=process.chargeNtuples.muonMaxRelIso04,
        electronMinPt=process.chargeNtuples.electronMinPt,
        electronMaxEta=process.chargeNtuples.electronMaxEta,
        electronId=process.chargeNtuples.electronId,
        electronMaxRelIso03=process.chargeNtuples.electronMaxRelIso03,
        verboseSummary=cms.untracked.bool(True),
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

if bool(int(options.enableEventPreselectionFilter)):
    process.p = cms.Path(process.inputEventWeightCounter * process.eventPreselectionFilter * process.chargeNtuples)
    print(
        "[jet-charge-calib] Enabled fast EventPreselectionFilter before ChargeNtupleProducer "
        f"(applyJetSelection={bool(int(options.prefilterApplyJetSelection))})."
    )
else:
    process.p = cms.Path(process.inputEventWeightCounter * process.chargeNtuples)
if pat_task_for_onnx_inference is not None:
    process.p.associate(pat_task_for_onnx_inference)
    print("[jet-charge-calib] Associated PAT tools task to run ONNX jet tags before ChargeNtupleProducer.")
