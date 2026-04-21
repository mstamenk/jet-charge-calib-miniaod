#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import yaml
except ImportError:
    print("Missing PyYAML. Install with pip or use a CMSSW environment that includes it.", file=sys.stderr)
    sys.exit(1)

AAA_PREFIX = "root://cmsxrootd.fnal.gov/"

DEFAULT_ERAS = [
    "UL16",
    "UL17",
    "UL18",
    "Run3_22",
    "Run3_22EE",
    "Run3_23",
    "Run3_23BPix",
    "Run3_24",
    "Run3_25",
]

ERA_CAMPAIGNS = {
    "UL16": {
        "mc": ["RunIISummer20UL16MiniAODv2-*"],
        "data": ["Run2016*"],
    },
    "UL17": {
        "mc": ["RunIISummer20UL17MiniAODv2-*"],
        "data": ["Run2017*"],
    },
    "UL18": {
        "mc": ["RunIISummer20UL18MiniAODv2-*"],
        "data": ["Run2018*"],
    },
    "Run3_22": {
        "mc": ["Run3Summer22MiniAODv4-*"],
        "data": ["Run2022*"],
    },
    "Run3_22EE": {
        "mc": ["Run3Summer22EEMiniAODv4-*"],
        "data": ["Run2022*"],
    },
    "Run3_23": {
        "mc": ["Run3Summer23MiniAODv4-*"],
        "data": ["Run2023*"],
    },
    "Run3_23BPix": {
        "mc": ["Run3Summer23BPixMiniAODv4-*"],
        "data": ["Run2023*"],
    },
    "Run3_24": {
        "mc": [
            "RunIII2024Summer24*MiniAODv6*",

        ],
        "data": ["Run2024*"],
    },
    "Run3_25": {
        "mc": [
            "Run3Summer25MiniAODv4-*",
            "Run3Summer25MiniAODv5-*",
            "Run3Summer25*MiniAODv4-*",
            "Run3Summer25*MiniAODv5-*",
        ],
        "data": ["Run2025*"],
    },
}

MC_SAMPLES = {
    "qcd": [
        "QCD_HT*to*_*",
        "QCD_Pt*",
        "QCD_PT*",
        "QCD_Bin-PT*",
    ],
    "ttbar_hadronic": [
        "TTto4Q_TuneCP5_13p6TeV_powheg-pythia8*",
        "TTto4Q-2Jets_TuneCP5_13p6TeV_amcatnloFXFX-pythia8*",
    ],
    "ttbar_semileptonic": [
        "TTtoLNu2Q_TuneCP5_13p6TeV_powheg-pythia8*",
        "TTtoLNu2Q-2Jets_TuneCP5_13p6TeV_amcatnloFXFX-pythia8*",
    ],
    "ttbar_dileptonic": [
        "TTto2L2Nu_TuneCP5_13p6TeV_powheg-pythia8*",
        "TTto2L2Nu-2Jets_TuneCP5_13p6TeV_amcatnloFXFX-pythia8*",
    ],
    "diboson_ww": [
        "WWTo2L2Q_*",
        "WWTo2Nu2Q_*",
        "WWTo4Q_*",
    ],
    "diboson_wz": [
        "WZTo2Q2L_*",
        "WZTo2Q2Nu_*",
    ],
    "diboson_zz": [
        "ZZTo2Q2L_*",
        "ZZTo2Q2Nu_*",
        "ZZTo4Q_*",
    ],
    "dyjets": [
        "DYJetsToLL_M-50_TuneCP5_13p6TeV-madgraphMLM-pythia8",
        "DYto2E-4Jets*",
        "DYto2Mu-4Jets*",
    ],
    "wjets_leptonic": [
        "WJetsToLNu_*",
        "WToLNu_*",
        "WtoLNu-4Jets*",
    ],
    "wjets_hadronic": [
        "WJetsToQQ_*",
        "WToQQ_*",
    ],
    "dihiggs": [
        "GluGluToHHTo4B*",
        "GluGluToHHTo2B2Tau*",
    ],
    "trihiggs": [
        "GluGluToHHH*",
        "VBFToHHH*",
        "HHHTo*",
    ],
}

