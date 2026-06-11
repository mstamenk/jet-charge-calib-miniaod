# Jet-Charge Calibration MiniAOD Framework

This repository provides a first working framework for jet-charge calibration on MiniAOD with:

1. Ntuple production (`cmssw/`) with trigger + lepton/jet preselection, jet charge variables, flavor labels, and charge-tagger discriminator storage.
2. Local/Condor production tooling (`scripts/`, `condor/`).
3. Initial analysis plotting for debugging and fit inputs (`analysis/`).

## Repository Layout

- `cmssw/`: CMSSW plugin + python config.
- `config/`: datasets, selections, features, JSONs, weights/systematics.
- `scripts/`: DAS filelist creation, splitting, condor submission wrappers, inference setup helpers.
- `condor/`: JDL templates.
- `analysis/`: first-pass plotting/debug scripts.
- `model-onnx/`: provided ONNX model(s).

## CMSSW Setup (Required Release: `CMSSW_15_1_0_patch4`)

Start from a clean login shell on a CMS machine with CVMFS available. The
framework is a CMSSW package, so the checkout must live under the `src/`
directory of the release.

```bash
source /cvmfs/cms.cern.ch/cmsset_default.sh
cmsrel CMSSW_15_1_0_patch4
cd CMSSW_15_1_0_patch4/src
cmsenv
```

Initialize the CMSSW git area and merge the charge-tagger topic. This step is
required because the MiniAOD workflow re-runs the RobustParTAK4 charge
inference sequence before writing ntuples.

```bash
git cms-init
git cms-merge-topic jose8af:CMSSW_15_CHARGE
```

Clone this framework in the same `src/` area and install the light Python
requirements used by the helper scripts:

```bash
git clone git@github.com:mstamenk/jet-charge-calib-miniaod.git
cd jet-charge-calib-miniaod
python -m pip install -r requirements.txt
```

Install the ONNX model in the CMSSW package path expected by the
`CMSSW_15_CHARGE` configuration, link this repository's CMSSW package into the
release as `JetChargeCalib`, and build:

```bash
scripts/install_model_in_cmssw.sh "$CMSSW_BASE" model-onnx/dp-2025-071-model.onnx
ln -sfn "$(pwd)/cmssw" "$CMSSW_BASE/src/JetChargeCalib"
cd "$CMSSW_BASE/src"
scram b -j 8
```

After building, return to the framework directory for all commands below:

```bash
cd "$CMSSW_BASE/src/jet-charge-calib-miniaod"
cmsenv
```

Quick checkout checklist:

- `echo "$CMSSW_VERSION"` prints `CMSSW_15_1_0_patch4`.
- `test -L "$CMSSW_BASE/src/JetChargeCalib"` succeeds.
- `test -f "$CMSSW_BASE/src/RecoBTag/Combined/data/RobustParTAK4/PUPPI/V00/modelfile/final_model.onnx"` succeeds.
- `scram b -j 8` finishes without errors.

## Charge-Tagger Inference

By default, `cmssw/test/run_cfg.py` re-runs RobustParTAK4 charge inference on
MiniAOD `slimmedJetsPuppi` and then reads the resulting jet discriminator
branches in the ntuplizer.

The important switches are:

- `enableOnnxChargeInference=1`: run the inference sequence inside the job.
- `requireOnnxChargeInference=1`: fail if the expected charge discriminator branches are missing.
- `sampleType=mc|data|auto`: controls MC/data handling, global tags, and golden JSON use.

For debugging only, set `enableOnnxChargeInference=0 requireOnnxChargeInference=0`
to run on MiniAOD files that do not have charge-tagger branches available.

## Local Ntuple Test

Make a tiny filelist first. For example, copy one MiniAOD file from DAS into
`run/local_test/filelist_test.txt`, one file per line. Paths can be AAA paths
such as `root://xrootd-cms.infn.it//store/...`.

The helper script is the shortest smoke test:

```bash
mkdir -p run/local_test
scripts/run_local_test.sh \
  run/local_test/filelist_test.txt \
  run/local_test/jetcharge_test.root \
  Run3_24 \
  "" \
  100 \
  mc
```

The equivalent full `cmsRun` command is:

```bash
cmsRun cmssw/test/run_cfg.py \
  inputFileList=/path/to/filelist.txt \
  outputFile=jetcharge_calib_ntuple.root \
  selectionsYml=config/selections.yml \
  featuresYml=config/features.yml \
  weightsYml=config/weights.yml \
  systematicsYml=config/systematics.yml \
  goldenJsonsYml=config/golden_jsons.yml \
  era=Run3_24 \
  sampleType=mc \
  maxEvents=100
```

Selection presets for channelized production:

