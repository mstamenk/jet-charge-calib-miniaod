#!/usr/bin/env python3
import argparse
import datetime as dt
import glob
import os
import re
import statistics


RE_BEGIN = re.compile(r"Begin processing the (\d+)(?:st|nd|rd|th) record\..* at (\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2})\.")
RE_OPEN_REQ = re.compile(r"^(\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2}) [A-Z]{3}\s+Initiating request to open file")
RE_FIRST_EVENT = re.compile(r"Begin processing the 1st record\..* at (\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2}:\d{2})\.")


def parse_time(value):
    return dt.datetime.strptime(value, "%d-%b-%Y %H:%M:%S")


def summarize(values):
    if not values:
        return None
    values = sorted(values)
    n = len(values)
    return {
        "n": n,
        "mean": sum(values) / n,
        "p50": statistics.median(values),
        "p90": values[int(0.9 * (n - 1))],
        "p99": values[int(0.99 * (n - 1))],
        "max": values[-1],
    }


def format_summary(name, stats, unit):
    if not stats:
        return f"{name}: n=0"
    return (
        f"{name}: n={stats['n']}, mean={stats['mean']:.2f}{unit}, "
        f"p50={stats['p50']:.2f}{unit}, p90={stats['p90']:.2f}{unit}, "
        f"p99={stats['p99']:.2f}{unit}, max={stats['max']:.2f}{unit}"
    )


def main():
    parser = argparse.ArgumentParser(description="Profile CMSSW runtime behavior from condor .err logs.")
    parser.add_argument("--log-dir", required=True, help="Directory containing condor sample subdirectories.")
    args = parser.parse_args()

    err_files = sorted(glob.glob(os.path.join(args.log_dir, "**", "*.err"), recursive=True))
    if not err_files:
        raise SystemExit(f"No .err files found under {args.log_dir}")

    rates_ev_per_s = []
    max_marker_events = []
    first_event_delay_s = []
    step_1000_gaps_s = []
    xrd_reopens_per_job = []

    for path in err_files:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()

        points = []
        for line in lines:
            m = RE_BEGIN.search(line)
            if m:
                points.append((int(m.group(1)), parse_time(m.group(2))))

        if points:
            max_marker_events.append(max(ev for ev, _ in points))
            if len(points) >= 2:
                ev0, t0 = points[0]
                ev1, t1 = points[-1]
                dt_s = (t1 - t0).total_seconds()
                if dt_s > 0 and ev1 > ev0:
                    rates_ev_per_s.append((ev1 - ev0) / dt_s)
            for (ev0, t0), (ev1, t1) in zip(points, points[1:]):
                if ev1 - ev0 == 1000:
                    dt_s = (t1 - t0).total_seconds()
                    if dt_s > 0:
                        step_1000_gaps_s.append(dt_s)

        open_req = None
        first_evt = None
        for line in lines:
            if open_req is None:
                m = RE_OPEN_REQ.search(line)
                if m:
                    open_req = parse_time(m.group(1))
            if first_evt is None:
                m = RE_FIRST_EVENT.search(line)
                if m:
                    first_evt = parse_time(m.group(1))
            if open_req is not None and first_evt is not None:
                first_event_delay_s.append((first_evt - open_req).total_seconds())
                break

        xrd_reopens_per_job.append(sum(1 for line in lines if "Opened a file at URL" in line))

    print(f"Profiled {len(err_files)} jobs from {args.log_dir}")
    print(format_summary("Event rate", summarize(rates_ev_per_s), " ev/s"))
    print(format_summary("Marker max event", summarize(max_marker_events), " events"))
    print(format_summary("Startup delay to 1st event", summarize(first_event_delay_s), " s"))
    print(format_summary("1000-event step time", summarize(step_1000_gaps_s), " s"))
    print(format_summary("XRootD reopen messages per job", summarize(xrd_reopens_per_job), ""))

    if step_1000_gaps_s:
        n_slow = sum(1 for v in step_1000_gaps_s if v > 120.0)
        frac_slow = 100.0 * n_slow / len(step_1000_gaps_s)
        print(f"1000-event steps slower than 120s: {n_slow}/{len(step_1000_gaps_s)} ({frac_slow:.2f}%)")


if __name__ == "__main__":
    main()
