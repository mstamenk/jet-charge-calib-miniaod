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

Create and enter the CMSSW release:

```bash
source /cvmfs/cms.cern.ch/cmsset_default.sh
cmsrel CMSSW_15_1_0_patch4
cd CMSSW_15_1_0_patch4/src
cmsenv
```

Clone this framework in the same `src` area:

```bash
git clone git@github.com:mstamenk/jet-charge-calib-miniaod.git
cd jet-charge-calib-miniaod
python -m pip install -r requirements.txt
ln -s "$(pwd)/cmssw" ../JetChargeCalib
cd ..
scram b -j 8
```

## CMSSW Charge-Tagger Integration (`CMSSW_15_CHARGE`)

For robust ParT jet-charge inference branches in MiniAOD, merge the charge topic in the CMSSW release:

```bash
cd /path/to/CMSSW_15_1_0_patch4/src
cmsenv
git cms-init
git cms-merge-topic jose8af:CMSSW_15_CHARGE
scram b -j 8
```

Then (re)link the framework package if needed:

```bash
ln -s /path/to/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/cmssw JetChargeCalib
scram b -j 8
```

## Inference Prerequisites (CMSSW_15_CHARGE)

The ntuplizer reads charge-tagger outputs from MiniAOD jet discriminators; it does **not** run ONNX itself.

You need:

1. A CMSSW release with the `CMSSW_15_CHARGE` content merged.
2. The ONNX model copied to the expected CMSSW path:

```bash
scripts/install_model_in_cmssw.sh /path/to/CMSSW_15_1_0_patch4 model-onnx/dp-2025-071-model.onnx
```

This installs to:

`RecoBTag/Combined/data/RobustParTAK4/PUPPI/V00/modelfile/final_model.onnx`

## Local Ntuple Test

```bash
cmsRun cmssw/test/run_cfg.py \
  inputFileList=/path/to/filelist.txt \
  outputFile=jetcharge_calib_ntuple.root \
  selectionsYml=config/selections.yml \
  featuresYml=config/features.yml \
  weightsYml=config/weights.yml \
  systematicsYml=config/systematics.yml \
  goldenJsonsYml=config/golden_jsons.yml \
  era=UL18 \
  dataEra=UL18 \
  maxEvents=100
```

## Build Filelists

```bash
python3 scripts/make_filelists.py config/datasets.yml --tag v1 --latest-only --max-files 5
python3 scripts/split_filelists.py --tag v1 --files-per-job 5
```

## Condor Submission

Use an output base under your samples area, e.g. `/home/mstamenk/jet-charge-calibration/samples`.

```bash
python3 scripts/submit_condor.py \
  --tag v1 \
  --era UL18 \
  --version v1 \
  --cmssw-base /path/to/CMSSW_15_1_0_patch4/src \
  --cfg /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/cmssw/test/run_cfg.py \
  --output-base /home/mstamenk/jet-charge-calibration/samples \
  --selections /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/selections.yml \
  --features /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/features.yml \
  --weights /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/weights.yml \
  --systematics /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/systematics.yml \
  --golden-jsons /isilon/export/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4/src/jet-charge-calib-miniaod/config/golden_jsons.yml \
  --data-era UL18
```

Add `--submit` to actually submit.

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
