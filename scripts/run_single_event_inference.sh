#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cmssw_base="${CMSSW_BASE:-/home/mstamenk/jet-charge-calibration/CMSSW_15_1_0_patch4}"
export SCRAM_ARCH="${SCRAM_ARCH:-el9_amd64_gcc12}"

dataset="${1:-/BTagMu/Run2016H-UL2016_MiniAODv2-v1/MINIAOD}"
event_id="${2:-283876:389:570269675}"
label="${3:-run2016h_283876_389_570269675}"

work_dir="${repo_dir}/run/single_event/${label}"
work_dir_rel="run/single_event/${label}"
picked_file="${work_dir}/picked_${label}.root"
filelist="${work_dir}/picked_${label}.txt"
ntuple="${work_dir_rel}/jetcharge_${label}.root"

mkdir -p "${work_dir}"

source /cvmfs/cms.cern.ch/cmsset_default.sh
cd "${cmssw_base}/src"
eval "$(scram runtime -sh)"
cd "${repo_dir}"
ulimit -s unlimited

if [[ ! -s "${picked_file}" ]]; then
  IFS=: read -r run lumi event <<< "${event_id}"
  input_file="$(dasgoclient -query="file dataset=${dataset} run=${run} lumi=${lumi}" | head -n 1)"
  if [[ -z "${input_file}" ]]; then
    echo "No DAS file found for dataset=${dataset}, run=${run}, lumi=${lumi}" >&2
    exit 1
  fi
  echo "DAS MiniAOD file: ${input_file}"
  edmCopyPickMerge \
    outputFile="${picked_file}" \
    eventsToProcess="${event_id}" \
    inputFiles="root://cms-xrd-global.cern.ch/${input_file}"

  if ! edmFileUtil -e "${picked_file}" | grep -q ' 1 events,'; then
    echo "Picked file does not contain exactly one event: ${picked_file}" >&2
    edmFileUtil -e "${picked_file}" >&2
    exit 1
  fi
fi

printf 'file:%s\n' "${picked_file}" > "${filelist}"

cmsRun cmssw/test/run_cfg.py \
  inputFileList="${filelist}" \
  outputFile="${ntuple}" \
  selectionsYml=config/selections_single_event.yml \
  featuresYml=config/features.yml \
  weightsYml=config/weights.yml \
  systematicsYml=config/systematics.yml \
  era=UL16 \
  dataEra=UL16 \
  maxEvents=-1 \
  sampleType=data \
  debugPrintFirstNEvents=1 \
  requireOnnxChargeInference=1 \
  enableOnnxChargeInference=1 \
  enableEventPreselectionFilter=0

python3 scripts/print_single_event_jets.py "${ntuple}"
