#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <input_filelist.txt> <output.root> [era] [dataEra] [maxEvents]" >&2
  exit 1
fi

input_filelist="$1"
output_file="$2"
era="${3:-UL18}"
data_era="${4:-$era}"
max_events="${5:-200}"

cmsRun cmssw/test/run_cfg.py \
  inputFileList="${input_filelist}" \
  outputFile="${output_file}" \
  selectionsYml=config/selections.yml \
  featuresYml=config/features.yml \
  weightsYml=config/weights.yml \
  systematicsYml=config/systematics.yml \
  goldenJsonsYml=config/golden_jsons.yml \
  era="${era}" \
  dataEra="${data_era}" \
  maxEvents="${max_events}"