- `config/selections_dilep_emu_os.yml`: exactly 1 muon + 1 electron (OS), `max_njets: 4`, lepton-jet overlap removal, loose ID/iso, and `max_nleptons: 2` veto.
- `config/selections_onelep.yml`: exactly 1 lepton (`single_lepton`) baseline.

For the current Run 3 dilepton e-mu production, use
`config/selections_dilep_emu_os_prod_v2.yml`. You can switch channels by
changing only `selectionsYml=...` in the `cmsRun` command.

For data, set `sampleType=data` and provide `dataEra`:

```bash
cmsRun cmssw/test/run_cfg.py \
  inputFileList=/path/to/data_filelist.txt \
  outputFile=jetcharge_calib_ntuple_data.root \
  selectionsYml=config/selections.yml \
  featuresYml=config/features.yml \
  weightsYml=config/weights.yml \
  systematicsYml=config/systematics.yml \
  goldenJsonsYml=config/golden_jsons.yml \
  era=Run3_24 \
  dataEra=Run3_24 \
  sampleType=data \
  maxEvents=100
```

The ntuple stores normalization metadata and weights:

- `sampleName`, `datasetName`
- `sampleXsecPb`, `sampleSumWeights`, `targetLumiPb`
- `sampleNormWeight = xsec*lumi/sumW`
- `eventWeight = genWeight*puWeight*prefireWeight*sampleNormWeight`
- `job_metadata` histogram with per-job processed counters:
  `n_events_processed`, `sum_gen_weight_processed`, and written-event counterparts.

Golden JSON is applied only for data (`sampleType=data`) and selected by `dataEra` from `config/golden_jsons.yml`.

## Build Filelists / Filesets

You need a valid CMS proxy before querying DAS:

```bash
voms-proxy-init -voms cms -rfc -valid 192:00
```

```bash
python3 scripts/make_filelists.py \
  config/datasets.yml \
  --tag run3_24_dilep_emu_os_v2 \
  --latest-only \
  --xsections config/xsections.yml

python3 scripts/split_filelists.py --tag run3_24_dilep_emu_os_v2 --files-per-job 5
```

This writes:

- `filelists/<tag>/*.txt` input filelists
- `filelists/<tag>/manifest.json` sample metadata (`sample_type`, dataset, xsec/sumw/lumi)
- `filelists_split/<tag>/<sample>/job_*.txt` per-job chunks

`config/xsections.yml` includes concrete Run2/Run3 `xsec_pb` entries and
`target_lumi_pb` (e.g. `Run3_24 = 107800 /pb`).

After producing MC ntuples, compute `sum_weights` from produced outputs and
write them back to `xsections.yml` (the script now prefers per-job
`job_metadata/sum_gen_weight_processed`, so it is not biased by event selection):

```bash
python3 scripts/compute_sum_weights.py \
  --output-base /home/mstamenk/jet-charge-calibration/samples \
  --era Run3_24 \
  --version prod_v2 \
  --tag run3_24_dilep_emu_os_v2 \
  --xsections config/xsections.yml
```

## Condor Submission

Use an output base under your samples area, e.g. `/home/mstamenk/jet-charge-calibration/samples`.

```bash
python3 scripts/submit_condor.py \
  --tag run3_24_dilep_emu_os_v2 \
  --era Run3_24 \
  --version prod_v2 \
  --cmssw-base /path/to/CMSSW_15_1_0_patch4/src \
  --cfg /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/cmssw/test/run_cfg.py \
  --output-base /home/mstamenk/jet-charge-calibration/samples \
  --selections /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/selections_dilep_emu_os_prod_v2.yml \
  --features /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/features_prod_v2.yml \
  --weights /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/weights.yml \
  --systematics /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/systematics.yml \
  --fileset-manifest /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/filelists/run3_24_dilep_emu_os_v2/manifest.json \
  --golden-jsons /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/golden_jsons.yml \
  --data-era Run3_24 \
  --max-events -1
```

Add `--submit` to actually submit.

Notes:

- `sample_type` is taken from `manifest.json`, so MC/data handling is automatic per fileset.
- Add `--require-metadata` when you want submission to fail if MC normalization
  metadata are incomplete. Without it, jobs can run first and `sum_weights` can
  be filled afterward from `job_metadata`.
- For one-file smoke tests, add `--one-file --max-events 100`.
- For data, the config applies the era JSON from `golden_jsons.yml`.
- For ONNX re-run, JEC levels are set to `L2Relative,L3Absolute` on MC and add `L2L3Residual` on data.

## Analysis Plots

```bash
python3 analysis/plot_basic.py --input "jetcharge_calib_ntuple.root" --outdir analysis/plots
```

This produces:

- trigger efficiency vs lepton `pT`
- top-mass proxy
- lepton `pT`
- jet `pT`
- jet flavour
- jet charge score
- debug counters (`nJetSel`, `nLepSel`)
