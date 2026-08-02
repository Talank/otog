#!/usr/bin/env python3
"""Confirm or kill leftover-state moves with small reversed-pair runs, under the discovery
budget: all tool-initiated execution (profiled run + confirmations) <= 5x suite time.

A state move claims "this test slows what runs after it". Test: run [victim, movers] and
[movers, victim] (same classes, order reversed) twice each alternating, compare the victim's
median time. Refutation requires a null on TWO distinct victims. Compiler-timing moves
(JIT_HUNGRY, COLD_FAVORED, COUPLED_PAIR, and blocks whose members mostly REWRITE loaded
classes — grouping them contains compiled-code invalidation) pass through: isolated fresh-JVM
runs cannot reproduce their in-suite effect.
"""
import argparse, json, statistics, subprocess, sys
from pathlib import Path

from ordering import block_members, read_candidates

HERE = Path(__file__).resolve().parent
STATE = ("STATE_NEW", "STATE_MUT", "PROP_WRITER", "STATE_TL")


def run(project, order, work, tag, java_home, maven_args):
    f = work / f"{tag}.order"
    f.write_text("\n".join(order) + "\n")
    cmd = [sys.executable, HERE / "run_order.py", "--project", project, "--order", f,
           "--java-home", java_home, "--log", work / f"{tag}.log"]
    r = subprocess.run(cmd + [f"--maven-arg={a}" for a in maven_args],
                       capture_output=True, text=True)
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"classes": {}}


def probe(project, movers, v, work, tag, java_home, mvn):
    """Two alternating pairs; 'slower'/'null' on the victim's median, else 'inconclusive'."""
    res = [run(project, o, work, f"{tag}-{k}", java_home, mvn)
           for k, o in (("first1", [v] + movers), ("after1", movers + [v]),
                        ("after2", movers + [v]), ("first2", [v] + movers))]
    if not all(c.get("green") for r in res for c in r["classes"].values()):
        return "inconclusive", None
    t = [r["classes"].get(v, {}).get("time") for r in res]
    if None in t:
        return "inconclusive", None
    first, after = statistics.median([t[0], t[3]]), statistics.median([t[1], t[2]])
    v = "slower" if after > first * 1.02 + 0.02 else "null" if after >= first * 0.95 else "inconclusive"
    return v, (first, after)  # a much-faster 'after' arm is warmup-dominated and proves nothing


def main():
    p = argparse.ArgumentParser()
    p.add_argument("fixture")
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--java-home",
                   default="/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home")
    p.add_argument("--maven-arg", action="append", default=[])
    args = p.parse_args()

    out = HERE / "out" / args.fixture
    (work := out / "confirm").mkdir(exist_ok=True)
    rows = [json.loads(l) for l in (out / "profile.jsonl").open() if l.strip()]
    original = [r["test"] for r in rows]
    rt = {r["test"]: r["runtimeMs"] / 1000 for r in rows}
    suite_s = sum(rt.values())
    spent, budget = suite_s, 5 * sum(rt.values())  # profiled run counts

    rewriters = {r["test"] for r in rows if r.get("retransformed")}
    plans = []  # (priority, cost, index, movers, victims)
    cands = read_candidates(out / "candidates.tsv")
    for i, (test, direction, flags) in enumerate(cands):
        if direction == "blockback" and 2 * len(set(block_members(flags)) & rewriters) \
                >= len(block_members(flags)):
            continue  # rewriter block = compiler-class move; pair runs cannot judge it
        movers = sorted(block_members(flags), key=rt.get)[:3] if direction == "blockback" \
            else [test] if direction == "back" and any(s in flags for s in STATE) else None
        if not movers:
            continue
        tail = original[min(original.index(m) for m in movers) + 1:]
        victims = sorted((t for t in tail if t not in movers), key=rt.get, reverse=True)[:2]
        if victims:
            prio = 0 if direction == "blockback" else \
                1 if ("STATE_NEW" in flags or "PROP_WRITER" in flags) else 2
            plans.append((prio, 4 * (sum(rt[m] for m in movers) + rt[victims[0]]), i, movers, victims))

    verdicts, ledger = {}, [f"profiled-run\t{suite_s:.1f}s"]
    for prio, cost, i, movers, victims in sorted(plans):
        nulls = 0
        for n, v in enumerate(victims):
            c = 4 * (sum(rt[m] for m in movers) + rt[v])
            if spent + c > budget:
                ledger.append(f"cand{i} v{n}\tSKIPPED (budget {spent:.1f}+{c:.1f} > {budget:.1f}s)")
                break
            spent += c
            kind, t = probe(args.project, movers, v, work, f"{i:02d}v{n}",
                            args.java_home, args.maven_arg)
            detail = f"{v.split('.')[-1]} {t[0]:.2f}s alone vs {t[1]:.2f}s after" if t else kind
            ledger.append(f"cand{i} v{n}\t{c:.1f}s\t{kind}: {detail}")
            if kind == "slower":
                verdicts[i] = "confirmed"
                break
            nulls += kind == "null"
        verdicts.setdefault(i, "REFUTED" if nulls >= 2 else "kept (insufficient evidence to drop)")

    kept = [c for i, c in enumerate(cands) if verdicts.get(i) != "REFUTED"]
    (out / "confirmed.tsv").write_text("".join(f"{t}\t{d}\t0\t{f}\n" for t, d, f in kept))
    ledger.append(f"TOTAL\t{spent:.1f}s of {budget:.1f}s allowed")
    (out / "spend.tsv").write_text("\n".join(ledger) + "\n")
    print("\n".join(ledger))
    print(f"[confirm] kept {len(kept)}/{len(cands)}; " +
          "; ".join(f"cand{i}={v}" for i, v in sorted(verdicts.items())))


if __name__ == "__main__":
    main()