ERA_DATASTREAMS = {
    "UL16": {"Muon": ["SingleMuon"], "EGamma": ["SingleElectron"], "BTagCSV": ["BTagCSV"]},
    "UL17": {"Muon": ["SingleMuon"], "EGamma": ["SingleElectron"], "BTagCSV": ["BTagCSV"]},
    "UL18": {"Muon": ["SingleMuon"], "EGamma": ["EGamma"], "JetHT": ["JetHT"]},
    "Run3_22": {"Muon": ["Muon"], "EGamma": ["EGamma"], "JetMET": ["JetMET"]},
    "Run3_22EE": {"Muon": ["Muon"], "EGamma": ["EGamma"], "JetMET": ["JetMET"]},
    "Run3_23": {"Muon": ["Muon"], "EGamma": ["EGamma"], "ParkingHH": ["ParkingHH"]},
    "Run3_23BPix": {"Muon": ["Muon"], "EGamma": ["EGamma"], "ParkingHH": ["ParkingHH"]},
    "Run3_24": {"Muon": ["Muon","Muon0","Muon1","Muon2","Muon3"], "EGamma": ["EGamma0","EGamma1"], "ParkingHH": ["ParkingHH"]},
    "Run3_25": {"Muon": ["Muon"], "EGamma": ["EGamma"], "ParkingHH": ["ParkingHH"]},
}

MC_SAMPLE_PROCESSING_INCLUDE = {
    "dyjets": {
        "Run3_22": ["Run3Summer22MiniAODv4-130X_mcRun3_2022_realistic_v5-v2"],
        "Run3_22EE": ["Run3Summer22MiniAODv4-130X_mcRun3_2022_realistic_v5-v2"],
    },
}

MC_SAMPLE_PROCESSING_EXCLUDE = {
    "dyjets": ["ALCARECO", "forPOG", "Pilot", "pilot"],
}

MC_DATASET_EXCLUDE = ["BGenFilter", "MuEnriched"]

ERA_DATA_RUNS = {
    "Run3_22": ["Run2022A", "Run2022B", "Run2022C", "Run2022D"],
    "Run3_22EE": ["Run2022E", "Run2022F", "Run2022G"],
    "Run3_23": ["Run2023C"],
    "Run3_23BPix": ["Run2023D"],
    "Run3_24": ["Run2024B", "Run2024C", "Run2024D", "Run2024E"],
}


def _run_das_query(dataset, query_filter=None):
    query = f"file dataset={dataset}"
    if query_filter:
        query += f" {query_filter}"
    cmd = ["dasgoclient", "-query", query]
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [AAA_PREFIX + f for f in files]


def _run_das_dataset_query(dataset_pattern, query_filter=None):
    query = f"dataset dataset={dataset_pattern}"
    if query_filter:
        query += f" {query_filter}"
    cmd = ["dasgoclient", "-query", query]
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _default_workers():
    return max(1, min(16, os.cpu_count() or 4))


def _dataset_processing(dataset):
    parts = dataset.strip("/").split("/")
    if len(parts) != 3:
        return ""
    return parts[1]

def _dataset_primary(dataset):
    parts = dataset.strip("/").split("/")
    if len(parts) != 3:
        return ""
    return parts[0]

def _dataset_group_key(dataset):
    parts = dataset.strip("/").split("/")
    if len(parts) != 3:
        return dataset
    processing = re.sub(r"-v\d+$", "", parts[1])
    return f"/{parts[0]}/{processing}/{parts[2]}"


def _dataset_data_run_key(dataset):
    parts = dataset.strip("/").split("/")
    if len(parts) != 3:
        return dataset
    processing = parts[1]
    run_key = processing.split("-", 1)[0]
    return f"/{parts[0]}/{run_key}/{parts[2]}"


def _dataset_version(dataset):
    parts = dataset.strip("/").split("/")
    if len(parts) != 3:
        return 0
    match = re.search(r"-v(\d+)$", parts[1])
    if not match:
        return 0
    return int(match.group(1))


def _data_processing_priority(processing):
    if "Run2024" in processing or "Run2025" in processing:
        return ["PromptReco", "Prompt"]
    if "Run2022" in processing or "Run2023" in processing:
        return ["22Sep2023"]
    return []


