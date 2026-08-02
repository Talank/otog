#!/usr/bin/env python3
"""Materialize the detector's applied order for a fixture as an order file."""
import json
import sys
from pathlib import Path

from ordering import apply_all, read_candidates

fixture, dest = sys.argv[1], Path(sys.argv[2])
out = Path(__file__).resolve().parent / "out" / fixture
original = [json.loads(l)["test"] for l in (out / "profile.jsonl").open() if l.strip()]
src = out / ("confirmed.tsv" if (out / "confirmed.tsv").exists() else "candidates.tsv")
cands = read_candidates(src)
applied = apply_all(original, cands)
dest.write_text("\n".join(applied) + "\n")
# baseline arm for A/B: the profile's own recorded order (same class set by construction)
dest.with_suffix(".baseline").write_text("\n".join(original) + "\n")
print(f"{dest}: {len(applied)} classes, {len(cands)} candidates")
