#!/usr/bin/env python3
"""Harness glue: score detector output against the 10 documented mechanisms (C1) + C2 caps.

Applied order = [front-movers as listed] + [unflagged, original order] + [back-movers as listed].
"""
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"


def load(fixture):
    prof = OUT / fixture / "profile.jsonl"
    cand = OUT / fixture / "candidates.tsv"
    if not prof.exists() or not cand.exists():
        return None
    original = [json.loads(l)["test"] for l in prof.open() if l.strip()]
    front, back, dirs = [], [], {}
    swaps, block = [], []
    for line in cand.open():
        if not line.strip():
            continue
        test, d = line.split("\t")[0], line.split("\t")[1]
        if d == "blockback":
            m = re.search(r"members=([^\]]+)\]", line)
            block = m.group(1).split(",") if m else []
            continue
        if d.startswith("swap:"):
            swaps.append((test, d.split(":", 1)[1]))
            continue
        dirs[test] = d
        (front if d == "front" else back).append(test)
    blockset = set(block) - set(dirs)
    middle = [t for t in original if t not in dirs and t not in blockset]
    for a, b in swaps:  # swaps reorder the middle block only
        if a in middle and b in middle:
            i, j = middle.index(a), middle.index(b)
            middle[i], middle[j] = middle[j], middle[i]
    applied = front + middle + back + [t for t in original if t in blockset]
    return {"original": original, "applied": applied, "dirs": dirs,
            "n": len(original), "ncand": len(dirs) + len(swaps) + (1 if block else 0)}


def pos(f, test):
    matches = [i for i, t in enumerate(f["applied"]) if t.endswith(test)]
    return matches[0] if matches else None


def flagged(f, test, d):
    return any(t.endswith(test) and dd == d for t, dd in f["dirs"].items())


CHECKS = [
    # (row, fixture, description, predicate)
    (1, "openpojo", "Identity back, after Structural",
     lambda f: flagged(f, "IdentityFactoryRaceConditionTest", "back")
     and pos(f, "StructuralTest") < pos(f, "IdentityFactoryRaceConditionTest")),
    (2, "jp-core", "Issue4488 back, after JavadocExtractor",
     lambda f: flagged(f, "Issue4488Test", "back")
     and pos(f, "JavadocExtractorTest") < pos(f, "Issue4488Test")),
    (3, "snakeyaml", "PyEmitter and BigDataLoad back",
     lambda f: flagged(f, "PyEmitterTest", "back") and flagged(f, "BigDataLoadTest", "back")),
    (4, "jp-solver", "JavaParserTypeSolver back",
     lambda f: flagged(f, "JavaParserTypeSolverTest", "back")),
    (5, "commonstext", "AppendInsert back, after FilterReader",
     lambda f: flagged(f, "TextStringBuilderAppendInsertTest", "back")
     and pos(f, "StringSubstitutorFilterReaderTest") < pos(f, "TextStringBuilderAppendInsertTest")),
    (6, "ahc-leak", "ResetByPeer back, after MultipartBody",
     lambda f: flagged(f, "NettyConnectionResetByPeerTest", "back")
     and pos(f, "MultipartBodyTest") < pos(f, "NettyConnectionResetByPeerTest")),
    (7, "ahc-pool", "AsyncHttpClientDefaults back",
     lambda f: flagged(f, "AsyncHttpClientDefaultsTest", "back")),
    (8, "gson", "LinkedTreeMap suite before JsonObject suite",
     lambda f: pos(f, "LinkedTreeMapSuiteTest") < pos(f, "JsonObjectAsMapSuiteTest")
     and f["ncand"] > 0),
    (9, "snakeyaml", "References before Stress, via flags",
     lambda f: pos(f, "issue377.ReferencesTest") < pos(f, "StressEmitterTest")
     and (flagged(f, "issue377.ReferencesTest", "front") or flagged(f, "StressEmitterTest", "back"))),
    (10, "snakeyaml", "CompactConstructorErrors front",
     lambda f: flagged(f, "CompactConstructorErrorsTest", "front")),
]


def main():
    fixtures = {}
    ok = 0
    for row, fixture, desc, pred in CHECKS:
        f = fixtures.setdefault(fixture, load(fixture))
        if f is None:
            print(f"row {row:2d} [{fixture}] MISSING OUTPUT - {desc}")
            continue
        good = False
        try:
            good = bool(pred(f))
        except TypeError:
            pass  # a pos() returned None
        ok += good
        print(f"row {row:2d} [{fixture}] {'PASS' if good else 'FAIL'} - {desc}")
    print(f"\nC1: {ok}/10")
    for name, f in fixtures.items():
        if f is None:
            continue
        cap = max(10, int(0.15 * f["n"]))
        status = "ok" if f["ncand"] <= cap else "OVER CAP"
        print(f"C2 [{name}] candidates={f['ncand']}/{f['n']} cap={cap} {status}")
    sys.exit(0 if ok == 10 else 1)


if __name__ == "__main__":
    main()
