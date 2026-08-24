"""Readability measurement and a generate → score → revise loop.

The TA's requirement is a Flesch-Kincaid self-evaluation loop that adjusts the
prompt until the explanation reads at grade 8 or below. The fine-tuned model
currently averages grade 10.5 on the held-out set, so roughly 2.5 grades of
simplification are needed.

Two deliberate design decisions:

* This is a plain function, not a graph framework. The control flow is
  generate → score → revise, three nodes with one loop edge, and wrapping that
  in LangGraph would add a dependency and state plumbing without changing
  behaviour. `revise_to_grade` is written so its pieces port unchanged into
  LangGraph nodes if the graph diagram is wanted for the report.

* It returns the BEST-scoring attempt, not the last one. Simplification
  plateaus and sometimes regresses, so keeping the final round would
  occasionally ship a worse answer than one already produced.

Numeric fidelity is checked after every rewrite. "Keep every number exactly" is
the instruction a model is most likely to violate, and the held-out numeric
fidelity of 100% is the one metric that must not regress: a summary that reads
beautifully but moves a decimal point is worse than one that reads at grade 11.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

try:
    import textstat
except ImportError:  # pragma: no cover - textstat is a light, pure-python dep
    textstat = None


# Matches integers and decimals, including thousands separators.
_NUMBER = re.compile(r'\d+(?:,\d{3})*(?:\.\d+)?')


def flesch_kincaid_grade(text: str) -> Optional[float]:
    """US grade level of `text`, or None when textstat is unavailable."""
    if textstat is None or not text or not text.strip():
        return None
    try:
        return float(textstat.flesch_kincaid_grade(text))
    except Exception:  # noqa: BLE001 - never let a metric break generation
        return None


def extract_numbers(text: str) -> List[str]:
    """Every number in `text`, normalised so 1,234 and 1234 compare equal."""
    return sorted(m.group(0).replace(',', '') for m in _NUMBER.finditer(text or ''))


def numbers_preserved(original: str, revised: str) -> bool:
    """True when the rewrite introduced or dropped no numeric values.

    Compares multisets, so a repeated value must stay repeated. This is the
    guard that stops a simplification pass from quietly changing a result.
    """
    return extract_numbers(original) == extract_numbers(revised)


REVISION_INSTRUCTION = (
    "Rewrite the explanation below so a 13-year-old can read it easily "
    "(US grade {target:.0f} or lower). It currently reads at grade {grade:.1f}.\n"
    "- Use shorter sentences. Aim for under 15 words each.\n"
    "- Replace long or technical words with everyday ones.\n"
    "- Keep every number, unit, test name and status EXACTLY as written.\n"
    "- Keep the same sections and the same meaning.\n"
    "- Do not add new medical claims.\n\n"
    "TEXT TO REWRITE:\n{text}"
)


@dataclass
class ReadabilityResult:
    """The chosen text plus the full audit trail of how it was reached."""

    text: str
    grade: Optional[float]
    rounds: int = 0
    history: List[dict] = field(default_factory=list)
    target_met: bool = False

    def summary(self) -> str:
        g = f"{self.grade:.1f}" if self.grade is not None else "n/a"
        return f"grade {g} after {self.rounds} revision(s), target_met={self.target_met}"


def revise_to_grade(
    initial_text: str,
    generate: Callable[[str], str],
    target_grade: float = 8.0,
    max_rounds: int = 2,
) -> ReadabilityResult:
    """Iteratively simplify `initial_text` until it reads at `target_grade`.

    `generate` is any callable taking a prompt and returning text, which keeps
    this testable on CPU with a stub and identical in production with
    BioMistral behind it.
    """
    best_text = initial_text
    best_grade = flesch_kincaid_grade(initial_text)
    history = [{"round": 0, "grade": best_grade, "accepted": True, "note": "initial"}]

    # No textstat, or an unscoreable string: return unchanged rather than
    # burning GPU time on a loop that cannot measure its own progress.
    if best_grade is None:
        return ReadabilityResult(best_text, None, 0, history, False)

    current = initial_text
    rounds = 0

    for attempt in range(1, max_rounds + 1):
        if best_grade <= target_grade:
            break

        prompt = REVISION_INSTRUCTION.format(
            target=target_grade, grade=best_grade, text=current
        )
        try:
            candidate = generate(prompt)
        except Exception as exc:  # noqa: BLE001 - a failed rewrite is not fatal
            history.append({"round": attempt, "error": str(exc), "accepted": False})
            break

        rounds = attempt
        cand_grade = flesch_kincaid_grade(candidate)

        if not candidate or not candidate.strip() or cand_grade is None:
            history.append({"round": attempt, "grade": None,
                            "accepted": False, "note": "empty or unscoreable"})
            continue

        if not numbers_preserved(initial_text, candidate):
            # Non-negotiable: a rewrite that alters the numbers is discarded
            # even if it reads better.
            history.append({"round": attempt, "grade": cand_grade, "accepted": False,
                            "note": "rejected - numeric fidelity lost"})
            continue

        accepted = cand_grade < best_grade
        history.append({"round": attempt, "grade": cand_grade, "accepted": accepted,
                        "note": "improved" if accepted else "no improvement"})
        current = candidate
        if accepted:
            best_text, best_grade = candidate, cand_grade

    return ReadabilityResult(
        text=best_text,
        grade=best_grade,
        rounds=rounds,
        history=history,
        target_met=best_grade is not None and best_grade <= target_grade,
    )
