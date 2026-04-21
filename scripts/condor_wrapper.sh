#!/bin/bash
set -euo pipefail

usage() {
  echo "Usage: $0 --cmssw-base PATH --cfg PATH --input-filelist PATH --output-file PATH \
    --selections PATH --features PATH --weights PATH --systematics PATH \
    [--golden-json PATH] [--golden-jsons-yml PATH] [--data-era ERA] [--era ERA] [--max-events N]" >&2
}

cmssw_base=""
cfg=""
input_filelist=""
output_file=""
selections_yml=""
features_yml=""
weights_yml=""
systematics_yml=""
golden_json=""
golden_jsons_yml=""
data_era=""
era=""
max_events="-1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cmssw-base)
      cmssw_base="$2"; shift 2 ;;
    --cfg)
      cfg="$2"; shift 2 ;;
    --input-filelist)
      input_filelist="$2"; shift 2 ;;
    --output-file)
      output_file="$2"; shift 2 ;;
    --selections)
      selections_yml="$2"; shift 2 ;;
    --features)
      features_yml="$2"; shift 2 ;;
    --weights)
      weights_yml="$2"; shift 2 ;;
    --systematics)
      systematics_yml="$2"; shift 2 ;;
    --golden-json)
      golden_json="$2"; shift 2 ;;
    --golden-jsons-yml)
      golden_jsons_yml="$2"; shift 2 ;;
    --data-era)
      data_era="$2"; shift 2 ;;
    --era)
      era="$2"; shift 2 ;;
    --max-events)
      max_events="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage; exit 1 ;;
  esac
 done

if [[ -z "${cmssw_base}" || -z "${cfg}" || -z "${input_filelist}" || -z "${output_file}" ]]; then
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/env_brux.sh" "${cmssw_base}"

cmsRun "${cfg}" \
  inputFileList="${input_filelist}" \
  outputFile="${output_file}" \
  maxEvents="${max_events}" \
  selectionsYml="${selections_yml}" \
  featuresYml="${features_yml}" \
  weightsYml="${weights_yml}" \
  systematicsYml="${systematics_yml}" \
  goldenJson="${golden_json}" \
  goldenJsonsYml="${golden_jsons_yml}" \
  dataEra="${data_era}" \
  era="${era}"

if [[ ! -s "${output_file}" ]]; then
  echo "Output file missing or empty: ${output_file}" >&2
  exit 2
fi
