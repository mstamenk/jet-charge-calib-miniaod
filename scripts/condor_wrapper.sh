#!/bin/bash
set -euo pipefail

usage() {
  echo "Usage: $0 --cmssw-base PATH --cfg PATH --input-filelist PATH --output-file PATH \
    --selections PATH --features PATH --weights PATH --systematics PATH \
    [--golden-json PATH] [--golden-jsons-yml PATH] [--data-era ERA] [--era ERA] [--sample-type auto|data|mc] \
    [--sample-name NAME] [--dataset-name DATASET] [--sample-xsec-pb XSEC] [--sample-sum-weights SUMW] \
    [--target-lumi-pb LUMI] [--enable-event-prefilter 0|1] [--prefilter-apply-jet-selection 0|1] \
    [--sequential-files-in-job 0|1] [--max-events N]" >&2
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
sample_type="auto"
sample_name=""
dataset_name=""
sample_xsec_pb="-1"
sample_sum_weights="0"
target_lumi_pb="0"
enable_event_prefilter="1"
prefilter_apply_jet_selection="0"
sequential_files_in_job="0"
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
    --sample-type)
      sample_type="$2"; shift 2 ;;
    --sample-name)
      sample_name="$2"; shift 2 ;;
    --dataset-name)
      dataset_name="$2"; shift 2 ;;
    --sample-xsec-pb)
      sample_xsec_pb="$2"; shift 2 ;;
    --sample-sum-weights)
      sample_sum_weights="$2"; shift 2 ;;
    --target-lumi-pb)
      target_lumi_pb="$2"; shift 2 ;;
    --enable-event-prefilter)
      enable_event_prefilter="$2"; shift 2 ;;
    --prefilter-apply-jet-selection)
      prefilter_apply_jet_selection="$2"; shift 2 ;;
    --sequential-files-in-job)
      sequential_files_in_job="$2"; shift 2 ;;
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
# Condor input files are transferred to scratch; keep this before env setup,
# since env_brux.sh changes working directory to CMSSW/src.
SCRATCH_DIR="${_CONDOR_SCRATCH_DIR:-$(pwd)}"
source "${SCRIPT_DIR}/env_brux.sh" "${cmssw_base}"

resolve_local_input() {
  local path="$1"
  if [[ -z "${path}" ]]; then
    echo ""
    return
  fi
  if [[ -f "${path}" ]]; then
    echo "${path}"
    return
  fi
  if [[ -f "${SCRATCH_DIR}/${path}" ]]; then
    echo "${SCRATCH_DIR}/${path}"
    return
  fi
  local base
  base="$(basename "${path}")"
  if [[ -f "${base}" ]]; then
    echo "${base}"
    return
  fi
  if [[ -f "${SCRATCH_DIR}/${base}" ]]; then
    echo "${SCRATCH_DIR}/${base}"
    return
  fi
  echo "${path}"
}

cfg_local="$(resolve_local_input "${cfg}")"
input_filelist_local="$(resolve_local_input "${input_filelist}")"
selections_yml_local="$(resolve_local_input "${selections_yml}")"
features_yml_local="$(resolve_local_input "${features_yml}")"
weights_yml_local="$(resolve_local_input "${weights_yml}")"
systematics_yml_local="$(resolve_local_input "${systematics_yml}")"
golden_json_local="$(resolve_local_input "${golden_json}")"
golden_jsons_yml_local="$(resolve_local_input "${golden_jsons_yml}")"

run_cmsrun() {
  local input_list="$1"
  local out_file="$2"
  cmsRun "${cfg_local}" \
    inputFileList="${input_list}" \
    outputFile="${out_file}" \
    maxEvents="${max_events}" \
    selectionsYml="${selections_yml_local}" \
    featuresYml="${features_yml_local}" \
    weightsYml="${weights_yml_local}" \
    systematicsYml="${systematics_yml_local}" \
    goldenJson="${golden_json_local}" \
    goldenJsonsYml="${golden_jsons_yml_local}" \
    dataEra="${data_era}" \
    era="${era}" \
    sampleType="${sample_type}" \
    sampleName="${sample_name}" \
    datasetName="${dataset_name}" \
    sampleXsecPb="${sample_xsec_pb}" \
    sampleSumWeights="${sample_sum_weights}" \
    targetLumiPb="${target_lumi_pb}" \
    enableEventPreselectionFilter="${enable_event_prefilter}" \
    prefilterApplyJetSelection="${prefilter_apply_jet_selection}"
}

if [[ "${sequential_files_in_job}" == "1" ]]; then
  mapfile -t _all_inputs < <(awk 'NF{print $0}' "${input_filelist_local}")
  n_inputs="${#_all_inputs[@]}"
  if [[ "${n_inputs}" -eq 0 ]]; then
    echo "No input files listed in ${input_filelist_local}" >&2
    exit 2
  fi
  echo "[condor_wrapper] Sequential file mode enabled: processing ${n_inputs} files one-by-one."
  tmp_dir="$(mktemp -d "${SCRATCH_DIR}/seq_inputs.XXXXXX")"
  part_outputs=()
  idx=0
  for infile in "${_all_inputs[@]}"; do
    idx=$((idx + 1))
    one_list="${tmp_dir}/input_${idx}.txt"
    one_out="${tmp_dir}/part_${idx}.root"
    printf '%s\n' "${infile}" > "${one_list}"
    echo "[condor_wrapper] (${idx}/${n_inputs}) cmsRun on ${infile}"
    run_cmsrun "${one_list}" "${one_out}"
    if [[ ! -s "${one_out}" ]]; then
      alt_out="${one_out%.root}_numEvent${max_events}.root"
      if [[ "${one_out}" == *.root && "${max_events}" =~ ^[0-9]+$ && -s "${alt_out}" ]]; then
        mv -f "${alt_out}" "${one_out}"
      fi
    fi
    if [[ ! -s "${one_out}" ]]; then
      echo "Sequential mode produced missing/empty output for file ${infile}" >&2
      exit 2
    fi
    part_outputs+=("${one_out}")
  done
  if [[ "${#part_outputs[@]}" -eq 1 ]]; then
    mv -f "${part_outputs[0]}" "${output_file}"
  else
    hadd -f "${output_file}" "${part_outputs[@]}"
  fi
  rm -rf "${tmp_dir}"
else
  run_cmsrun "${input_filelist_local}" "${output_file}"
fi

if [[ ! -s "${output_file}" ]]; then
  output_file_numevent="${output_file%.root}_numEvent${max_events}.root"
  if [[ "${output_file}" == *.root && "${max_events}" =~ ^[0-9]+$ && -s "${output_file_numevent}" ]]; then
    mv -f "${output_file_numevent}" "${output_file}"
  fi
fi

if [[ ! -s "${output_file}" ]]; then
  echo "Output file missing or empty: ${output_file}" >&2
  if [[ "${output_file}" == *.root && "${max_events}" =~ ^[0-9]+$ ]]; then
    echo "Checked alternate output file: ${output_file%.root}_numEvent${max_events}.root" >&2
  fi
  exit 2
fi