def _filter_data_by_run(era, datasets):
    allowed = ERA_DATA_RUNS.get(era)
    if not allowed:
        return datasets
    filtered = []
    for dataset in datasets:
        if any(f"/{prefix}-" in dataset for prefix in allowed):
            filtered.append(dataset)
    return filtered


def _select_preferred_data(datasets):
    grouped = {}
    for dataset in datasets:
        grouped.setdefault(_dataset_data_run_key(dataset), []).append(dataset)
    selected = []
    for _, entries in grouped.items():
        preferred = []
        for dataset in entries:
            parts = dataset.strip("/").split("/")
            if len(parts) != 3:
                continue
            processing = parts[1]
            keywords = _data_processing_priority(processing)
            if keywords and any(keyword in processing for keyword in keywords):
                preferred.append(dataset)
        if preferred:
            selected.append(max(preferred, key=_dataset_version))
        else:
            selected.append(max(entries, key=_dataset_version))
    return sorted(set(selected))


def _select_latest(datasets):
    grouped = {}
    for dataset in datasets:
        grouped.setdefault(_dataset_group_key(dataset), []).append(dataset)
    selected = []
    for _, entries in grouped.items():
        selected.append(max(entries, key=_dataset_version))
    return sorted(set(selected))


def _filter_by_processing(datasets, include_substrings=None, exclude_substrings=None):
    if include_substrings:
        datasets = [
            dataset
            for dataset in datasets
            if any(sub in _dataset_processing(dataset) for sub in include_substrings)
        ]
    if exclude_substrings:
        datasets = [
            dataset
            for dataset in datasets
            if not any(sub in _dataset_processing(dataset) for sub in exclude_substrings)
        ]
    return datasets


def _filter_mc_datasets(era, sample, datasets):
    if MC_DATASET_EXCLUDE:
        datasets = [dataset for dataset in datasets if not any(tag in dataset for tag in MC_DATASET_EXCLUDE)]
    include = None
    include_cfg = MC_SAMPLE_PROCESSING_INCLUDE.get(sample)
    if isinstance(include_cfg, dict):
        include = include_cfg.get(era)
    elif include_cfg:
        include = include_cfg
    exclude = MC_SAMPLE_PROCESSING_EXCLUDE.get(sample)
    datasets = _filter_by_processing(datasets, include_substrings=include, exclude_substrings=exclude)
    if sample == "qcd":
        datasets = [ds for ds in datasets if "TuneCP5" in ds]
        ht = [ds for ds in datasets if _dataset_primary(ds).startswith("QCD_HT")]
        if ht:
            return ht
        binpt = [ds for ds in datasets if _dataset_primary(ds).startswith("QCD_Bin-PT")]
        if binpt:
            return binpt
        pt = [
            ds
            for ds in datasets
            if _dataset_primary(ds).startswith("QCD_Pt") or _dataset_primary(ds).startswith("QCD_PT")
        ]
        if pt:
            return pt
    return datasets


def _resolve_dataset_versions(datasets, dataset_query_filter, prefer_latest, era="", sample=""):
    resolved = []
    for dataset in datasets:
        if not isinstance(dataset, str):
            continue
        if "*" in dataset:
            found = _run_das_dataset_query(dataset, query_filter=dataset_query_filter)
            if found:
                resolved.extend(found)
            else:
                resolved.append(dataset)
            continue
        parts = dataset.strip("/").split("/")
        if prefer_latest and len(parts) == 3:
            processing = parts[1]
            if re.search(r"-v\d+$", processing):
                processing_glob = re.sub(r"-v\d+$", "-v*", processing)
                pattern = f"/{parts[0]}/{processing_glob}/{parts[2]}"
                found = _run_das_dataset_query(pattern, query_filter=dataset_query_filter)
                if found:
                    resolved.extend(found)
                else:
                    resolved.append(dataset)
                continue
        resolved.append(dataset)

    resolved = sorted(set(resolved))
    if any(ds.endswith("/MINIAODSIM") for ds in resolved):
        resolved = _filter_mc_datasets(era, sample, resolved)
    if prefer_latest:
        if resolved and resolved[0].endswith("/MINIAOD"):
            return _select_preferred_data(resolved)
        return _select_latest(resolved)
    return resolved


