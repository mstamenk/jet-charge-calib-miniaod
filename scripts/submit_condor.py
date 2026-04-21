#!/usr/bin/env python3
import argparse
import glob
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
    parser.add_argument("--request-memory", default="4000")
    parser.add_argument("--request-cpus", default="1")
    parser.add_argument("--request-disk", default="2000")
    parser.add_argument("--job-flavour", default="workday")
    parser.add_argument("--one-file", action="store_true", help="Submit a single job with one input file")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(__file__))
    split_base = os.path.join(base_dir, "filelists_split", args.tag)
    if not os.path.isdir(split_base):
        raise RuntimeError(f"Missing split filelists directory: {split_base}")
    log_base = os.path.join(base_dir, "condor", "logs", args.tag)
    os.makedirs(log_base, exist_ok=True)

    template_path = os.path.join(base_dir, "condor", "templates", "job.jdl.in")
    template = read_template(template_path)

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

        for job_file in job_files:
            job_id = os.path.splitext(os.path.basename(job_file))[0]
            if args.one_file:
                with open(job_file, "r", encoding="utf-8") as handle:
                    first_line = ""
                    for line in handle:
                        first_line = line.strip()
                        if first_line:
                            break
                if not first_line:
                    raise RuntimeError(f"No files found in {job_file}")
                limited_job_file = os.path.join(sample_log_dir, f"{job_id}_onefile.txt")
                with open(limited_job_file, "w", encoding="utf-8") as handle:
                    handle.write(first_line + "\n")
                job_file = limited_job_file
                job_id = f"{job_id}_onefile"
            era_key = args.era or args.data_era
            if not era_key:
                raise RuntimeError("Provide --era (or --data-era for data) when using hlt_by_era.")
            output_dir = os.path.join(args.output_base, era_key, args.version, args.tag, sample)
            os.makedirs(output_dir, exist_ok=True)
            output_root = os.path.join(output_dir, f"ntuple_{job_id}.root")

            wrapper = os.path.join(base_dir, "scripts", "condor_wrapper.sh")
            arguments = (
                f"--cmssw-base {args.cmssw_base} --cfg {args.cfg} "
                f"--input-filelist {job_file} --output-file {output_root} "
                f"--selections {args.selections} --features {args.features} "
                f"--weights {args.weights} --systematics {args.systematics}"
            )
            if args.golden_json:
                arguments += f" --golden-json {args.golden_json}"
            if args.golden_jsons:
                arguments += f" --golden-jsons-yml {args.golden_jsons}"
            if args.data_era:
                arguments += f" --data-era {args.data_era}"
            if era_key:
                arguments += f" --era {era_key}"
            env_brux = os.path.join(base_dir, "scripts", "env_brux.sh")
            transfer_files = [args.cfg, job_file, args.selections, args.features, args.weights, args.systematics]
            if os.path.exists(env_brux):
                transfer_files.append(env_brux)
            if args.golden_json:
                transfer_files.append(args.golden_json)
            if args.golden_jsons:
                transfer_files.append(args.golden_jsons)
            mapping = {
                "wrapper": wrapper,
                "arguments": arguments,
                "log_out": os.path.join(sample_log_dir, f"{job_id}.out"),
                "log_err": os.path.join(sample_log_dir, f"{job_id}.err"),
                "log_log": os.path.join(sample_log_dir, f"{job_id}.log"),
                "request_memory": args.request_memory,
                "request_cpus": args.request_cpus,
                "request_disk": args.request_disk,
                "job_flavour": args.job_flavour,
                "transfer_input_files": ",".join(transfer_files),
                "transfer_output_files": "",
            }

            jdl_path = os.path.join(sample_log_dir, f"{job_id}.jdl")
            with open(jdl_path, "w", encoding="utf-8") as handle:
                handle.write(render_template(template, mapping))

            if args.submit:
                subprocess.run(["condor_submit", jdl_path], check=True)
            else:
                print(f"Prepared {jdl_path} -> output {output_root}")


if __name__ == "__main__":
    main()
