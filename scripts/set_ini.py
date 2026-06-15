#!/usr/bin/env python3
"""Idempotently set keys in an INI file (e.g. grafana.ini).

Usage: set_ini.py <file> key=value [key=value ...]

Replaces the first line matching `^\\s*;?\\s*<key>\\s*=` (handles both the
default commented form `;key = x` and an already-set `key = x`), so re-running
is safe. Comments and layout elsewhere are preserved.
"""
import re
import sys

def main():
    path = sys.argv[1]
    pairs = [a.split("=", 1) for a in sys.argv[2:]]
    lines = open(path).read().split("\n")
    for key, val in pairs:
        pat = re.compile(r"^\s*;?\s*" + re.escape(key) + r"\s*=")
        for i, line in enumerate(lines):
            if pat.match(line):
                lines[i] = f"{key} = {val}"
                break
        else:
            print(f"WARN: key '{key}' not found in {path}", file=sys.stderr)
    open(path, "w").write("\n".join(lines))
    print("  set:", ", ".join(k for k, _ in pairs))

if __name__ == "__main__":
    main()