def _sanitize_dataset_tag(dataset):
    tag = dataset.strip("/").replace("/", "__")
    tag = tag.replace("*", "")
    return tag


def _iter_dataset_entries(cfg, prefix=None):
    if prefix is None:
        prefix = []
    if not isinstance(cfg, dict):
        return
    for key, value in cfg.items():
        if isinstance(value, dict):
            if any(field in value for field in ("dataset", "datasets", "dataset_query", "dataset_queries")):
                yield prefix + [key], value
            else:
                yield from _iter_dataset_entries(value, prefix + [key])


def _extract_era_from_path(path):
    for token in path:
        if token in ERA_CAMPAIGNS:
            return token
    return ""


def _should_keep_path(path, filter_eras):
    if not filter_eras:
        return True
    era = _extract_era_from_path(path)
    return era in filter_eras


def _resolve_datasets(sample_cfg, dataset_query_filter, prefer_latest, era="", sample=""):
    if "dataset" in sample_cfg:
        datasets = [sample_cfg["dataset"]]
        return _resolve_dataset_versions(datasets, dataset_query_filter, prefer_latest, era=era, sample=sample)
    if "datasets" in sample_cfg:
        datasets = list(sample_cfg["datasets"])
        return _resolve_dataset_versions(datasets, dataset_query_filter, prefer_latest, era=era, sample=sample)
    queries = sample_cfg.get("dataset_query") or sample_cfg.get("dataset_queries")
    if not queries:
        return []
    if isinstance(queries, str):
        queries = [queries]
    datasets = []
    for query in queries:
        datasets.extend(_run_das_dataset_query(query, query_filter=dataset_query_filter))
    datasets = sorted(set(datasets))
    if sample:
        datasets = _filter_mc_datasets(era, sample, datasets)
    if prefer_latest:
        if datasets and datasets[0].endswith("/MINIAOD"):
            return _select_preferred_data(datasets)
        return _select_latest(datasets)
    return datasets


