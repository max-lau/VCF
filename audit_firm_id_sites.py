#!/usr/bin/env python3
"""
Run this on the VPS from the repo root BEFORE touching any call site:

    python3 audit_firm_id_sites.py > firm_id_audit_$(date +%Y%m%d).txt

Does two things the 109-count alone doesn't tell you:
  1. Lists every READ site (the getattr fallback pattern) with file:line,
     grouped by file, so you can walk them risk-first.
  2. Lists every WRITE site (anything setting request.state.firm_id), so you
     can confirm no middleware is quietly setting it to "default" on the
     API-key path -- if one is, the dependency swap alone won't fix behavior
     until that write site is also removed.

No dependencies beyond the stdlib. Read-only -- makes no changes.
"""
import re
import sys
from pathlib import Path

READ_PATTERN = re.compile(
    r'getattr\s*\(\s*request\.state\s*,\s*["\']firm_id["\']\s*,\s*["\']default["\']\s*\)'
)
WRITE_PATTERN = re.compile(r'request\.state\.firm_id\s*=')

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend")

read_hits = {}
write_hits = {}

for path in ROOT.rglob("*.py"):
    text = path.read_text(errors="ignore").splitlines()
    for i, line in enumerate(text, start=1):
        if READ_PATTERN.search(line):
            read_hits.setdefault(str(path), []).append((i, line.strip()))
        if WRITE_PATTERN.search(line):
            write_hits.setdefault(str(path), []).append((i, line.strip()))

print("=" * 80)
print(f"READ sites (getattr fallback pattern) -- {sum(len(v) for v in read_hits.values())} total across {len(read_hits)} files")
print("=" * 80)
for fname in sorted(read_hits, key=lambda f: -len(read_hits[f])):
    print(f"\n{fname}  ({len(read_hits[fname])} sites)")
    for lineno, line in read_hits[fname]:
        print(f"  L{lineno}: {line}")

print("\n" + "=" * 80)
print(f"WRITE sites (request.state.firm_id = ...) -- {sum(len(v) for v in write_hits.values())} total")
print("=" * 80)
print("Check each of these for a silent '\"default\"' write on the API-key path.")
for fname, hits in write_hits.items():
    print(f"\n{fname}")
    for lineno, line in hits:
        print(f"  L{lineno}: {line}")

print("\n" + "=" * 80)
print("Suggested risk-first migration order (adjust to your actual counts above):")
print("  1. privilege_log.py")
print("  2. redaction.py")
print("  3. matter_exports.py")
print("  4. pdf_export.py")
print("  5. everything else, lowest-stakes last")
print("=" * 80)
