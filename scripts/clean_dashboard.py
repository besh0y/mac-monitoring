#!/usr/bin/env python3
"""Clean a Grafana dashboard API response into a provisioning-ready JSON file.

Reads the body of `GET /api/dashboards/uid/<uid>` on stdin, extracts the
dashboard model, strips fields that are local to a Grafana instance, and writes
the result to <out_file>.

Usage:  clean_dashboard.py <out_file> <uid>   (response JSON on stdin)
"""
import json
import sys

def main():
    out_file, uid = sys.argv[1], sys.argv[2]
    d = json.loads(sys.stdin.read()).get("dashboard")
    if not d:
        sys.stderr.write(f"    no dashboard returned for uid={uid}\n")
        sys.exit(1)
    for k in ("id", "version", "iteration"):
        d.pop(k, None)
    d["uid"] = uid
    with open(out_file, "w") as fh:
        json.dump(d, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"    {uid:14s} -> {out_file.split('/')[-1]}")

if __name__ == "__main__":
    main()
