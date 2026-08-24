"""Tests for the deterministic reference-range lookup.

Run:  python -m pytest code/reference_ranges/test_range_lookup.py -q
      python code/reference_ranges/test_range_lookup.py        (no pytest needed)

The first block reproduces the six false HIGHs from the notebook's substring
matcher and asserts they are gone. The rest pins the safety properties: refuse
rather than guess.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.reference_ranges.range_lookup import (  # noqa: E402
    HIGH,
    LOW,
    NORMAL,
    NOT_EVALUATED,
    PRESENT,
    RangeLookup,
)
from app.reference_ranges import units  # noqa: E402

LK = RangeLookup()


# ---------------------------------------------------------------------------
# 1. The regression that motivated this module
# ---------------------------------------------------------------------------
# The notebook matched with `if key in test_upper or test_upper in key`, so
# MCHC hit MCH's range, and every ABSOLUTE <cell> hit the percentage row.
# A healthy CBC came back with six HIGHs.

def test_absolute_counts_are_not_scored_against_percentages():
    """ABSOLUTE NEUTROPHILS 4.5 x10^3/uL is normal, not HIGH."""
    r = LK.classify("ABSOLUTE NEUTROPHILS", 4.5, "x10^3/uL")
    assert r.status == NORMAL, r
    # The table carries both 'Absolute Neutrophil' and 'Absolute Neutrophil
    # Count' with identical bounds, so either is a correct resolution.
    assert "Neutrophil" in (r.matched_test or ""), r
    assert r.reference_unit == "x10^3/µL", r

    r = LK.classify("ABSOLUTE LYMPHOCYTES", 2.2, "x10^3/uL")
    assert r.status == NORMAL, r
    assert "Lymphocyte" in (r.matched_test or ""), r

    r = LK.classify("ABSOLUTE EOSINOPHILS", 0.15, "x10^3/uL")
    assert r.status == NORMAL, r


def test_absolute_count_in_per_microlitre_converts():
    """4500 /uL is the same as 4.5 x10^3/uL and must classify identically."""
    r = LK.classify("Absolute Neutrophil Count", 4500, "/uL")
    assert r.status == NORMAL, r
    assert abs(r.value_in_reference_unit - 4.5) < 1e-9, r


def test_percentage_row_still_works_in_percent():
    r = LK.classify("Neutrophils", 55, "%")
    assert r.status == NORMAL, r
    assert r.reference_text == "40-70 %", r


def test_mchc_uses_its_own_range_not_mch_s():
    """The original bug: MCHC was scored against MCH's 27-32 range.

    Both now exist as separate rows (added via additional_ranges.json), so the
    property to hold is that each resolves to ITSELF.
    """
    mchc = LK.classify("MCHC", 33.0, "g/dL")
    assert mchc.matched_test == "MCHC", mchc
    assert mchc.reference_text == "31-36 g/dL", mchc
    assert mchc.status == NORMAL, mchc

    mch = LK.classify("MCH", 28.1, "pg")
    assert mch.matched_test == "MCH", mch
    assert mch.reference_text == "27-33 pg", mch

    # ...and their units keep them apart even if a name resolved loosely.
    assert LK.classify("MCHC", 33.0, "pg").status == NOT_EVALUATED


def test_red_cell_indices_are_now_covered():
    for name, value, unit in (("MCV", 86.2, "fL"), ("MCH", 28.1, "pg"),
                              ("MCHC", 32.6, "g/dL"), ("RDW", 13.4, "%")):
        r = LK.classify(name, value, unit)
        assert r.status == NORMAL, (name, r)


def test_healthy_cbc_reports_no_false_abnormals():
    """The full panel from the bug report, at healthy values."""
    panel = [
        ("Hemoglobin", 14.2, "g/dL"),
        ("WBC Count", 7.2, "x10^3/uL"),
        ("Platelet Count", 250, "x10^3/uL"),
        ("Neutrophils", 55, "%"),
        ("Lymphocytes", 30, "%"),
        ("Eosinophils", 3, "%"),
        ("ABSOLUTE NEUTROPHILS", 4.5, "x10^3/uL"),
        ("ABSOLUTE LYMPHOCYTES", 2.2, "x10^3/uL"),
        ("ABSOLUTE EOSINOPHILS", 0.15, "x10^3/uL"),
    ]
    for name, val, unit in panel:
        r = LK.classify(name, val, unit, sex="M")
        assert r.status == NORMAL, (name, r.status, r.reference_text, r.reason)


# ---------------------------------------------------------------------------
# 2. The unit gate
# ---------------------------------------------------------------------------

def test_cbc_rbc_never_uses_the_urine_microscopy_range():
    """"RBC" names two different tests; the unit decides which.

    The workbook's own RBC row is urine microscopy (0-3 /HPF). A whole-blood
    count of 4.9 x10^6/uL must reach the blood row that additional_ranges.json
    supplies - and must never be scored against 0-3 /HPF, which is what
    produced the original false HIGH.
    """
    blood = LK.classify("RBC", 4.9, "x10^6/uL")
    assert blood.status == NORMAL, blood
    assert blood.matched_test == "RBC Count", blood
    assert blood.reference_unit == "x10^6/µL", blood

    urine = LK.classify("RBC", 2, "/HPF")
    assert urine.reference_text == "0-3 /HPF", urine

    # No unit means we cannot tell the two apart, so neither is used.
    assert LK.classify("RBC", 4.9, None).reason == "MISSING_UNIT"


def test_urine_rbc_still_works():
    r = LK.classify("RBC", 2, "/HPF")
    assert r.status == NORMAL, r
    r = LK.classify("RBC", 25, "/HPF")
    assert r.status == HIGH, r


def test_molar_never_converts_to_mass():
    """Glucose 5.5 mmol/L against a mg/dL range must refuse, not report LOW."""
    r = LK.classify("Glucose", 5.5, "mmol/L")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "UNIT_MISMATCH", r


def test_missing_unit_is_assumed_but_implausible_values_refuse():
    # Plausible: assume the table's unit, flag it.
    r = LK.classify("Glucose", 90, None)
    assert r.status == NORMAL, r
    assert any("assumed" in c for c in r.caveats), r
    # Implausible: 5.5 as mg/dL is 16x below the low bound -> refuse.
    r = LK.classify("Glucose", 0.5, None)
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "SUSPECTED_UNIT_MISMATCH", r


def test_strict_mode_refuses_missing_units():
    strict = RangeLookup(assume_unit_when_missing=False)
    r = strict.classify("Glucose", 90, None)
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "MISSING_UNIT", r


def test_equivalent_units_convert():
    assert units.compatible("10^9/L", "x10^3/µL")
    assert abs(units.convert(7.2, "10^9/L", "x10^3/µL") - 7.2) < 1e-9
    r = LK.classify("WBC Count", 7.2, "10^9/L")
    assert r.status == NORMAL, r


def test_meq_does_not_convert_to_mmol():
    """mEq/L is 2x mmol/L for divalent ions, so the conversion is refused."""
    assert not units.compatible("mEq/L", "mmol/L")


# ---------------------------------------------------------------------------
# 3. Sex-specific ranges
# ---------------------------------------------------------------------------

def test_sex_specific_uses_the_right_bounds():
    r = LK.classify("Hemoglobin", 12.1, "g/dL", sex="F")
    assert r.status == NORMAL and r.context == "F", r
    r = LK.classify("Hemoglobin", 12.1, "g/dL", sex="M")
    assert r.status == LOW and r.context == "M", r


def test_sex_unknown_uses_union_and_says_so():
    r = LK.classify("Hemoglobin", 12.1, "g/dL")
    assert r.status == NORMAL, r
    assert r.reference_low == 11.6 and r.reference_high == 16.6, r
    assert any("sex not provided" in c for c in r.caveats), r


def test_single_sex_row_refuses_when_sex_unknown():
    """'Bioavailable Testosterone 72-235 (M)' has no female range at all."""
    r = LK.classify("Bioavailable Testosterone", 100, "ng/dL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "SEX_REQUIRED", r
    r = LK.classify("Bioavailable Testosterone", 100, "ng/dL", sex="M")
    assert r.status == NORMAL, r


# ---------------------------------------------------------------------------
# 4. The Notes column overrides the range text
# ---------------------------------------------------------------------------

def test_qualitative_rows_are_never_scored():
    """'Length of Urine Collection' reads '24' but is not an analyte."""
    r = LK.classify("Length of Urine Collection", 24, "hr")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "QUALITATIVE_ANALYTE", r


def test_titre_row_is_not_parsed_as_a_number():
    r = LK.classify("Anti-Nuclear Antibody", 80, None)
    assert r.status == NOT_EVALUATED, r


def test_body_fluid_rows_refuse():
    """Body-fluid chemistry is interpreted against a paired serum value."""
    r = LK.classify("Sodium, Ascites", 140, "mmol/L")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "BODY_FLUID_NO_FIXED_RANGE", r

    r = LK.classify("Glucose, Pleural", 80, "mg/dL")
    assert r.status == NOT_EVALUATED, r


def test_csf_glucose_keeps_its_explicit_range():
    """Not every body-fluid row is blocked: CSF glucose has a real 40-70 range
    and an unblocked Notes cell, so it evaluates - with its context surfaced."""
    r = LK.classify("Glucose, CSF", 55, "mg/dL")
    assert r.status == NORMAL, r
    assert any("serum glucose" in c for c in r.caveats), r


def test_neonatal_bilirubin_requires_nomogram():
    r = LK.classify("Bilirubin, Neonatal", 8.0, "mg/dL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "NOMOGRAM_REQUIRED", r


def test_drug_peak_trough_refuses():
    r = LK.classify("Vancomycin", 15, "µg/mL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "AMBIGUOUS_PEAK_TROUGH", r


# ---------------------------------------------------------------------------
# 5. Bounds, fuzzy matching and caveats
# ---------------------------------------------------------------------------

def test_one_sided_bounds():
    r = LK.classify("Triglycerides", 120, "mg/dL")
    assert r.status == NORMAL and r.reference_text == "<150 mg/dL", r
    r = LK.classify("Triglycerides", 180, "mg/dL")
    assert r.status == HIGH, r


def test_expected_zero_reports_present():
    r = LK.classify("Hemoglobin S", 0, "%")
    assert r.status == NORMAL, r
    r = LK.classify("Hemoglobin S", 35, "%")
    assert r.status == PRESENT, r


def test_ocr_typos_resolve():
    for typo in ("Hemoglbin", "Haemoglobin", "HGB", "Hemoglobin "):
        r = LK.classify(typo, 14.0, "g/dL", sex="M")
        assert r.status == NORMAL, (typo, r)


def test_fuzzy_match_is_flagged_as_approximate():
    r = LK.classify("Hemoglbin", 14.0, "g/dL", sex="M")
    assert r.match_tier in ("fuzzy", "exact", "alias"), r
    if r.match_tier == "fuzzy":
        assert any("approximately" in c for c in r.caveats), r


def test_aliases_resolve():
    assert LK.classify("TSH", 2.0, "mIU/L").status == NORMAL
    assert LK.classify("SGPT", 25, "U/L").status == NORMAL
    assert LK.classify("HbA1c", 5.2, "%").status == NORMAL
    assert LK.classify("PSA", 1.2, "ng/mL").status == NORMAL


def test_ast_alias_survives_source_misspelling():
    """The workbook spells it 'Asparate Aminotransferase (AST)'."""
    r = LK.classify("AST", 30, "U/L")
    assert r.status == NORMAL, r


def test_nonsense_name_is_refused():
    r = LK.classify("Zzzz Not A Test", 5, "mg/dL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "TEST_NOT_FOUND", r


def test_no_numeric_value_refuses():
    r = LK.classify("Hemoglobin", "not detected", "g/dL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "NO_NUMERIC_VALUE", r


def test_qualifier_surfaces_as_caveat():
    r = LK.classify("Glycated Hemoglobin", 5.2, "%")
    assert r.status == NORMAL, r
    assert any("non-diabetic" in c for c in r.caveats), r


def test_fasting_note_surfaces_as_caveat():
    r = LK.classify("Glucose", 90, "mg/dL")
    assert r.status == NORMAL, r
    assert any("Fasting" in c for c in r.caveats), r


def test_prompt_line_is_stable():
    r = LK.classify("Hemoglobin", 10.0, "g/dL", sex="F")
    line = r.to_prompt_line()
    assert "status=LOW" in line and "11.6-15" in line, line


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Urine-microscopy collision (regression from the first live deploy)
# ---------------------------------------------------------------------------
# The frontend reported a healthy CBC as "Red Blood Cells 5.37 HIGH" and
# "White Blood Cells 10.1 HIGH". Both names exist in the table only as URINE
# microscopy rows (0-3 and 0-5 /HPF). OCR had dropped the units, the missing
# unit was assumed to be the table's, and 5.37 vs 0-3 is far too close to the
# bound for the implausibility guard to fire.

def test_cbc_counts_without_units_are_refused_not_assumed_to_be_microscopy():
    for name, value in (("Red Blood Cells", 5.37), ("White Blood Cells", 10.1)):
        r = LK.classify(name, value, None)
        assert r.status == NOT_EVALUATED, (name, r)
        assert r.reason == "MISSING_UNIT", (name, r)
        assert any("microscopy" in c for c in r.caveats), r


def test_blood_wbc_resolves_past_the_urine_row():
    """A unit mismatch in the exact tier must not abort resolution."""
    r = LK.classify("White Blood Cells", 10.1, "x10^3/uL")
    assert r.status == NORMAL, r
    assert r.matched_test == "WBC Count", r
    assert r.reference_text == "4.5-11 x10^3/µL", r


def test_urine_microscopy_still_works_when_the_unit_says_so():
    assert LK.classify("White Blood Cells", 3, "/HPF").status == NORMAL
    assert LK.classify("Red Blood Cells", 2, "/HPF").status == NORMAL
    assert LK.classify("White Blood Cells", 40, "/HPF").status == HIGH


def test_cbc_red_cell_count_resolves_to_the_blood_row_not_the_urine_one():
    """`RBC Count` was added, so a CBC red-cell count now has a correct target.

    The urine-microscopy row of the same name must still win when the unit says
    /HPF, and neither may be used when the unit is missing.
    """
    blood = LK.classify("Red Blood Cells", 5.37, "million/uL")
    assert blood.status == NORMAL, blood
    assert blood.matched_test == "RBC Count", blood
    assert blood.reference_unit == "x10^6/µL", blood

    urine = LK.classify("Red Blood Cells", 2, "/HPF")
    assert urine.status == NORMAL and urine.reference_text == "0-3 /HPF", urine

    assert LK.classify("Red Blood Cells", 5.37, None).reason == "MISSING_UNIT"


def test_added_rows_carry_their_source():
    """Every row from additional_ranges.json must cite a named source.

    Scoped to the supplement: the workbook itself has rows saying "previously
    missing" without a Source, which is the vendor's business, not ours.
    """
    import json as _json
    from pathlib import Path as _Path
    here = _Path(__file__).parent
    supplement = _json.loads((here / "additional_ranges.json").read_text(encoding="utf-8"))
    names = {r["Test Name"] for r in supplement["rows"]}
    assert len(names) >= 20, len(names)

    db = _json.loads((here / "reference_db.json").read_text(encoding="utf-8"))
    by_name = {e["test_name"]: e for e in db["entries"]}
    for name in names:
        entry = by_name.get(name)
        if entry is None:
            continue        # skipped because the workbook already had that name
        assert entry["note"] and "Source:" in entry["note"], name
        # A row we added is useless unless it actually classifies.
        assert entry["evaluable"], name


def test_full_cbc_panel_from_the_live_report_has_no_false_abnormals():
    panel = [
        ("Hemoglobin", 15.1, "g/dL"), ("Red Blood Cells", 5.37, None),
        ("Hematocrit", 46.3, "%"), ("MCV", 86.2, "fL"), ("MCHC", 32.6, "g/dL"),
        ("White Blood Cells", 10.1, None), ("Neutrophils", 58, "%"),
        ("Eosinophils", 3, "%"), ("Basophils", 0, "%"), ("Lymphocytes", 34, "%"),
        ("Platelet Count", 275, "x10^3/uL"), ("ESR", 12, "mm/hr"),
    ]
    flagged = [
        (n, LK.classify(n, v, u, sex="M").status)
        for n, v, u in panel
        if LK.classify(n, v, u, sex="M").status in (HIGH, LOW)
    ]
    assert flagged == [], f"healthy panel flagged abnormal: {flagged}"



# ---------------------------------------------------------------------------
# Refusals must be self-consistent and self-explaining
# ---------------------------------------------------------------------------

def test_unit_on_a_unitless_test_is_its_own_reason():
    """`Cholesterol Ratio (Total/HDL)` is a ratio: it has no units.

    A report showing "42 mg/dL" for it has picked up the wrong column, and the
    card must not then advertise "Normal: <5" beside NOT CHECKED.
    """
    r = LK.classify("Cholesterol Ratio (Total/HDL)", 42, "mg/dL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "UNIT_ON_UNITLESS_TEST", r
    # No range is offered for a result we refused to check.
    assert r.reference_text is None, r
    assert r.reference_low is None and r.reference_high is None, r


def test_the_ratio_still_works_without_a_unit():
    r = LK.classify("Cholesterol Ratio (Total/HDL)", 4.2, None)
    assert r.status == NORMAL, r
    assert r.reference_text == "<5", r


def test_ocr_merged_test_names_are_refused_and_explained():
    """OCR joined two table rows into one name.

    At 145 mg/dL the candidates disagree - LDL (<100) is HIGH, total
    cholesterol (<200) is NORMAL - so guessing would be actively harmful.
    """
    r = LK.classify("LDL, Calculated, Cholesterol, Total (Calc.)", 145, "mg/dL")
    assert r.status == NOT_EVALUATED, r
    assert r.reason == "AMBIGUOUS_MATCH", r
    joined = " ".join(r.caveats)
    assert "Cholesterol, LDL, Calculated" in joined, r.caveats
    assert "read as one" in joined, r.caveats


def test_every_reason_code_has_plain_english():
    """The generator is banned from printing codes, so it must be given words."""
    from app.reference_ranges.range_lookup import REASON_TEXT, reason_text
    seen = set()
    for name, value, unit in (
        ("Cholesterol Ratio (Total/HDL)", 42, "mg/dL"),
        ("LDL, Calculated, Cholesterol, Total (Calc.)", 145, "mg/dL"),
        ("Red Blood Cells", 5.37, None),
        ("Glucose", 5.5, "mmol/L"),
        ("Sodium, Ascites", 140, "mmol/L"),
        ("Vancomycin", 15, "ug/mL"),
        ("Zzzz Not A Test", 5, "mg/dL"),
    ):
        r = LK.classify(name, value, unit)
        assert r.status == NOT_EVALUATED, (name, r)
        seen.add(r.reason)
        assert r.reason in REASON_TEXT, r.reason
        assert "_" not in reason_text(r.reason), r.reason   # a sentence, not a code
        assert r.reason not in r.to_prompt_line(), r.to_prompt_line()
    assert len(seen) >= 5, seen


def _run() -> int:
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}\n        {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}\n        {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
