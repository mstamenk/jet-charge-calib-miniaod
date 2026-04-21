#!/bin/bash
set -euo pipefail

cmssw_src="${1:-${CMSSW_BASE:-}}"
if [[ -z "${cmssw_src}" ]]; then
  echo "CMSSW path not provided. Pass CMSSW_15_0_17/src or set CMSSW_BASE." >&2
  exit 1
fi

# Accept CMSSW_BASE (no /src) or CMSSW src path.
if [[ -d "${cmssw_src}/src" ]]; then
  cmssw_src="${cmssw_src}/src"
fi

set +u
source /cvmfs/cms.cern.ch/cmsset_default.sh
set -u
cd "${cmssw_src}"

if [[ -z "${SCRAM_ARCH:-}" ]]; then
  export SCRAM_ARCH="el9_amd64_gcc12"
fi

tmp_env="$(mktemp)"
if ! scram runtime -sh > "${tmp_env}"; then
  echo "scram runtime failed for ${cmssw_src}" >&2
  rm -f "${tmp_env}"
  exit 1
fi
source "${tmp_env}"
rm -f "${tmp_env}"

if ! command -v cmsRun >/dev/null 2>&1; then
  echo "cmsRun not found in PATH after scram runtime." >&2
  exit 1
fi
