#!/usr/bin/env python3
import argparse
import os

from studies.ttbar_dilepton_reco.io import default_branch_map, inspect_root_file, write_branch_map, write_inspection_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--branch-map", default="studies/ttbar_dilepton_reco/branch_map.yaml")
    ap.add_argument("--json", default="studies/ttbar_dilepton_reco/output/inspect_snapshot.json")
    args = ap.parse_args()

    out = inspect_root_file(args.input)
    print(f"file path: {out['file']}")
    for t in out["trees"]:
        print(f"tree: {t['name']} entries: {t['entries']}")
        print("matched branches:")
        for b in t["matched"]:
            print(f"  {b}")

    write_inspection_json(args.json, out)
    if out["trees"]:
        bmap = default_branch_map(out["trees"][0]["branches"])
        write_branch_map(args.branch_map, bmap)
        print(f"wrote branch map: {os.path.abspath(args.branch_map)}")


if __name__ == "__main__":
    main()
