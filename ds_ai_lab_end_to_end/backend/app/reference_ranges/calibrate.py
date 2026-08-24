"""Calibration harness for the test-name resolver.

Run:  python -m code.reference_ranges.calibrate
      python -m code.reference_ranges.calibrate --vector   (also scores tier 4)

Produces the two numbers that set the resolver's operating point:

  in-vocabulary recall   - can it still find a test whose name the OCR mangled?
  out-of-vocabulary FPR  - does it invent a match for a test the table lacks?

These pull in opposite directions, which is the whole reason the threshold is
measured rather than guessed. Results are printed, not asserted; this is an
evaluation tool, not a test.
"""

from __future__ import annotations

import argparse
import random
import time

from .range_lookup import RangeLookup, _signature
from .build_reference_db import normalize_name

# Real analytes and report furniture that are NOT in this workbook. A resolver
# that matches any of these is fabricating a reference range.
OOV_PROBES = [
    "Procalcitonin", "Interleukin-6", "Lipase", "Homocysteine", "Fibrinogen",
    "Anti-CCP Antibody", "Beta-2 Microglobulin", "Ceruloplasmin", "Haptoglobin",
    "Osteocalcin", "Erythropoietin", "Cystatin C", "Serum Amyloid A",
    # report furniture the OCR will happily hand us as if it were a test
    "Patient Name", "Referring Physician", "Sample Collected On",
    "Report Generated", "Collection Date", "Barcode Number", "Zzqq Wxyz",
]


def _corrupt(s: str, mode: str, rng: random.Random) -> str:
    if mode == "case":
        return s.upper()
    if mode == "typo" and len(s) > 4:
        i = rng.randrange(1, len(s) - 1)
        return s[:i] + s[i + 1:]
    if mode == "swap" and len(s) > 5:
        i = rng.randrange(1, len(s) - 2)
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if mode == "noise":
        return f"Serum {s} Level"
    return s


MODES = ("clean", "case", "typo", "swap", "noise")


def in_vocab(lk: RangeLookup, sample, rng: random.Random) -> None:
    print(f"{'corruption':10s} {'correct':>9s} {'WRONG':>8s} {'refused':>9s} {'sec':>7s}")
    print("-" * 48)
    for mode in MODES:
        ok = wrong = miss = 0
        t0 = time.time()
        for e in sample:
            cand, _, _ = lk.resolve(_corrupt(e["test_name"], mode, rng), e["unit_raw"])
            if cand is None:
                miss += 1
            elif _signature(cand.entry) == _signature(e):
                ok += 1
            else:
                wrong += 1
        n = len(sample)
        print(f"{mode:10s} {ok/n:8.1%} {wrong/n:7.1%} {miss/n:8.1%} {time.time()-t0:6.1f}")


def out_of_vocab(lk: RangeLookup, known: set[str]) -> None:
    probes = [p for p in OOV_PROBES if normalize_name(p) not in known]
    bad = []
    for p in probes:
        cand, _, _ = lk.resolve(p, None)
        if cand is not None:
            bad.append((p, cand.entry["test_name"], round(cand.score)))
    n = len(probes)
    print(f"refused (good): {(n-len(bad))/n:.1%}   fabricated (bad): {len(bad)/n:.1%}")
    for p, m, s in bad:
        print(f"   {p!r} -> {m!r} ({s})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", action="store_true", help="enable the Chroma tier")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args()

    rng = random.Random(7)
    kw = {"vector_enabled": args.vector}
    if args.threshold is not None:
        kw["fuzzy_threshold"] = args.threshold
    lk = RangeLookup(**kw)

    entries = [e for e in lk.entries if e["evaluable"]]
    sample = rng.sample(entries, min(args.sample, len(entries)))
    known = {e["normalized"] for e in lk.entries}

    print(f"resolver: fuzzy_threshold={lk.fuzzy_threshold} vector={lk.vector_enabled}")
    print(f"in-vocabulary (n={len(sample)}):\n")
    in_vocab(lk, sample, rng)
    print("\nout-of-vocabulary:")
    out_of_vocab(lk, known)


if __name__ == "__main__":
    main()