def _discover_datasets(eras, dataset_query_filter, prefer_latest, workers):
    output = {"mc": {}, "data": {}}
    query_tasks = []
    samples_by_group = {"mc": {}, "data": {}}

    for era in eras:
        campaigns = ERA_CAMPAIGNS.get(era, {})
        mc_campaigns = campaigns.get("mc", [])
        data_campaigns = campaigns.get("data", [])
        if mc_campaigns:
            output["mc"][era] = {}
        if data_campaigns:
            output["data"][era] = {}

        for sample, primaries in MC_SAMPLES.items():
            if not mc_campaigns:
                continue
            samples_by_group["mc"].setdefault(era, set()).add(sample)
            for primary in primaries:
                for campaign in mc_campaigns:
                    pattern = f"/{primary}/{campaign}/MINIAODSIM"
                    print(f"[discover] {era} mc {sample}: {pattern}")
                    query_tasks.append(("mc", era, sample, pattern))

        era_streams = ERA_DATASTREAMS.get(era, {})
        for sample, primaries in era_streams.items():
            if not data_campaigns:
                continue
            samples_by_group["data"].setdefault(era, set()).add(sample)
            for primary in primaries:
                for campaign in data_campaigns:
                    pattern = f"/{primary}/{campaign}/MINIAOD"
                    print(f"[discover] {era} data {sample}: {pattern}")
                    query_tasks.append(("data", era, sample, pattern))

    results = {}
    if query_tasks:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_key = {
                executor.submit(_run_das_dataset_query, pattern, query_filter=dataset_query_filter): (group, era, sample)
                for group, era, sample, pattern in query_tasks
            }
            for future in as_completed(future_to_key):
                group, era, sample = future_to_key[future]
                try:
                    datasets = future.result()
                except subprocess.CalledProcessError as exc:
                    print(f"[discover] {group} {era} {sample}: DAS query failed ({exc})")
                    continue
                key = (group, era, sample)
                results.setdefault(key, set()).update(datasets)

    for era, samples in samples_by_group["mc"].items():
        for sample in sorted(samples):
            datasets = sorted(results.get(("mc", era, sample), set()))
            datasets = _filter_mc_datasets(era, sample, datasets)
            if datasets:
                print(f"[discover] {era} mc {sample}: {len(datasets)} dataset(s) found")
                output["mc"][era][sample] = {
                    "datasets": _select_latest(datasets) if prefer_latest else datasets
                }
            else:
                print(f"[discover] {era} mc {sample}: 0 dataset(s) found")

    for era, samples in samples_by_group["data"].items():
        for sample in sorted(samples):
            datasets = sorted(results.get(("data", era, sample), set()))
            datasets = _filter_data_by_run(era, datasets)
            if datasets:
                print(f"[discover] {era} data {sample}: {len(datasets)} dataset(s) found")
                if prefer_latest:
                    datasets = _select_preferred_data(datasets)
                output["data"][era][sample] = {"datasets": datasets}
            else:
                print(f"[discover] {era} data {sample}: 0 dataset(s) found")

    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", help="Path to datasets.yml (input or output with --discover)")
    parser.add_argument("--tag", help="Output tag (used for filelists/<tag>)")
    parser.add_argument("--max-files", type=int, default=0, help="Limit number of files per sample")
    parser.add_argument("--query-filter", default="", help="Optional dasgoclient file query filter")
    parser.add_argument("--dataset-query-filter", default="", help="Optional dasgoclient dataset query filter")
    parser.add_argument("--discover", action="store_true", help="Discover datasets in DAS and write YAML to config path")
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Keep only the newest -vN dataset per processing string",
    )
    parser.add_argument(
        "--recommended-only",
        action="store_true",
        help="Deprecated alias for --latest-only (kept for compatibility)",
    )
    parser.add_argument(
        "--eras",
        default=",".join(DEFAULT_ERAS),
        help="Comma-separated eras for discovery (default: %(default)s)",
    )
    parser.add_argument(
        "--filter-era",
        default="",
        help="Comma-separated eras to keep when generating filelists (non-discover mode)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=_default_workers(),
        help="Number of parallel DAS queries (default: %(default)s)",
    )
    args = parser.parse_args()
    args.workers = max(1, args.workers)

    if args.discover:
        eras = [era.strip() for era in args.eras.split(",") if era.strip()]
        prefer_latest = args.latest_only or args.recommended_only
        discovered = _discover_datasets(eras, args.dataset_query_filter, prefer_latest, args.workers)
        with open(args.config, "w", encoding="utf-8") as handle:
            yaml.safe_dump(discovered, handle, sort_keys=True)
        print(f"Wrote dataset discovery YAML -> {args.config}")
        return

    if not args.tag:
        parser.error("--tag is required unless --discover is set")

    with open(args.config, "r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)

    out_base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "filelists", args.tag)
    os.makedirs(out_base, exist_ok=True)

    prefer_latest = args.latest_only or args.recommended_only
    filter_eras = [era.strip() for era in args.filter_era.split(",") if era.strip()]
    filelist_tasks = []
    for path, sample_cfg in _iter_dataset_entries(cfg):
        if not _should_keep_path(path, filter_eras):
            continue
        era = _extract_era_from_path(path)
        sample = path[-1] if path else ""
        datasets = _resolve_datasets(sample_cfg, args.dataset_query_filter, prefer_latest, era=era, sample=sample)
        if not datasets:
            continue
        for dataset in datasets:
            sample_tag = "__".join(path + [_sanitize_dataset_tag(dataset)])
            out_path = os.path.join(out_base, f"{sample_tag}.txt")
            filelist_tasks.append((dataset, out_path, sample_tag))

    if not filelist_tasks:
        print("No datasets selected to query.")
        return

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_task = {
            executor.submit(_run_das_query, dataset, query_filter=args.query_filter): (dataset, out_path, sample_tag)
            for dataset, out_path, sample_tag in filelist_tasks
        }
        for future in as_completed(future_to_task):
            dataset, out_path, sample_tag = future_to_task[future]
            try:
                files = future.result()
            except subprocess.CalledProcessError as exc:
                print(f"[filelists] {sample_tag}: DAS query failed ({exc})")
                continue
            if args.max_files:
                files = files[: args.max_files]
            with open(out_path, "w", encoding="utf-8") as out:
                out.write("\n".join(files) + "\n")
            print(f"Wrote {len(files)} files -> {out_path}")


if __name__ == "__main__":
    main()
