#!/usr/bin/env python3
import argparse
import glob
import json
import os
import subprocess


def read_template(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def render_template(template, mapping):
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def load_fileset_manifest(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict) and "samples" in payload and isinstance(payload["samples"], dict):
        return payload["samples"]
    if isinstance(payload, dict):
        return payload
    return {}


def infer_sample_type_from_filelist(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                upper = line.upper()
                if "MINIAODSIM" in upper or "NANOAODSIM" in upper or "AODSIM" in upper:
                    return "mc"
                if "/MINIAOD" in upper or "/NANOAOD" in upper or "/AOD" in upper:
                    return "data"
                break
    except OSError:
        pass
    return "auto"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sample", default="", help="Limit to a sample name (matches filelists_split/<tag>/<sample>)")
    parser.add_argument("--cmssw-base", required=True)
    parser.add_argument("--cfg", required=True)
    parser.add_argument("--output-base", required=True)
    parser.add_argument("--era", default="", help="Era key used for hlt_by_era/weights (e.g. Run3_24)")
    parser.add_argument("--version", default="v1", help="Output version tag (default: v1)")
    parser.add_argument("--selections", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--systematics", required=True)
    parser.add_argument("--golden-json", default="", help="Golden JSON file (data only)")
    parser.add_argument("--golden-jsons", default="", help="Golden JSONs YAML mapping")
    parser.add_argument("--data-era", default="", help="Era key for golden JSON lookup")
    parser.add_argument(
        "--fileset-manifest",
        default="",
        help="Optional filelist metadata JSON (default: filelists/<tag>/manifest.json when present)",
    )
    parser.add_argument(
        "--target-lumi-pb",
        type=float,
        default=0.0,
        help="Override target luminosity in /pb for MC normalization metadata",
    )
    parser.add_argument(
        "--sample-type-override",
        default="",
        choices=["", "auto", "mc", "data"],
        help="Override sample type metadata (auto|mc|data)",
    )
    parser.add_argument(
        "--sample-name-override",
        default="",
        help="Override sample name metadata",
    )
    parser.add_argument(
        "--dataset-name-override",
        default="",
        help="Override dataset name metadata",
    )
    parser.add_argument(
        "--sample-xsec-pb-override",
        type=float,
        default=None,
        help="Override MC cross section metadata in pb",
    )
    parser.add_argument(
        "--sample-sum-weights-override",
        type=float,
        default=None,
        help="Override MC sum(weights) metadata",
    )
    parser.add_argument(
        "--require-metadata",
        action="store_true",
        help="Fail if required metadata is missing instead of using defaults",
    )
    parser.add_argument(
        "--allow-missing-mc-normalization",
        action="store_true",
        help=(
            "Legacy compatibility flag (no-op): MC submissions no longer require "
            "normalization metadata unless --require-metadata is set."
        ),
    )
    parser.add_argument(
        "--enable-event-prefilter",
        type=int,
        choices=[0, 1],
        default=1,
        help="Enable fast EventPreselectionFilter in cmsRun jobs (default: 1).",
    )
    parser.add_argument(
        "--prefilter-apply-jet-selection",
        type=int,
        choices=[0, 1],
        default=0,
        help="Apply jet selection in EventPreselectionFilter (default: 0 for safe superset).",
    )
    parser.add_argument(
        "--sequential-files-in-job",
        type=int,
        choices=[0, 1],
        default=0,
        help=(
            "When set to 1, each condor job processes its input file list sequentially "
            "(one file per cmsRun invocation) and merges outputs at the end."
        ),
    )
    parser.add_argument("--max-events", type=int, default=-1, help="cmsRun maxEvents for each job (-1 = all)")
    parser.add_argument("--request-memory", default="4000")
    parser.add_argument("--request-cpus", default="1")
    parser.add_argument("--request-disk", default="2000")
    parser.add_argument(
        "--job-flavour",
        default="",
        help="Optional JobFlavour classad (e.g. espresso, microcentury, longlunch, workday). Leave empty to omit.",
    )
    parser.add_argument("--one-file", action="store_true", help="Submit a single job with one input file")
    parser.add_argument(
        "--files-per-job",
        type=int,
        default=0,
        help=(
            "Optional rechunking at submit time. "
            "Set to N>0 to split each discovered job_*.txt into sub-jobs with at most N files each. "
            "Use 1 to run one input file per cmsRun job."
        ),
    )
    parser.add_argument(
        "--single-cluster",
        action="store_true",
        help="Submit all generated jobs in one condor_submit call (single cluster with many proc IDs)",
    )
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    if args.files_per_job < 0:
        raise RuntimeError("--files-per-job must be >= 0")

    base_dir = os.path.dirname(os.path.dirname(__file__))
    split_base = os.path.join(base_dir, "filelists_split", args.tag)
    if not os.path.isdir(split_base):
        raise RuntimeError(f"Missing split filelists directory: {split_base}")
    manifest_path = args.fileset_manifest or os.path.join(base_dir, "filelists", args.tag, "manifest.json")
    fileset_manifest = load_fileset_manifest(manifest_path)
    if fileset_manifest:
        print(f"Loaded fileset manifest: {manifest_path}")
    log_base = os.path.join(base_dir, "condor", "logs", args.tag)
    os.makedirs(log_base, exist_ok=True)

    template_path = os.path.join(base_dir, "condor", "templates", "job.jdl.in")
    template = read_template(template_path)
    prepared_jdls = []

    samples = [args.sample] if args.sample else sorted(os.listdir(split_base))
    if args.one_file and not samples:
        raise RuntimeError("No samples found to run --one-file.")
    if args.one_file and not args.sample:
        samples = samples[:1]

    for sample in samples:
        sample_dir = os.path.join(split_base, sample)
        if not os.path.isdir(sample_dir):
            continue
        job_files = sorted(glob.glob(os.path.join(sample_dir, "job_*.txt")))
        if not job_files:
            continue

        sample_log_dir = os.path.join(log_base, sample)
        os.makedirs(sample_log_dir, exist_ok=True)

        if args.one_file:
            if not job_files:
                continue
            job_files = job_files[:1]

        sample_meta = fileset_manifest.get(sample, {})
        sample_type = str(sample_meta.get("sample_type", "auto"))
        sample_name = str(sample_meta.get("sample_name", sample))
        dataset_name = str(sample_meta.get("dataset", ""))
        sample_xsec_pb = float(sample_meta.get("xsec_pb", -1.0) or -1.0)
        sample_sum_weights = float(sample_meta.get("sum_weights", 0.0) or 0.0)
        target_lumi_pb = (
            float(args.target_lumi_pb)
            if args.target_lumi_pb > 0.0
            else float(sample_meta.get("target_lumi_pb", 0.0) or 0.0)
        )

        for job_file in job_files:
            job_id = os.path.splitext(os.path.basename(job_file))[0]
            with open(job_file, "r", encoding="utf-8") as handle:
                input_lines = [line.strip() for line in handle if line.strip()]
            if not input_lines:
                raise RuntimeError(f"No files found in {job_file}")

            per_job = args.files_per_job
            if args.one_file:
                per_job = 1

            job_chunks = []
            if per_job and per_job > 0:
                for idx in range(0, len(input_lines), per_job):
                    chunk = input_lines[idx : idx + per_job]
                    chunk_idx = idx // per_job + 1
                    chunk_file = os.path.join(sample_log_dir, f"{job_id}_chunk{chunk_idx:04d}.txt")
                    with open(chunk_file, "w", encoding="utf-8") as handle:
                        handle.write("\n".join(chunk) + "\n")
                    chunk_id = f"{job_id}_chunk{chunk_idx:04d}"
                    job_chunks.append((chunk_file, chunk_id))
            else:
                job_chunks.append((job_file, job_id))

            for chunk_file, chunk_id in job_chunks:
                inferred_type = infer_sample_type_from_filelist(chunk_file)
                effective_sample_type = sample_type
                if effective_sample_type == "auto" and inferred_type in ("mc", "data"):
                    effective_sample_type = inferred_type

                effective_sample_name = sample_name
                effective_dataset_name = dataset_name
                effective_sample_xsec_pb = sample_xsec_pb
                effective_sample_sum_weights = sample_sum_weights
                if args.sample_type_override:
                    effective_sample_type = args.sample_type_override
                if args.sample_name_override:
                    effective_sample_name = args.sample_name_override
                if args.dataset_name_override:
                    effective_dataset_name = args.dataset_name_override
                if args.sample_xsec_pb_override is not None:
                    effective_sample_xsec_pb = float(args.sample_xsec_pb_override)
                if args.sample_sum_weights_override is not None:
                    effective_sample_sum_weights = float(args.sample_sum_weights_override)

                # Metadata validation is opt-in via --require-metadata.
                # This allows deferred MC normalization workflows where sample_sum_weights
                # are computed after production from job_metadata/genWeight sums.
                require_metadata = args.require_metadata

                if require_metadata:
                    missing = []
                    if effective_sample_type not in ("mc", "data"):
                        missing.append("sample_type")
                    if not effective_sample_name:
                        missing.append("sample_name")
                    if not effective_dataset_name:
                        missing.append("dataset_name")
                    if effective_sample_type == "mc" and effective_sample_xsec_pb <= 0.0:
                        missing.append("sample_xsec_pb")
                    if effective_sample_type == "mc" and effective_sample_sum_weights <= 0.0:
                        missing.append("sample_sum_weights")
                    if effective_sample_type == "mc" and target_lumi_pb <= 0.0:
                        missing.append("target_lumi_pb")
                    if missing:
                        raise RuntimeError(
                            f"Missing required metadata for sample '{sample}' job '{chunk_id}': " + ", ".join(missing)
                        )

                era_key = args.era or args.data_era
                if not era_key:
                    raise RuntimeError("Provide --era (or --data-era for data) when using hlt_by_era.")
                output_dir = os.path.join(args.output_base, era_key, args.version, args.tag, sample)
                os.makedirs(output_dir, exist_ok=True)
                output_root = os.path.join(output_dir, f"ntuple_{chunk_id}.root")

                wrapper = os.path.join(base_dir, "scripts", "condor_wrapper.sh")
                arguments = (
                    f"--cmssw-base {args.cmssw_base} --cfg {args.cfg} "
                    f"--input-filelist {chunk_file} --output-file {output_root} "
                    f"--selections {args.selections} --features {args.features} "
                    f"--weights {args.weights} --systematics {args.systematics} "
                    f"--max-events {args.max_events} "
                    f"--enable-event-prefilter {args.enable_event_prefilter} "
                    f"--prefilter-apply-jet-selection {args.prefilter_apply_jet_selection} "
                    f"--sequential-files-in-job {args.sequential_files_in_job}"
                )
                arguments += (
                    f" --sample-type {effective_sample_type}"
                    f" --sample-xsec-pb {effective_sample_xsec_pb}"
                    f" --sample-sum-weights {effective_sample_sum_weights}"
                    f" --target-lumi-pb {target_lumi_pb}"
                )
                if effective_sample_name:
                    arguments += f" --sample-name {effective_sample_name}"
                if effective_dataset_name:
                    arguments += f" --dataset-name {effective_dataset_name}"
                if args.golden_json:
                    arguments += f" --golden-json {args.golden_json}"
                if args.golden_jsons:
                    arguments += f" --golden-jsons-yml {args.golden_jsons}"
                if args.data_era:
                    arguments += f" --data-era {args.data_era}"
                if era_key:
                    arguments += f" --era {era_key}"
                env_brux = os.path.join(base_dir, "scripts", "env_brux.sh")
                transfer_files = [
                    args.cfg,
                    chunk_file,
                    args.selections,
                    args.features,
                    args.weights,
                    args.systematics,
                ]
                if os.path.exists(env_brux):
                    transfer_files.append(env_brux)
                if args.golden_json:
                    transfer_files.append(args.golden_json)
                if args.golden_jsons:
                    transfer_files.append(args.golden_jsons)
                mapping = {
                    "wrapper": wrapper,
                    "arguments": arguments,
                    "log_out": os.path.join(sample_log_dir, f"{chunk_id}.out"),
                    "log_err": os.path.join(sample_log_dir, f"{chunk_id}.err"),
                    "log_log": os.path.join(sample_log_dir, f"{chunk_id}.log"),
                    "request_memory": args.request_memory,
                    "request_cpus": args.request_cpus,
                    "request_disk": args.request_disk,
                    "job_flavour_line": f'+JobFlavour = "{args.job_flavour}"' if args.job_flavour else "",
                    "transfer_input_files": ",".join(transfer_files),
                    "transfer_output_files": "",
                }

                jdl_path = os.path.join(sample_log_dir, f"{chunk_id}.jdl")
                rendered_jdl = render_template(template, mapping)
                with open(jdl_path, "w", encoding="utf-8") as handle:
                    handle.write(rendered_jdl)
                prepared_jdls.append((jdl_path, output_root))

                if not args.submit:
                    print(f"Prepared {jdl_path} -> output {output_root}")

    if args.submit:
        if args.single_cluster:
            if not prepared_jdls:
                print("No jobs prepared; nothing to submit.")
                return
            batch_jdl_path = os.path.join(log_base, "submit_all_single_cluster.jdl")
            with open(batch_jdl_path, "w", encoding="utf-8") as handle:
                for idx, (jdl_path, _) in enumerate(prepared_jdls):
                    with open(jdl_path, "r", encoding="utf-8") as job_handle:
                        handle.write(job_handle.read())
                    if idx + 1 < len(prepared_jdls):
                        handle.write("\n\n")
            subprocess.run(["condor_submit", "-single-cluster", batch_jdl_path], check=True)
            print(f"Submitted {len(prepared_jdls)} jobs in one cluster via {batch_jdl_path}")
        else:
            for jdl_path, _ in prepared_jdls:
                subprocess.run(["condor_submit", jdl_path], check=True)


if __name__ == "__main__":
    main()
