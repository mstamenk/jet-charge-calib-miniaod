#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys

try:
    import yaml
except ImportError as exc:
    print("Missing PyYAML. Install it with `python -m pip install PyYAML`.", file=sys.stderr)
    raise SystemExit(1) from exc


def _find_tree_name(root_file):
    import ROOT

    handle = ROOT.TFile.Open(root_file)
    if not handle or handle.IsZombie():
        raise RuntimeError(f"Failed to open ROOT file: {root_file}")
    for name in ("Events", "chargeNtuples/Events"):
        tree = handle.Get(name)
        if tree:
            handle.Close()
            return name
    handle.Close()
    raise RuntimeError(f"Could not find Events tree in {root_file}")


def _read_job_metadata(root_file):
    import ROOT

    handle = ROOT.TFile.Open(root_file)
    if not handle or handle.IsZombie():
        raise RuntimeError(f"Failed to open ROOT file: {root_file}")

    hist = handle.Get("job_metadata")
    if not hist:
        handle.Close()
        return None

    axis = hist.GetXaxis()
    labels = {str(axis.GetBinLabel(i)): i for i in range(1, axis.GetNbins() + 1)}
    idx_sumw = labels.get("sum_gen_weight_processed", 3)
    idx_nev = labels.get("n_events_processed", 1)
    sumw = float(hist.GetBinContent(idx_sumw))
    nev = int(round(hist.GetBinContent(idx_nev)))
    handle.Close()
    return sumw, nev


def _compute_sample_sumw(files):
    import ROOT

    if not files:
        return 0.0, 0, "none"

    sumw_from_job_metadata = 0.0
    nev_from_job_metadata = 0
    all_have_job_metadata = True
    for root_file in files:
        meta = _read_job_metadata(root_file)
        if meta is None:
            all_have_job_metadata = False
            break
        sumw_from_job_metadata += float(meta[0])
        nev_from_job_metadata += int(meta[1])

    if all_have_job_metadata:
        return sumw_from_job_metadata, nev_from_job_metadata, "job_metadata"

    tree_name = _find_tree_name(files[0])
    df = ROOT.RDataFrame(tree_name, files)
    columns = {str(name) for name in df.GetColumnNames()}
    n_events = int(df.Count().GetValue())
    if "genWeight" in columns:
        sum_weights = float(df.Sum("genWeight").GetValue())
    else:
        sum_weights = float(n_events)
    return sum_weights, n_events, "events_tree"


def _load_manifest(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "samples" in payload and isinstance(payload["samples"], dict):
        return payload["samples"]
    if isinstance(payload, dict):
        return payload
    return {}


def _load_yaml(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _dump_yaml(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=True)


def _ensure_dataset_override(xsec_cfg, dataset):
    dataset_overrides = xsec_cfg.setdefault("dataset_overrides", {})
    current = dataset_overrides.get(dataset, {})
    if isinstance(current, (int, float)):
        current = {"xsec_pb": float(current)}
    elif not isinstance(current, dict):
        current = {}
    dataset_overrides[dataset] = current
    return current


def main():
    parser = argparse.ArgumentParser(
        description="Compute per-sample sum(genWeight) from produced ntuples and optionally update xsections.yml."
    )
    parser.add_argument("--output-base", required=True, help="Base output dir used by submit_condor.py")
    parser.add_argument("--era", required=True, help="Era key (e.g. Run3_24)")
    parser.add_argument("--version", default="v1", help="Production version under output-base (default: v1)")
    parser.add_argument("--tag", required=True, help="Production tag (same as submit_condor --tag)")
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional manifest JSON path (default: filelists/<tag>/manifest.json)",
    )
    parser.add_argument(
        "--xsections",
        default="",
        help="Optional xsections YAML to update dataset_overrides.<dataset>.sum_weights in place",
    )
    parser.add_argument(
        "--out-yml",
        default="",
        help="Optional output YAML with computed sums (default: run/sum_weights_<tag>_<era>.yml)",
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(__file__))
    prod_dir = os.path.join(args.output_base, args.era, args.version, args.tag)
    if not os.path.isdir(prod_dir):
        raise RuntimeError(f"Production directory not found: {prod_dir}")

    manifest_path = args.manifest or os.path.join(base_dir, "filelists", args.tag, "manifest.json")
    manifest = _load_manifest(manifest_path)

    xsec_path = args.xsections
    xsec_cfg = _load_yaml(xsec_path) if xsec_path else {}

    results = {}
    for sample in sorted(os.listdir(prod_dir)):
        sample_dir = os.path.join(prod_dir, sample)
        if not os.path.isdir(sample_dir):
            continue
        files = sorted(glob.glob(os.path.join(sample_dir, "*.root")))
        if not files:
            continue

        meta = manifest.get(sample, {})
        sample_type = str(meta.get("sample_type", ""))
        if sample_type == "data" or sample.startswith("data__"):
            continue

        sum_weights, n_events, method = _compute_sample_sumw(files)
        dataset = str(meta.get("dataset", ""))
        results[sample] = {
            "dataset": dataset,
            "sum_weights": sum_weights,
            "n_events": n_events,
            "n_files": len(files),
            "source": method,
        }
        print(
            f"[sumw] {sample}: sum_weights={sum_weights:.10g}, n_events={n_events}, "
            f"n_files={len(files)}, source={method}"
        )

        if xsec_cfg and dataset:
            override = _ensure_dataset_override(xsec_cfg, dataset)
            override["sum_weights"] = float(sum_weights)

    if not results:
        print("No MC samples found to process.")
        return 0

    out_yml = args.out_yml or os.path.join(base_dir, "run", f"sum_weights_{args.tag}_{args.era}.yml")
    os.makedirs(os.path.dirname(out_yml), exist_ok=True)
    _dump_yaml(out_yml, {"samples": results})
    print(f"[sumw] Wrote summary YAML: {out_yml}")

    if xsec_cfg and xsec_path:
        _dump_yaml(xsec_path, xsec_cfg)
        print(f"[sumw] Updated xsections file: {xsec_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
