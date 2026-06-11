#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <input_filelist.txt> <output.root> [era] [dataEra] [maxEvents] [sampleType] [debugPrintFirstNEvents] [requireOnnxChargeInference] [enableOnnxChargeInference]" >&2
  exit 1
fi

input_filelist="$1"
output_file="$2"
era="${3:-UL18}"
data_era="${4:-}"
max_events="${5:-200}"
sample_type="${6:-auto}"
debug_print_first_n_events="${7:-0}"
require_onnx_charge_inference="${8:-1}"
enable_onnx_charge_inference="${9:-1}"

# Convenience form: pass maxEvents as the 4th argument for MC tests.
if [[ $# -eq 4 && "${4}" =~ ^[0-9]+$ ]]; then
  data_era=""
  max_events="${4}"
fi

cmsrun_args=(
  cmssw/test/run_cfg.py
  inputFileList="${input_filelist}"
  outputFile="${output_file}"
  selectionsYml=config/selections.yml
  featuresYml=config/features.yml
  weightsYml=config/weights.yml
  systematicsYml=config/systematics.yml
  goldenJsonsYml=config/golden_jsons.yml
  era="${era}"
  maxEvents="${max_events}"
  sampleType="${sample_type}"
  debugPrintFirstNEvents="${debug_print_first_n_events}"
  requireOnnxChargeInference="${require_onnx_charge_inference}"
  enableOnnxChargeInference="${enable_onnx_charge_inference}"
)

if [[ -n "${data_era}" ]]; then
  cmsrun_args+=(dataEra="${data_era}")
fi

cmsRun "${cmsrun_args[@]}"
