"""Deterministic reference-range lookup and status classification.

This is the function the pipeline calls *before* generation. It answers
"is this value high, low or normal?" with arithmetic, and hands the answer to
the language model as a fact to explain. The model is never asked to decide it.

    from code.reference_ranges.range_lookup import RangeLookup

    lk = RangeLookup()
    r = lk.classify("Hemoglbin", 12.1, unit="g/dL", sex="F")
    r.status            # 'NORMAL'
    r.matched_test      # 'Hemoglobin'
    r.reference_text    # '11.6-15.0 g/dL'

Two halves, deliberately separated:

* Resolving the test NAME is a search problem. OCR yields "Hemoglbin", "HGB",
  "Haemoglobin", so this half is layered: exact -> alias -> fuzzy -> vector.
* Comparing the VALUE is arithmetic. It is `<` and `>` against bounds parsed at
  build time. No similarity score ever reaches this half.

Every path that cannot produce a confident answer returns NOT_EVALUATED with a
machine-readable reason. There is no fallback guess anywhere in this module.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    from .units import UnitError, compatible, convert, normalize_unit, unit_group
    from .build_reference_db import normalize_name, name_tokens
except ImportError:  # pragma: no cover - direct-script execution
    from units import UnitError, compatible, convert, normalize_unit, unit_group  # type: ignore
    from build_reference_db import normalize_name, name_tokens  # type: ignore

DEFAULT_DB = Path(__file__).resolve().parent / "reference_db.json"
DEFAULT_CHROMA_DIR = Path(__file__).resolve().parent / "chroma_index"

# ---------------------------------------------------------------------------
# Status vocabulary. Kept small and closed so prompts can enumerate it.
# ---------------------------------------------------------------------------
NORMAL = "NORMAL"
LOW = "LOW"
HIGH = "HIGH"
PRESENT = "PRESENT"          # analyte expected to be absent was detected
NOT_EVALUATED = "NOT_EVALUATED"

# Unit groups that describe a measurement CONTEXT rather than a natural unit for
# an analyte. A missing unit may never be assumed to be one of these: the same
# test name means something completely different in blood and in urine
# microscopy, and picking the wrong one silently produces a confident, wrong
# status. See the MISSING_UNIT branch in classify().
_UNITS_REQUIRING_EXPLICIT = {"per_hpf", "per_100_wbc"}

# mEq/L is charge-equivalents, so converting it to mmol/L needs the ion's
# valence - which is a property of the ANALYTE, not of the unit. units.py
# therefore refuses the conversion outright, and it is resolved here, where the
# test has already been identified.
#
# This matters a lot in practice: most labs report electrolytes in mEq/L, and
# refusing them meant Sodium, Potassium, Chloride and Bicarbonate all came back
# "not checked" on reports whose ranges we hold.
_ION_VALENCE: dict[str, int] = {
    "sodium": 1, "potassium": 1, "chloride": 1, "bicarbonate": 1,
    "lithium": 1, "ammonium": 1,
    "calcium": 2, "magnesium": 2, "calcium, total": 2, "free calcium": 2,
}


def _meq_convertible(test_name: str, unit_a, unit_b) -> bool:
    """True when unit_a/unit_b are the mEq/L <-> mmol/L pair for a known ion."""
    if {normalize_unit(unit_a), normalize_unit(unit_b)} != {"meq/l", "mmol/l"}:
        return False
    return _meq_factor(test_name) is not None


def _meq_factor(test_name: str) -> float | None:
    """mmol per mEq for `test_name`, or None if its valence is unknown.

    1.0 for a monovalent ion (1 mEq = 1 mmol), 0.5 for a divalent one
    (1 mEq = 0.5 mmol). Unknown analytes stay refused rather than guessed.
    """
    key = normalize_name(test_name)
    valence = _ION_VALENCE.get(key)
    if valence is None:
        base = key.split(",")[0].strip()
        valence = _ION_VALENCE.get(base)
    return None if valence is None else 1.0 / valence

# Plain-English wording for each refusal. The generator is told never to print
# raw codes, so it must be GIVEN the sentence rather than left to invent one -
# asked to paraphrase UNIT_MISMATCH it wrote "the reference range is missing",
# which is simply untrue.
REASON_TEXT: dict[str, str] = {
    "TEST_NOT_IN_REFERENCE_TABLE": "this test is not in our reference table",
    "TEST_NOT_FOUND": "we could not recognise this test name",
    "AMBIGUOUS_MATCH": "this name matches more than one test, so we cannot tell which one it is",
    "UNIT_MISMATCH": "the units on the report do not match our reference table",
    "UNIT_ON_UNITLESS_TEST": "this test is a ratio or index and has no units, but the report shows one",
    "SUSPECTED_UNIT_MISMATCH": "the value looks far outside the expected units for this test",
    "MISSING_UNIT": "the report did not show a unit, and this test cannot be read without one",
    "QUALITATIVE_ANALYTE": "this test is reported as a description, not a number",
    "BODY_FLUID_NO_FIXED_RANGE": "body-fluid results are read against a matching blood sample",
    "NO_STANDARDIZED_RANGE": "there is no standard reference range for this test",
    "NOMOGRAM_REQUIRED": "this test is read against an age chart, not a fixed range",
    "AMBIGUOUS_PEAK_TROUGH": "this drug level depends on when the dose was given",
    "SEX_REQUIRED": "this test needs the patient's sex, which was not on the report",
    "NO_NUMERIC_VALUE": "no number could be read for this test",
    "NO_APPLICABLE_RANGE": "no reference range applies to this result",
}


def reason_text(reason: str | None) -> str:
    """Plain sentence for a refusal reason code."""
    return REASON_TEXT.get(reason or "", "we could not check this result")

# ---------------------------------------------------------------------------
# Curated aliases: report shorthand -> exact table test name.
# ---------------------------------------------------------------------------
ALIASES: dict[str, str] = {
    # haematology
    "hb": "Hemoglobin",
    "hgb": "Hemoglobin",
    "haemoglobin": "Hemoglobin",
    "hct": "Hematocrit",
    "pcv": "Hematocrit",
    "packed cell volume": "Hematocrit",
    "plt": "Platelet Count",
    "platelets": "Platelet Count",
    "platelet": "Platelet Count",
    "tlc": "WBC Count",
    "total leucocyte count": "WBC Count",
    "total leukocyte count": "WBC Count",
    "leucocyte count": "WBC Count",
    "leukocyte count": "WBC Count",
    "wbc": "WBC Count",
    # The table's `White Blood Cells` row is URINE microscopy (0-5 /HPF). On a
    # CBC this name means the blood count, so it is aliased to WBC Count; the
    # unit gate decides which one applies.
    "white blood cells": "WBC Count",
    # `Red Blood Cells` also exists as a urine-microscopy row (0-3 /HPF). With a
    # blood unit the alias tier reaches the real count; with /HPF the exact tier
    # keeps the microscopy row; with no unit at all it is refused.
    "red blood cells": "RBC Count",
    "erythrocytes": "RBC Count",
    "rbc count": "RBC Count",
    # Bare "RBC" exact-matches the urine-microscopy row. With a /HPF unit that
    # row is correct and wins in the exact tier; with a blood unit the exact
    # tier fails on units and this alias reaches the whole-blood count.
    "rbc": "RBC Count",
    "total rbc count": "RBC Count",
    "white blood cell count": "WBC Count",
    "total wbc count": "WBC Count",
    "leucocytes": "WBC Count",
    "leukocytes": "WBC Count",
    "mpv": "Mean Platelet Volume",
    "anc": "Absolute Neutrophil Count",
    "neutrophils %": "Neutrophils",
    "lymphocytes %": "Lymphocytes",
    # chemistry
    "ast": "Asparate Aminotransferase (AST)",   # sic: source table misspells 'Aspartate'
    "sgot": "Asparate Aminotransferase (AST)",
    "alt": "Alanine Aminotransferase (ALT)",
    "sgpt": "Alanine Aminotransferase (ALT)",
    "alp": "Alkaline Phosphatase",
    "total protein": "Protein",
    "na": "Sodium",
    "k": "Potassium",
    "cl": "Chloride",
    "ca": "Calcium",
    # endocrine
    "tsh": "Thyroid Stimulating Hormone",
    "t3": "Triiodothyronine (T3)",
    "t4": "Thyroxine (T4)",
    "ft4": "Thyroxine (T4), Free",
    "free t4": "Thyroxine (T4), Free",
    "hba1c": "Glycated Hemoglobin",
    "a1c": "Glycated Hemoglobin",
    "glycosylated hemoglobin": "Glycated Hemoglobin",
    # lipids
    "ldl": "Cholesterol, LDL, Calculated",
    "ldl cholesterol": "Cholesterol, LDL, Calculated",
    "hdl": "Cholesterol, HDL",
    "hdl cholesterol": "Cholesterol, HDL",
    "total cholesterol": "Cholesterol, Total",
    "cholesterol": "Cholesterol, Total",
    "tg": "Triglycerides",
    "triglyceride": "Triglycerides",
    # misc
    "crp": "C-Reactive Protein",
    "psa": "Prostate Specific Antigen",
    "fbs": "Glucose",
    "rbs": "Glucose",
    "fasting blood sugar": "Glucose",
    "random blood sugar": "Glucose",
    "blood sugar": "Glucose",
    "b12": "Vitamin B12",
    "vitamin b12": "Vitamin B12",
    "vit b12": "Vitamin B12",
    "vitamin d": "25-OH Vitamin D",
    "vit d": "25-OH Vitamin D",
    "inr": "INR(PT)",
    "pt": "Prothrombin Time",
    "aptt": "APTT",
    "esr": "ESR",
    "bun": "Bun",
    "blood urea nitrogen": "Bun",
    "blood urea": "Urea",
    "egfr": "eGFR",
    "gfr": "eGFR",
}

# Tests this workbook simply does not contain. Naming them explicitly gives the
# patient an honest "not in our reference table" instead of letting fuzzy search
# drag them onto a neighbouring row.
KNOWN_ABSENT: dict[str, str] = {
    # Still genuinely absent after the supplement in additional_ranges.json.
    "pdw": "platelet distribution width",
    "pct": "plateletcrit",
    "rdw cv": "red cell distribution width (CV)",
    "rdw sd": "red cell distribution width (SD)",
    "ptt": "partial thromboplastin time (unactivated)",
    # NOTE: MCV, MCH, MCHC, RDW, ESR, eGFR, PT, APTT and the whole-blood red
    # cell count used to live here. They are now in the table via
    # additional_ranges.json. BUN was never actually missing - the workbook
    # spells it `Bun` (7-20 mg/dL), which is why searching for "blood urea
    # nitrogen" did not find it.
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    """The grounded fact handed to the generator."""

    status: str
    test_query: str
    value: float | None = None
    unit_query: str | None = None

    matched_test: str | None = None
    match_tier: str | None = None          # exact | alias | fuzzy | vector
    match_confidence: float | None = None

    reference_text: str | None = None      # human-readable, e.g. '11.6-15.0 g/dL'
    reference_low: float | None = None
    reference_high: float | None = None
    reference_unit: str | None = None
    value_in_reference_unit: float | None = None
    context: str | None = None             # 'M' | 'F' | 'any'

    reason: str | None = None              # set when status == NOT_EVALUATED
    caveats: list[str] = field(default_factory=list)
    source: str = "lab_test_reference_ranges_1.xlsx"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_prompt_line(self) -> str:
        """One-line grounded fact for the generation prompt.

        The generator is instructed to explain this, never to recompute it.
        """
        name = self.matched_test or self.test_query
        if self.status == NOT_EVALUATED:
            line = (
                f"- {name}: {_fmt(self.value)} {self.unit_query or ''}".rstrip()
                + f" | status=NOT_CHECKED | why={reason_text(self.reason)}"
            )
            if self.caveats:
                line += " | caveats=" + "; ".join(self.caveats)
            return line
        line = (
            f"- {name}: {_fmt(self.value_in_reference_unit)} {self.reference_unit or ''}".rstrip()
            + f" | reference={self.reference_text} | status={self.status}"
        )
        if self.caveats:
            line += " | caveats=" + "; ".join(self.caveats)
        return line


@dataclass
class _Candidate:
    entry: dict[str, Any]
    score: float
    tier: str


def _fmt(v: float | None) -> str:
    if v is None:
        return "?"
    return f"{v:g}"


def parse_value(raw: Any) -> float | None:
    """Pull a number out of an OCR'd result cell.

    Handles thousands separators and stray comparators ('<0.01'). Returns None
    when there is no unambiguous number, which the caller treats as
    NOT_EVALUATED rather than zero.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = unicodedata.normalize("NFKC", str(raw)).strip()
    s = s.replace(",", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _signature(entry: dict[str, Any]) -> tuple:
    """Identity of an entry for ambiguity checks: same bounds+unit == same answer."""
    return (
        json.dumps(entry["bounds"], sort_keys=True),
        entry["unit_normalized"],
        entry["evaluable"],
    )


# ---------------------------------------------------------------------------
# The lookup
# ---------------------------------------------------------------------------

class RangeLookup:
    """Layered test-name resolver plus arithmetic range comparison."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB,
        *,
        fuzzy_threshold: float = 88.0,
        ambiguity_margin: float = 3.0,
        vector_enabled: bool = False,
        vector_threshold: float = 0.62,
        chroma_dir: Path | str = DEFAULT_CHROMA_DIR,
        assume_unit_when_missing: bool = True,
        plausibility_factor: float = 100.0,
    ) -> None:
        self.db = json.loads(Path(db_path).read_text(encoding="utf-8"))
        self.entries: list[dict[str, Any]] = self.db["entries"]
        self.fuzzy_threshold = fuzzy_threshold
        self.ambiguity_margin = ambiguity_margin
        self.vector_enabled = vector_enabled
        self.vector_threshold = vector_threshold
        self.chroma_dir = Path(chroma_dir)
        self.assume_unit_when_missing = assume_unit_when_missing
        self.plausibility_factor = plausibility_factor

        self._by_name: dict[str, list[dict[str, Any]]] = {}
        for e in self.entries:
            self._by_name.setdefault(e["normalized"], []).append(e)

        self._alias_norm = {normalize_name(k): v for k, v in ALIASES.items()}
        self._reversed_norm = self._build_reversed_index()
        self._absent_norm = {normalize_name(k): v for k, v in KNOWN_ABSENT.items()}

        self._choices = [e["tokens"] for e in self.entries]
        self._last_ambiguous: list[str] = []
        self._collection = None  # lazily built Chroma collection

    def _build_reversed_index(self) -> dict[str, list[dict[str, Any]]]:
        """Index `Analyte, Qualifier` rows under `Qualifier Analyte` too.

        The workbook names tests the way an index does - "Bilirubin, Direct",
        "Cholesterol, HDL", "Thyroxine (T4), Free" - while reports write them
        the way people speak: "Direct Bilirubin", "HDL Cholesterol". Without
        this, "Direct Bilirubin" fuzzy-matches `Bilirubin, Direct`, `Bilirubin`
        and `Bilirubin, Neonatal, Direct` at an identical score and is refused
        as ambiguous, even though one of them is exactly right.

        This is deterministic string rewriting, not similarity: a name either is
        a comma-reversal of a table row or it is not. Reversals that collide
        with an existing name, or with each other, are dropped rather than
        guessed at.
        """
        index: dict[str, list[dict[str, Any]]] = {}
        for entry in self.entries:
            raw = entry["test_name"]
            if "," not in raw:
                continue
            head, _, tail = raw.partition(",")
            reversed_name = normalize_name(f"{tail.strip()} {head.strip()}")
            if not reversed_name or reversed_name in self._by_name:
                continue        # a real row already owns this name
            index.setdefault(reversed_name, []).append(entry)

        # Keep only unambiguous reversals: same bounds+unit is fine (duplicate
        # rows), differing ones are dropped.
        return {
            name: rows for name, rows in index.items()
            if len({_signature(r) for r in rows}) == 1
        }

    # -- name resolution ---------------------------------------------------

    def _exact(self, norm: str) -> list[_Candidate]:
        return [_Candidate(e, 100.0, "exact") for e in self._by_name.get(norm, [])]

    def _alias(self, norm: str) -> list[_Candidate]:
        target = self._alias_norm.get(norm)
        if not target:
            return []
        return [
            _Candidate(e, 100.0, "alias")
            for e in self._by_name.get(normalize_name(target), [])
        ]

    def _reversed(self, norm: str) -> list[_Candidate]:
        """Comma-reversed table names: "Direct Bilirubin" -> "Bilirubin, Direct"."""
        return [
            _Candidate(e, 100.0, "reversed")
            for e in self._reversed_norm.get(norm, [])
        ]

    def _fuzzy(self, norm: str, limit: int = 10) -> list[_Candidate]:
        from rapidfuzz import fuzz, process

        query = name_tokens(norm)
        if not query:
            return []
        hits = process.extract(
            query, self._choices, scorer=fuzz.WRatio, limit=limit, score_cutoff=60
        )
        out: list[_Candidate] = []
        for _, score, idx in hits:
            # token_set_ratio rescues word-order and extra-word cases such as
            # "absolute neutrophils" vs "absolute neutrophil count".
            tset = fuzz.token_set_ratio(query, self._choices[idx])
            out.append(_Candidate(self.entries[idx], max(score, tset), "fuzzy"))
        out.sort(key=lambda c: -c.score)
        return out

    def _vector(self, norm: str, limit: int = 5) -> list[_Candidate]:
        """Semantic last resort. Off by default - see the measurement below.

        Calibrated on 200 sampled rows with OCR-like corruption (see
        calibrate.py). Against transposed characters, enabling this tier moved
        2pp of safe refusals into 0.5pp more correct answers and 1.5pp more
        WRONG ones - three times more wrong than right - while costing ~13x
        latency. The scores are not separable either: 'Bad cholesterol' matches
        'Cholesterol, Pleural' at 0.67, above the 0.63 of the one genuinely
        useful hit ('Vitamin B-12 level' -> 'Vitamin B12'), so no threshold
        splits them.

        Short clinical names are the wrong shape for sentence embeddings:
        'Hemoglobin', 'Hemoglobin F' and 'Fetal Hemoglobin' are near-identical
        vectors with different reference ranges. Trading a safe refusal for a
        3:1 chance of the wrong range is a bad bet in a medical pipeline, so
        this stays opt-in. The index is still worth having for patient-facing
        chat retrieval, where a near-miss is harmless.
        """
        col = self._get_collection()
        if col is None:
            return []
        res = col.query(query_texts=[norm], n_results=limit)
        out: list[_Candidate] = []
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for rid, dist in zip(ids, dists):
            similarity = 1.0 - float(dist)  # cosine space
            out.append(_Candidate(self.entries[int(rid)], similarity * 100.0, "vector"))
        return out

    def _get_collection(self):
        if self._collection is not None or not self.vector_enabled:
            return self._collection
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=str(self.chroma_dir))
        ef = embedding_functions.ONNXMiniLM_L6_V2()
        col = client.get_or_create_collection(
            name="lab_reference_ranges",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        if col.count() == 0:
            col.add(
                ids=[str(e["id"]) for e in self.entries],
                documents=[_embed_text(e) for e in self.entries],
                metadatas=[
                    {
                        "test_name": e["test_name"],
                        "unit": e["unit_raw"] or "",
                        "unit_group": e["unit_group"] or "",
                        "evaluable": bool(e["evaluable"]),
                    }
                    for e in self.entries
                ],
            )
        self._collection = col
        return col

    def build_vector_index(self) -> int:
        """Materialise the Chroma collection ahead of time. Returns row count."""
        self.vector_enabled = True
        col = self._get_collection()
        return col.count() if col is not None else 0

    def resolve(
        self, test_name: str, unit: str | None = None
    ) -> tuple[_Candidate | None, str | None, list[str]]:
        """Resolve a reported test name to a reference row.

        Returns (candidate, failure_reason, caveats). Unit is used to
        disambiguate, never to override an exact name hit's identity.
        """
        caveats: list[str] = []
        norm = normalize_name(test_name)
        if not norm:
            return None, "EMPTY_TEST_NAME", caveats

        if norm in self._absent_norm and norm not in self._by_name:
            return None, "TEST_NOT_IN_REFERENCE_TABLE", caveats

        # A UNIT_MISMATCH in one tier must NOT abort resolution. The table's
        # `White Blood Cells` is a urine-microscopy row, so a CBC's
        # "White Blood Cells 10.1 x10^3/uL" hits an exact name match whose unit
        # is incompatible - but `WBC Count` is sitting in the alias tier with
        # exactly the right range. Remember the mismatch and keep looking; only
        # report it if no later tier resolves.
        deferred: str | None = None

        # Reports routinely write a test as "NAME (SYNONYM)": "SGPT (ALT)",
        # "SGOT (AST)", "Glucose (Fasting)", "Vitamin D (25-OH)". Neither half
        # alone is the full string, so try the whole name first, then the part
        # before the bracket, then the part inside it. All three go through the
        # SAME exact/alias/reversed tiers - this widens what we recognise, it
        # does not loosen how confidently we match.
        for norm in self._name_variants(norm):
            picked, reason, caveats2 = self._resolve_exactish(norm, unit)
            if picked:
                caveats.extend(caveats2)
                return picked, None, caveats
            if reason:
                return None, reason, caveats
        norm = normalize_name(test_name)

        for tier_fn in ():
            picked, reason = self._select(tier_fn(norm), unit, threshold=100.0)
            if picked:
                return picked, None, caveats
            if reason == "UNIT_MISMATCH":
                deferred = deferred or reason
            elif reason:
                return None, reason, caveats

        # An exact or alias hit whose unit disagrees means the ANALYTE is
        # identified and the unit is wrong. Stop here. Continuing to fuzzy search
        # looks for any row with a compatible unit and finds a different sample
        # type: "RBC 4.9 x10^6/uL" matched `RBC, CSF` (a CSF red-cell count,
        # expected 0) and came back HIGH, and "Glucose 5.5 mmol/L" matched
        # `Glucose, Stool`. Sample type is semantic, not something a unit or a
        # string distance can decide.
        # A name on the known-absent list has now failed exact and alias
        # matching, which means this workbook genuinely lacks it for this sample
        # type. Say so - it is more informative than a unit complaint, and it
        # stops fuzzy search dragging the name onto a neighbouring row, which is
        # exactly how a CBC red-cell count ended up scored against urine.
        if norm in self._absent_norm:
            return None, "TEST_NOT_IN_REFERENCE_TABLE", caveats

        if deferred:
            return None, deferred, caveats

        picked, reason = self._select(self._fuzzy(norm), unit, self.fuzzy_threshold)
        if picked:
            if picked.score < 96:
                caveats.append(
                    f"test name matched approximately: "
                    f"'{test_name}' -> '{picked.entry['test_name']}'"
                )
            return picked, None, caveats
        if reason == "UNIT_MISMATCH":
            deferred = deferred or reason
        elif reason:
            return None, reason, caveats

        if self.vector_enabled:
            picked, reason = self._select(
                self._vector(norm), unit, self.vector_threshold * 100
            )
            if picked:
                caveats.append(
                    f"test name matched semantically: "
                    f"'{test_name}' -> '{picked.entry['test_name']}'"
                )
                return picked, None, caveats
            if reason == "UNIT_MISMATCH":
                deferred = deferred or reason
            elif reason:
                return None, reason, caveats

        # A name we know this workbook lacks gives a clearer answer than a bare
        # "not found" - even when a same-named row exists for a different sample
        # type (there is no CBC red-cell count here, only urine microscopy).
        if norm in self._absent_norm:
            return None, "TEST_NOT_IN_REFERENCE_TABLE", caveats
        return None, "TEST_NOT_FOUND", caveats

    def _name_variants(self, norm: str) -> list[str]:
        """The full name, then the text outside brackets, then inside them."""
        variants = [norm]
        m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*(.*)$", norm)
        if m:
            outside = (m.group(1) + " " + m.group(3)).strip()
            inside = m.group(2).strip()
            for v in (outside, inside):
                v = normalize_name(v)
                if v and v not in variants:
                    variants.append(v)
        return variants

    def _resolve_exactish(self, norm: str, unit: str | None):
        """Exact, alias and comma-reversed tiers for one name variant."""
        deferred = None
        for tier_fn in (self._exact, self._alias, self._reversed):
            picked, reason = self._select(tier_fn(norm), unit, threshold=100.0)
            if picked:
                return picked, None, []
            if reason == "UNIT_MISMATCH":
                deferred = deferred or reason
            elif reason:
                return None, reason, []
        return None, deferred, []

    def _select(
        self, cands: Sequence[_Candidate], unit: str | None, threshold: float
    ) -> tuple[_Candidate | None, str | None]:
        """Pick one candidate from a tier, or refuse.

        Returns (candidate, None) on success, (None, reason) on a hard refusal,
        and (None, None) to mean "nothing here, try the next tier".

        Unit filtering happens BEFORE score ranking, and that ordering matters.
        Plain string similarity ranks the substring `Lymphocytes` (20-40 %)
        above `Absolute Lymphocyte Count` (1.0-4.8 x10^3/uL) for the query
        "ABSOLUTE LYMPHOCYTES" - the same substring trap the old notebook fell
        into. Dropping unit-incompatible rows first lets the correct row win on
        score instead of merely being rescued by a later mismatch check.
        """
        if not cands:
            return None, None

        top_unfiltered = max(c.score for c in cands)
        pool = list(cands)

        if unit and normalize_unit(unit):
            compat = [
                c
                for c in pool
                if not c.entry["unit_normalized"]
                or compatible(unit, c.entry["unit_raw"])
                # mEq/L <-> mmol/L depends on the analyte's charge, so it cannot
                # be settled by units.py alone. Without this the candidate is
                # dropped here and classify() never reaches the conversion.
                or _meq_convertible(c.entry["test_name"], unit, c.entry["unit_raw"])
            ]
            if compat:
                pool = compat
            else:
                # Only call it a unit mismatch when the NAME really did match;
                # otherwise this tier simply has nothing to offer.
                return (None, "UNIT_MISMATCH") if top_unfiltered >= threshold else (None, None)

        pool = [c for c in pool if c.score >= threshold]
        if not pool:
            return None, None

        # Prefer an evaluable row when several share the top score.
        top = max(c.score for c in pool)
        near = [c for c in pool if top - c.score <= self.ambiguity_margin]
        evaluable = [c for c in near if c.entry["evaluable"]]
        if evaluable:
            near = evaluable

        sigs = {_signature(c.entry) for c in near}
        if len(sigs) > 1:
            # Record the rivals so the caller can say WHICH tests it is torn
            # between. OCR that merges two table rows into one name lands here,
            # e.g. "LDL, Calculated, Cholesterol, Total (Calc.)" - and the two
            # candidates disagree about the answer (145 is HIGH for LDL but
            # NORMAL for total cholesterol), so guessing is not an option.
            self._last_ambiguous = [c.entry["test_name"] for c in near][:4]
            return None, "AMBIGUOUS_MATCH"
        return max(near, key=lambda c: c.score), None

    # -- classification ----------------------------------------------------

    def classify(
        self,
        test_name: str,
        value: Any,
        unit: str | None = None,
        sex: str | None = None,
    ) -> Classification:
        """Classify a single reported result. Never raises, never guesses.

        Enforces one invariant on the way out: a result we refused to check
        carries NO reference range. The bounds are chosen before units are
        reconciled, so several refusal paths would otherwise return a populated
        range - and the card then showed "NOT CHECKED" next to "Normal: <5",
        which reads as a contradiction.
        """
        res = self._classify(test_name, value, unit, sex)
        if res.status == NOT_EVALUATED:
            res.reference_text = None
            res.reference_low = None
            res.reference_high = None
            res.value_in_reference_unit = None
        return res

    def _classify(
        self,
        test_name: str,
        value: Any,
        unit: str | None = None,
        sex: str | None = None,
    ) -> Classification:
        val = parse_value(value)
        res = Classification(
            status=NOT_EVALUATED,
            test_query=str(test_name),
            value=val,
            unit_query=unit,
        )

        self._last_ambiguous = []
        cand, reason, caveats = self.resolve(test_name, unit)
        res.caveats.extend(caveats)
        if cand is None:
            res.reason = reason
            if reason == "AMBIGUOUS_MATCH" and self._last_ambiguous:
                res.caveats.append(
                    "this name matches several tests ("
                    + ", ".join(self._last_ambiguous)
                    + "), which usually means two rows of the report were read as one"
                )
            return res

        entry = cand.entry
        res.matched_test = entry["test_name"]
        res.match_tier = cand.tier
        res.match_confidence = round(cand.score, 1)
        res.reference_unit = entry["unit_raw"]
        if entry.get("caveat"):
            res.caveats.append(entry["caveat"])

        if val is None:
            res.reason = "NO_NUMERIC_VALUE"
            return res

        if not entry["evaluable"]:
            res.reason = entry["not_evaluable_reason"]
            res.reference_text = entry["raw_range"]
            return res

        # -- pick the bound set for this patient ---------------------------
        bounds_map = entry["bounds"]
        ctx = "any"
        sex_key = (sex or "").strip().upper()[:1]
        if entry["kind"] == "sex_specific":
            if sex_key in ("M", "F") and sex_key in bounds_map:
                ctx = sex_key
            elif "any" in bounds_map:
                ctx = "any"
                other = {k: v for k, v in bounds_map.items() if k in ("M", "F")}
                res.caveats.append(
                    "patient sex not provided; combined adult range used "
                    + "("
                    + ", ".join(
                        f"{k}: {_fmt(v['low'])}-{_fmt(v['high'])}" for k, v in other.items()
                    )
                    + ")"
                )
            else:
                res.reason = "SEX_REQUIRED"
                res.reference_text = entry["raw_range"]
                return res
        if ctx not in bounds_map:
            res.reason = "NO_APPLICABLE_RANGE"
            return res

        bound = bounds_map[ctx]
        res.context = ctx
        res.reference_low = bound["low"]
        res.reference_high = bound["high"]

        # -- unit reconciliation -------------------------------------------
        ref_unit = entry["unit_raw"]
        assumed = False
        if normalize_unit(unit) and normalize_unit(ref_unit):
            try:
                val_ref = convert(val, unit, ref_unit)
            except UnitError:
                # mEq/L <-> mmol/L is the one conversion that depends on the
                # analyte, so it is resolved here rather than in units.py.
                factor = None
                if {normalize_unit(unit), normalize_unit(ref_unit)} == {"meq/l", "mmol/l"}:
                    factor = _meq_factor(entry["test_name"])
                if factor is None:
                    res.reason = "UNIT_MISMATCH"
                    res.reference_text = _range_text(bound, ref_unit)
                    return res
                val_ref = (val * factor if normalize_unit(unit) == "meq/l"
                           else val / factor)
                res.caveats.append(
                    f"converted from {unit} using the charge of {entry['test_name']}"
                )
        elif normalize_unit(unit) and not normalize_unit(ref_unit):
            # Reference row is unitless (a score, index or ratio) but the report
            # carries a unit, so they are not describing the same quantity.
            # `Cholesterol Ratio (Total/HDL)` is the case that surfaced this: a
            # ratio has no units, and a report showing "42 mg/dL" for it has
            # picked up the wrong column.
            res.reason = "UNIT_ON_UNITLESS_TEST"
            return res
        else:
            val_ref = val
            if normalize_unit(ref_unit):
                # Some units are context-specific rather than the obvious unit
                # for an analyte, so assuming them is never safe. /HPF is the
                # motivating case: the table's `Red Blood Cells` and
                # `White Blood Cells` are URINE MICROSCOPY rows (0-3 and 0-5
                # per high-power field). A CBC reporting "Red Blood Cells 5.37"
                # with the unit lost to OCR would otherwise be scored against
                # urine and reported HIGH - and at only ~1.8x the bound, the
                # implausibility check never fires. A report that means /HPF
                # says so, so require it explicitly.
                if unit_group(ref_unit) in _UNITS_REQUIRING_EXPLICIT:
                    res.reason = "MISSING_UNIT"
                    res.reference_text = _range_text(bound, ref_unit)
                    res.caveats.append(
                        f"no unit on the report; {entry['test_name']} in this table is "
                        f"a microscopy count ({ref_unit}) and cannot be assumed"
                    )
                    return res
                if not self.assume_unit_when_missing:
                    res.reason = "MISSING_UNIT"
                    res.reference_text = _range_text(bound, ref_unit)
                    return res
                assumed = True

        res.value_in_reference_unit = val_ref
        res.reference_text = _range_text(bound, ref_unit)

        # When the unit had to be assumed, a value orders of magnitude outside
        # the range is far more likely a unit mismatch than a real result.
        # Refusing here is what stops "Glucose 5.5 mmol/L" being read as
        # 5.5 mg/dL and reported as catastrophically low.
        if assumed and _implausible(val_ref, bound, self.plausibility_factor):
            res.reason = "SUSPECTED_UNIT_MISMATCH"
            res.caveats.append(
                f"no unit on report; value is implausible for {ref_unit}"
            )
            return res
        if assumed:
            res.caveats.append(f"unit not detected on report; assumed {ref_unit}")

        # -- the arithmetic -------------------------------------------------
        res.status = _compare(val_ref, bound, entry["kind"])
        if entry.get("qualifier"):
            res.caveats.append(f"reference applies to: {entry['qualifier']}")
        return res

    def classify_many(
        self, results: Iterable[dict[str, Any]], sex: str | None = None
    ) -> list[Classification]:
        """Classify a Stage-3 `lab_results` list.

        Each item may use the keys test/test_name/name, value/result, unit/units.
        """
        out = []
        for item in results:
            name = item.get("test") or item.get("test_name") or item.get("name") or ""
            value = item.get("value", item.get("result"))
            unit = item.get("unit", item.get("units"))
            out.append(self.classify(name, value, unit, sex=item.get("sex", sex)))
        return out


def _range_text(bound: dict[str, Any], unit: str | None) -> str:
    lo, hi = bound["low"], bound["high"]
    u = f" {unit}" if unit else ""
    if lo is not None and hi is not None:
        if lo == hi:
            return f"{_fmt(lo)}{u}"
        return f"{_fmt(lo)}-{_fmt(hi)}{u}"
    if hi is not None:
        return f"{'<=' if bound['inclusive_high'] else '<'}{_fmt(hi)}{u}"
    if lo is not None:
        return f"{'>=' if bound['inclusive_low'] else '>'}{_fmt(lo)}{u}"
    return "unspecified"


def _compare(value: float, bound: dict[str, Any], kind: str) -> str:
    lo, hi = bound["low"], bound["high"]
    if kind == "expected_zero":
        return NORMAL if value == 0 else PRESENT
    if lo is not None:
        if value < lo or (value == lo and not bound["inclusive_low"]):
            return LOW
    if hi is not None:
        if value > hi or (value == hi and not bound["inclusive_high"]):
            return HIGH
    return NORMAL


def _implausible(value: float, bound: dict[str, Any], factor: float) -> bool:
    lo, hi = bound["low"], bound["high"]
    if hi is not None and hi > 0 and value > hi * factor:
        return True
    if lo is not None and lo > 0 and value < lo / factor:
        return True
    return False


def _embed_text(entry: dict[str, Any]) -> str:
    """Document text for the vector tier: the name, plus unit for context."""
    parts = [entry["test_name"]]
    if entry["unit_raw"]:
        parts.append(f"({entry['unit_raw']})")
    return " ".join(parts)


GROUNDING_INSTRUCTION = (
    "The STATUS of every result below was computed by a deterministic lookup "
    "against a reference-range table. Explain each status in plain language. "
    "Do NOT re-evaluate, re-calculate, or contradict a status, and do not infer "
    "a status for any result marked NOT_EVALUATED - for those, say that this "
    "report's reference table does not cover the test and the patient should "
    "ask their doctor. State any caveats shown."
)


def build_grounding_block(
    classifications: Sequence[Classification], include_instruction: bool = True
) -> str:
    """Render classifications as the grounded-facts section of the prompt.

    This is the contract with the generator: statuses arrive as given facts, so
    the model's job is explanation rather than judgement.
    """
    lines: list[str] = []
    if include_instruction:
        lines.append(GROUNDING_INSTRUCTION)
        lines.append("")
    lines.append("LAB RESULTS (status is authoritative):")
    for c in classifications:
        lines.append(c.to_prompt_line())
    evaluated = [c for c in classifications if c.status != NOT_EVALUATED]
    skipped = [c for c in classifications if c.status == NOT_EVALUATED]
    lines.append("")
    lines.append(
        f"({len(evaluated)} of {len(classifications)} results had a usable "
        f"reference range; {len(skipped)} could not be evaluated.)"
    )
    return "\n".join(lines)


_DEFAULT: RangeLookup | None = None


def get_lookup(**kwargs: Any) -> RangeLookup:
    """Process-wide singleton so the 653-row DB is parsed once."""
    global _DEFAULT
    if _DEFAULT is None or kwargs:
        lk = RangeLookup(**kwargs)
        if not kwargs:
            _DEFAULT = lk
        return lk
    return _DEFAULT


def classify(
    test_name: str, value: Any, unit: str | None = None, sex: str | None = None
) -> Classification:
    """Module-level convenience wrapper around the singleton."""
    return get_lookup().classify(test_name, value, unit, sex)
