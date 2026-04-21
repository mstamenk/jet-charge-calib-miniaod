#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <CMSSW_BASE_OR_SRC> [model_path]" >&2
  exit 1
fi

cmssw_path="$1"
model_path="${2:-model-onnx/dp-2025-071-model.onnx}"

if [[ -d "${cmssw_path}/src" ]]; then
  cmssw_src="${cmssw_path}/src"
else
  cmssw_src="${cmssw_path}"
fi

if [[ ! -d "${cmssw_src}" ]]; then
  echo "CMSSW src path not found: ${cmssw_src}" >&2
  exit 2
fi

if [[ ! -f "${model_path}" ]]; then
  echo "Model file not found: ${model_path}" >&2
  exit 3
fi

target_dir="${cmssw_src}/RecoBTag/Combined/data/RobustParTAK4/PUPPI/V00/modelfile"
target_file="${target_dir}/final_model.onnx"

mkdir -p "${target_dir}"
cp "${model_path}" "${target_file}"

echo "Installed model -> ${target_file}"
