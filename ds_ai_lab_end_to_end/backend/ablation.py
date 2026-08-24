"""Ablation: does grounding the status actually reduce wrong verdicts?

Run:
    cd backend && python3 ablation.py                 # deterministic arms, CPU
    cd backend && python3 ablation.py --markdown      # table for the report
    cd backend && python3 ablation.py --llm --sample 8  # adds the model arm (GPU)

WHY THIS EXISTS
---------------
The project's central claim is that computing HIGH/LOW/NORMAL deterministically,
instead of letting the fine-tuned LLM infer it, removes a class of wrong
answers. That is an empirical claim, so it needs a measured before/after rather
than one hand-picked panel.

THE ARMS
--------
baseline   The matcher this project shipped with, reproduced verbatim from
           commit 4d01d82: a 20-row table matched with
               if key in test_upper or test_upper in key
           Its table is in baseline_table.json, extracted from that commit so
           the comparison is against what actually ran, not a caricature.

grounded   The current app.reference_ranges lookup.

llm        (optional, --llm) The fine-tuned model given the SAME results with
           the status field removed, and asked to supply it. This measures the
           behaviour the grounded layer replaced.

GROUND TRUTH, AND ITS LIMIT
--------------------------
Cases are generated FROM the reference table, so the correct answer is known by
construction: pick an evaluable row, then choose a value inside, below or above
its bounds.

The two arms use DIFFERENT tables (the baseline's Hemoglobin is 13.0-17.0, ours
is 13.2-16.6), so a value near a bound could be scored "wrong" for the baseline
when it is only following a different published range. That would flatter the
grounded arm for no good reason. Values are therefore generated with a wide
margin - the midpoint for NORMAL, half the lower bound for LOW, double the upper
bound for HIGH - so any reasonable adult range agrees on the verdict. What is
left to measure is whether an arm picks the RIGHT TEST and reads its units, not
whose reference range is preferable.

Be explicit about the residual limit when citing this: the grounded arm's
bounds come from the same table the truth is drawn from, so its score is a
measure of resolution and unit handling, not of whether those published ranges
are clinically ideal.

METRICS
-------
accuracy        fraction of cases given the correct status
false abnormal  truly NORMAL, reported HIGH or LOW   <- the harmful direction
false normal    truly HIGH/LOW, reported NORMAL      <- the other harmful one
answered        fraction it was willing to judge at all
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("MEDREPORT_STUB_MODELS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.reference_ranges.range_lookup import RangeLookup, NOT_EVALUATED  # noqa: E402

HERE = Path(__file__).resolve().parent
BASELINE_TABLE = HERE / "baseline_table.json"

# Unit spellings that appear on real reports. Cases are generated with these so
# the arms are scored on realistic input rather than the table's own notation.
UNIT_VARIANTS = {
    "g/dL": ["g/dL", "gm/dL"],
    "x10^3/µL": ["x10^3/uL", "10^9/L", "/cumm"],
    "x10^6/µL": ["x10^6/uL", "mill/cumm"],
    "mmol/L": ["mmol/L", "mEq/L"],
    "%": ["%"],
}


def unit_variants(unit: str | None) -> list[str]:
    if not unit:
        return [None]
    return UNIT_VARIANTS.get(unit, [unit])


# ---------------------------------------------------------------------------
# Benchmark generation
# ---------------------------------------------------------------------------

def build_cases(db_path: Path, seed: int = 11, per_test: int = 3) -> list[dict]:
    """Generate labelled cases from the reference table itself."""
    rng = random.Random(seed)
    db = json.loads(db_path.read_text(encoding="utf-8"))
    cases: list[dict] = []

    for entry in db["entries"]:
        if not entry["evaluable"] or entry["kind"] == "expected_zero":
            continue
        bound = entry["bounds"].get("any") or next(iter(entry["bounds"].values()), None)
        if not bound:
            continue
        lo, hi = bound["low"], bound["high"]
        unit = entry["unit_raw"]

        # Wide margins, so the verdict does not depend on whose table you use.
        wanted = []
        if lo is not None and hi is not None and hi > lo:
            wanted = [("NORMAL", (lo + hi) / 2),
                      ("LOW", lo * 0.5 if lo > 0 else lo - (hi - lo)),
                      ("HIGH", hi * 2 if hi > 0 else hi + (hi - lo))]
        elif hi is not None:                      # "<150"
            wanted = [("NORMAL", hi * 0.4), ("HIGH", hi * 3)]
        elif lo is not None:                      # ">40"
            wanted = [("NORMAL", lo * 3), ("LOW", lo * 0.3)]

        for truth, value in wanted[:per_test]:
            if value is None or value < 0:
                continue
            cases.append({
                "test": entry["test_name"],
                "value": round(value, 3),
                "unit": rng.choice(unit_variants(unit)),
                "truth": truth,
            })
    return cases


# ---------------------------------------------------------------------------
# Arm 1: the matcher this project shipped with (commit 4d01d82)
# ---------------------------------------------------------------------------

class BaselineMatcher:
    """Substring name matching against a 20-row table, as originally shipped.

    Reproduced rather than imported: the code no longer exists in the tree, and
    the point of the ablation is to compare against what really ran.
    """

    def __init__(self, table_path: Path = BASELINE_TABLE):
        self.reference_ranges = json.loads(table_path.read_text(encoding="utf-8"))

    def classify(self, test: str, value, unit=None, sex=None) -> str:
        test_upper = str(test).upper()
        for key, ref in self.reference_ranges.items():
            # THE ORIGINAL LINE, verbatim.
            if key in test_upper or test_upper in key:
                try:
                    val = float(str(value).replace(",", ""))
                except (TypeError, ValueError):
                    return NOT_EVALUATED
                low, high = ref["normal"]
                if val < low:
                    return "LOW"
                if val > high:
                    return "HIGH"
                return "NORMAL"
        return NOT_EVALUATED


# ---------------------------------------------------------------------------
# Arm 2: the current grounded lookup
# ---------------------------------------------------------------------------

class GroundedLookup:
    def __init__(self):
        self.lk = RangeLookup()

    def classify(self, test: str, value, unit=None, sex=None) -> str:
        return self.lk.classify(test, value, unit, sex=sex).status


# ---------------------------------------------------------------------------
# Arm 3 (optional): the fine-tuned model, asked to supply the status itself
# ---------------------------------------------------------------------------

class LLMArm:
    """Gives the model the result WITHOUT a status and asks it to decide.

    This is the behaviour the grounded layer replaced, so it is the arm that
    quantifies what grounding bought.
    """

    PROMPT = (
        "You are reading one lab result. Reply with exactly one word: "
        "HIGH, LOW or NORMAL.\n\n{record}\n\nOne word only:"
    )

    def __init__(self):
        from app.pipeline.llm import BioMistralPipeline
        self.pipe = BioMistralPipeline()

    def classify(self, test: str, value, unit=None, sex=None) -> str:
        record = json.dumps({"test": test, "value": value, "unit": unit or ""})
        out = self.pipe.generate(self.PROMPT.format(record=record), max_new_tokens=8)
        upper = (out or "").upper()
        for token in ("NORMAL", "HIGH", "LOW"):   # NORMAL first: it contains no other
            if token in upper:
                return token
        return NOT_EVALUATED


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score(arm, cases: list[dict]) -> dict:
    counts = Counter()
    for case in cases:
        got = arm.classify(case["test"], case["value"], case["unit"])
        truth = case["truth"]
        counts["n"] += 1
        if got == NOT_EVALUATED or got == "UNKNOWN":
            counts["refused"] += 1
            continue
        counts["answered"] += 1
        if got == truth:
            counts["correct"] += 1
        elif truth == "NORMAL":
            counts["false_abnormal"] += 1     # said HIGH/LOW about a normal value
        elif got == "NORMAL":
            counts["false_normal"] += 1       # said NORMAL about an abnormal value
        else:
            counts["wrong_direction"] += 1    # said HIGH for a LOW, or vice versa
    n = max(counts["n"], 1)
    a = max(counts["answered"], 1)
    return {
        "n": counts["n"],
        "answered": counts["answered"] / n,
        "accuracy": counts["correct"] / n,
        "false_abnormal": counts["false_abnormal"] / n,
        "false_normal": counts["false_normal"] / n,
        "wrong_direction": counts["wrong_direction"] / n,
        # Conditional on having answered. This separates the two failure modes:
        # a small table is a COVERAGE gap, while being wrong about what it did
        # answer is a CORRECTNESS bug. The substring matcher had both, and only
        # this column isolates the second.
        "accuracy_when_answered": counts["correct"] / a,
        "wrong_when_answered": 1 - counts["correct"] / a,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="store_true", help="add the model arm (needs a GPU)")
    ap.add_argument("--sample", type=int, default=0, help="limit cases (use with --llm)")
    ap.add_argument("--markdown", action="store_true", help="emit a markdown table")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    db = HERE / "app" / "reference_ranges" / "reference_db.json"
    cases = build_cases(db, seed=args.seed)
    if args.sample:
        cases = random.Random(args.seed).sample(cases, min(args.sample, len(cases)))

    arms = [("baseline (substring, 20 rows)", BaselineMatcher()),
            ("grounded (reference_ranges)", GroundedLookup())]
    if args.llm:
        arms.append(("LLM decides the status", LLMArm()))

    print(f"{len(cases)} generated cases, ground truth from the reference table\n")
    results = [(label, score(arm, cases)) for label, arm in arms]

    if args.markdown:
        print("| arm | answered | accuracy (all) | accuracy (when it answered) | "
              "wrong when answered | false abnormal |")
        print("|---|---|---|---|---|---|")
        for label, r in results:
            print(f"| {label} | {r['answered']:.1%} | {r['accuracy']:.1%} | "
                  f"{r['accuracy_when_answered']:.1%} | {r['wrong_when_answered']:.1%} | "
                  f"{r['false_abnormal']:.1%} |")
    else:
        print(f"{'arm':32s} {'answered':>9s} {'acc(all)':>9s} {'acc(ans)':>9s} "
              f"{'wrong(ans)':>11s} {'false abn':>10s}")
        print("-" * 86)
        for label, r in results:
            print(f"{label:32s} {r['answered']:8.1%} {r['accuracy']:8.1%} "
                  f"{r['accuracy_when_answered']:8.1%} {r['wrong_when_answered']:10.1%} "
                  f"{r['false_abnormal']:9.1%}")

    print("\nacc(ans)/wrong(ans) are conditional on the arm answering at all, which "
          "separates\na coverage gap from a correctness bug. false abnormal = a healthy "
          "value\nreported HIGH or LOW.")


if __name__ == "__main__":
    main()
