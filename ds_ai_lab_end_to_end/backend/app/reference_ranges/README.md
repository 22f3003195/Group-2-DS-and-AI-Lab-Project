# Reference ranges — deterministic grounding for lab results

Converts `lab_test_reference_ranges_1.xlsx` (653 rows) into a normalised JSON
database and exposes a lookup that decides HIGH / LOW / NORMAL **by arithmetic**,
so BioMistral explains a status instead of guessing one.

```python
from code.reference_ranges.range_lookup import RangeLookup, build_grounding_block

lk = RangeLookup()
r  = lk.classify("Hemoglbin", 12.1, unit="g/dL", sex="F")

r.status          # 'NORMAL'
r.matched_test    # 'Hemoglobin'
r.reference_text  # '11.6-15 g/dL'
r.caveats         # ["test name matched approximately: 'Hemoglbin' -> 'Hemoglobin'"]

print(build_grounding_block(lk.classify_many(lab_results, sex="F")))
```

## Why it is split in two

Resolving a test **name** is a search problem — OCR yields `Hemoglbin`, `HGB`,
`Haemoglobin`. Comparing a **value** to a range is arithmetic. Mixing them is
what produced the original bug, so they are separate stages and no similarity
score ever reaches the comparison.

| tier | mechanism | when |
|---|---|---|
| 1 | exact normalised name | always |
| 2 | curated alias table (`TSH`, `SGPT`, `HbA1c`, …) | always |
| 3 | `rapidfuzz`, threshold 88, singularised tokens | always |
| 4 | Chroma + ONNX MiniLM | **opt-in**, see below |

Then: unit compatibility gate → sex-specific bound selection → `<` / `>`.

## Files

| file | role |
|---|---|
| `build_reference_db.py` | xlsx → `reference_db.json`, parses every bound once |
| `range_lookup.py` | tiered resolver + `classify()` + prompt block |
| `units.py` | unit equivalence groups and refusals |
| `calibrate.py` | measures the resolver's operating point |
| `test_range_lookup.py` | 32 tests, incl. the original bug regressions |

Rebuild after editing the workbook:

```bash
python -m code.reference_ranges.build_reference_db --report
python code/reference_ranges/test_range_lookup.py
```

## What the database contains

**333 of 653 rows (51%) are numerically evaluable.** The rest cannot be scored,
and that is a property of the source data, not a parser limitation:

| reason | rows |
|---|---|
| `QUALITATIVE_ANALYTE` | 179 |
| `BODY_FLUID_NO_FIXED_RANGE` | 114 |
| `NO_STANDARDIZED_RANGE` | 13 |
| `AMBIGUOUS_PEAK_TROUGH` | 4 |
| everything else | 13 |

### The Notes column overrides the range text

The workbook's `Read Me` states that qualitative, body-fluid and
clinically-interpreted rows have no fixed normal range. Only **12 distinct**
Notes values exist, so they are handled exhaustively rather than heuristically
(`NOTE_POLICY` in `build_reference_db.py`), and a `BLOCK` note beats a
successful parse. This matters because several blocked rows *do* contain
digits:

- `Anti-Nuclear Antibody` → `Negative (<1:40)` — the number is an assay titre
- `Elliptocytes` → `None/Rare (<1–2%)`
- `Length of Urine Collection` → `24` — a collection duration, not an analyte
- `Bilirubin, Neonatal` → `1.0–12.0 (age-dependent)` — needs the Bhutani nomogram

A parser trusting the range column alone would happily compare against all four.

## Safety properties

Every one of these is pinned by a test.

**Units are a hard gate, not a hint.** The table's only `RBC` row is *urine
microscopy*, `0–3 /HPF`. A CBC's `RBC 4.9 x10^6/µL` is refused rather than
reported as wildly HIGH. Molar never converts to mass (that needs a molar mass
the table lacks), and `mEq/L` never converts to `mmol/L` (it is 2× for divalent
ions).

**Missing units are assumed, then sanity-checked.** OCR unit accuracy is ~22%,
so refusing every unitless value would make the pipeline useless. Instead the
table's unit is assumed, a caveat is attached, and the value is range-checked:
`Glucose 5.5` (i.e. mmol/L read as mg/dL) is 16× below the low bound, so it
returns `SUSPECTED_UNIT_MISMATCH` instead of a terrifying LOW. Pass
`assume_unit_when_missing=False` for strict mode.

**Sex-specific ranges are real and common.** 20 rows, covering Hemoglobin,
Hematocrit, Ferritin, Iron, Testosterone and Uric Acid. With `sex=` given, the
correct bounds are used; without it, the union is used *and a caveat says so*.
Rows giving only one sex (`Bioavailable Testosterone 72–235 (M)`) return
`SEX_REQUIRED` rather than applying a male range to a female patient.

**Absent tests say so.** `MCV`, `MCH`, `MCHC`, `RDW`, `ESR`, `eGFR`, serum
`BUN`, `PT` and `APTT` are genuinely not in this workbook. They return
`TEST_NOT_IN_REFERENCE_TABLE` instead of being dragged onto a neighbouring row.

## Calibration

`python -m code.reference_ranges.calibrate`, 200 sampled rows, resolver given
the correct unit:

| corruption | correct | wrong | refused |
|---|---|---|---|
| clean | 100.0% | 0.0% | 0.0% |
| uppercased | 100.0% | 0.0% | 0.0% |
| dropped char | 90.5% | 2.0% | 7.5% |
| transposed chars | 77.5% | 4.5% | 18.0% |
| `Serum … Level` padding | 92.5% | 0.0% | 7.5% |

The fuzzy threshold of 88 is measured, not guessed. Wrong-match rate is flat
(~3.8%) from threshold 70 to 96, so raising it buys no safety — but
out-of-vocabulary behaviour sets a hard floor:

| threshold | out-of-table names correctly refused |
|---|---|
| 80 | 91.3% |
| 84 | 91.3% |
| **86–90** | **100%** |

Below 86, `Procalcitonin` resolves to `Prolactin` and `Collection Date` to
`Length of Urine Collection`. The boundary sits at ~85.5, so 88 keeps a margin.

### Why the Chroma tier is off by default

It is implemented (`RangeLookup(vector_enabled=True)`, index in
`chroma_index/`), but measurement argued against making it the default. On
transposed names it converted 2pp of safe refusals into **0.5pp more correct
and 1.5pp more wrong** answers, at ~13× the latency. Nor is a better threshold
available: `Bad cholesterol` → `Cholesterol, Pleural` scores 0.67, *above* the
0.63 of the one real win (`Vitamin B-12 level` → `Vitamin B12`).

Short clinical names are simply the wrong shape for sentence embeddings —
`Hemoglobin`, `Hemoglobin F` and `Fetal Hemoglobin` are near-identical vectors
with different reference ranges. The index remains useful for **patient-facing
chat retrieval**, where a near-miss costs nothing; it is name→range resolution
that needs exactness.

## Known caveats

- Ranges are broad published adult values (Mayo/ARUP), **not lab-validated**.
  The `Read Me` disclaimer is carried into `reference_db.json` as `disclaimer`.
- Paediatric and pregnancy ranges are absent; adult defaults are what you get.
- `pandas` is deliberately unused: this environment has a Python-2-era
  `xlrd 0.7.1` whose import raises `SyntaxError`, and `pandas.read_excel`
  imports it unconditionally. `openpyxl` is used directly.
