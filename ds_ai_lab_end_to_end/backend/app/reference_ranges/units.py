"""Unit canonicalisation and conversion for lab reference ranges.

The single job of this module is to answer one question safely:

    "Is the unit on the patient's report the same physical quantity as the unit
     on the reference-range row, and if so what is the scale factor?"

Design rule: this module NEVER guesses. Two units either belong to the same
declared equivalence group (and therefore have an exact scale factor between
them), or they are incompatible and the caller must refuse to classify. In
particular, molar units (mmol/L) are deliberately NOT convertible to mass units
(mg/dL): that conversion needs the analyte's molar mass, which this table does
not carry. Refusing is correct; inventing a factor is how a pipeline tells a
healthy patient they are sick.

The `RBC` row is the motivating example. The table's `RBC` is urine microscopy
(0-3 /HPF). A CBC report's RBC is ~4.9 x10^6/uL. Those units live in different
groups, so classification is refused rather than reporting a wild HIGH.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

# Characters that mean "micro" across the encodings this project has seen.
_MICRO_CHARS = {
    "µ",  # MICRO SIGN
    "μ",  # GREEK SMALL LETTER MU
}


def normalize_unit(raw: str | None) -> str:
    """Fold a unit string to a comparable key.

    Lowercases, maps micro-sign variants to 'u', removes spaces, and rewrites
    the many spellings of scientific notation to a single `10^N` form.
    """
    if raw is None:
        return ""
    s = unicodedata.normalize("NFKC", str(raw)).strip()
    if not s or s.lower() in {"none", "nan", "-", "–", "—"}:
        return ""

    for ch in _MICRO_CHARS:
        s = s.replace(ch, "u")

    # Repair superscripts that OCR mangles. A lab prints 10^9/L as "10\u2079/L";
    # the exponent comes back as a degree sign, a caret-less digit run, or a
    # Unicode superscript. Left alone these become unknown units and the result
    # is refused even though its range is in the table - three of four "not
    # checked" cards on one real report were exactly this.
    s = s.translate(str.maketrans("\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079",
                                  "0123456789"))
    s = s.replace("\u00b0", "9")        # 10°/L  -> 10 9 /L: ° is a misread 9
    s = s.lower()
    s = s.replace("×", "x")  # MULTIPLICATION SIGN
    s = re.sub(r"\s+", "", s)

    # x10^3 / 10e3 / 10*3 / k  ->  10^3
    s = re.sub(r"^x?10[\^\*e]?(\d+)", r"10^\1", s)
    # thou/K prefixes used by analysers: K/uL, thou/uL
    s = re.sub(r"^(k|thou|thousand)/", "10^3/", s)
    s = re.sub(r"^(m|mill|million)/(ul|mcl)$", r"10^6/ul", s)

    s = s.replace("mcl", "ul").replace("mcg", "ug")
    # Notations common on Indian and older US reports. "cumm" is a cubic
    # millimetre, which is exactly a microlitre; "gm" is just "g" spelled out.
    # Without these, Hemoglobin in gm/dL and a WBC count in /cumm are refused
    # even though their ranges are right there in the table.
    s = re.sub(r"\bcu\.?\s*mm\b", "ul", s)
    s = s.replace("cumm", "ul").replace("cmm", "ul").replace("mm3", "ul")
    s = re.sub(r"^gm(?=/)", "g", s)
    s = re.sub(r"^(million|mill|mil)(?=/)", "10^6", s)
    s = re.sub(r"^lakhs?(?=/)", "10^5", s)
    s = s.replace("litre", "l").replace("liter", "l")
    s = s.replace("cells/", "/").replace("cell/", "/")
    s = s.replace("percent", "%")
    return s


# --------------------------------------------------------------------------
# Equivalence groups
# --------------------------------------------------------------------------
# Each group maps a normalised unit -> multiplicative factor to that group's
# base unit. value_in_base = value * factor.
#
# Groups are closed: conversion is only ever performed within a group.

_GROUPS: dict[str, dict[str, float]] = {
    # ---- cell concentration. base: 10^3/uL  (== 10^9/L) ----
    "cell_conc": {
        "10^3/ul": 1.0,
        "10^9/l": 1.0,
        "10^6/ul": 1000.0,
        "10^12/l": 1000.0,
        "/ul": 0.001,
        "/l": 1e-9,
        "/mm3": 0.001,
        "/cmm": 0.001,
        "10^6/l": 1e-3,
        "10^5/ul": 100.0,      # lakhs/cumm, used for platelet counts in India
    },
    # ---- mass concentration. base: mg/dl ----
    "mass_conc": {
        "mg/dl": 1.0,
        "g/dl": 1000.0,
        "g/l": 100.0,
        "mg/l": 0.1,
        "ug/ml": 0.1,
        "ug/dl": 1e-3,
        "ng/ml": 1e-4,
        "ng/dl": 1e-6,
        "pg/ml": 1e-7,
        "ug/l": 1e-4,
    },
    # ---- amount concentration (molar). base: mmol/l. NEVER crosses to mass. ----
    "molar_conc": {
        "mmol/l": 1.0,
        "umol/l": 1e-3,
        "nmol/l": 1e-6,
        "pmol/l": 1e-9,
        "mol/l": 1000.0,
    },
    # mEq/L is charge-equivalents, not moles: it equals mmol/L only for
    # monovalent ions and is 2x mmol/L for divalent ones (Ca, Mg). Since the
    # factor depends on the analyte, mEq/L gets its own closed group and simply
    # never converts to mmol/L.
    "equiv_conc": {"meq/l": 1.0},
    # ---- enzyme activity. base: u/l ----
    "activity": {
        "u/l": 1.0,
        "iu/l": 1.0,
        "u/ml": 1000.0,
        "iu/ml": 1000.0,
        "miu/l": 1e-3,
        "uiu/ml": 1e-3,
        "miu/ml": 1.0,
    },
    # ---- 24-hour mass excretion. base: mg/24hr ----
    "mass_per_day": {
        "mg/24hr": 1.0,
        "g/24hr": 1000.0,
        "ug/24hr": 1e-3,
    },
    # ---- 24-hour molar excretion. separate from mass, same reasoning as above ----
    "molar_per_day": {
        "mmol/24hr": 1.0,
        "meq/24hr": 1.0,
        "umol/24hr": 1e-3,
    },
    # ---- fraction ----
    "fraction": {
        "%": 1.0,
        "%oftotal": 1.0,
    },
    # ---- microscopy density. /LPF is a different magnification and is
    # deliberately absent so it can never be compared against /HPF. ----
    "per_hpf": {
        "/hpf": 1.0,
    },
    # ---- misc single-member groups (comparable only to themselves) ----
    "per_100_wbc": {"/100wbc": 1.0},
    "time": {"sec": 1.0, "s": 1.0, "min": 60.0, "hr": 3600.0},
    "pressure": {"mmhg": 1.0, "kpa": 7.50062},
    "osmolality": {"mosm/kg": 1.0},
    "volume_cell": {"fl": 1.0},
    "mass_cell": {"pg": 1.0},
    "clearance": {"ml/min": 1.0, "l/min": 1000.0},
    # Sedimentation rate. Its own group: nothing else is measured in mm/hr.
    "sed_rate": {"mm/hr": 1.0, "mm/h": 1.0, "mm/1hr": 1.0, "mm/hour": 1.0},
    # eGFR is body-surface-normalised, so it is deliberately NOT interchangeable
    # with the raw `mL/min` of a measured creatinine clearance.
    "gfr": {"ml/min/1.73m2": 1.0, "ml/min/1.73sqm": 1.0, "ml/min/1.73": 1.0},
    "mom": {"mom": 1.0},
    "titer": {"titer": 1.0},
    "ratio_mass": {"mg/g": 1.0, "mg/mg": 1000.0, "ug/mg": 1.0},
    "viscosity": {"centipoise": 1.0},
    "renin": {"ng/ml/hr": 1.0},
    "volume_per_day": {"ml/24hr": 1.0},
    "excretion_activity": {"u/hr": 1.0},
}

# Units that are assay-defined and only ever comparable to an identical string.
_OPAQUE = {
    "bethesdaunits",
    "gplu/ml",
    "mplu/ml",
    "ug/mlfeu",
    "mgsurfactant/galbumin",
}

# Reverse index: normalised unit -> (group name, factor to base)
_UNIT_INDEX: dict[str, tuple[str, float]] = {}
for _gname, _members in _GROUPS.items():
    for _u, _f in _members.items():
        _UNIT_INDEX[_u] = (_gname, float(_f))
for _u in _OPAQUE:
    _UNIT_INDEX[_u] = (f"opaque:{_u}", 1.0)


class UnitError(Exception):
    """Raised when a conversion is requested that this module refuses to make."""


def unit_group(raw: str | None) -> str | None:
    """Return the equivalence-group name for a unit, or None if unrecognised."""
    key = normalize_unit(raw)
    if not key:
        return None
    hit = _UNIT_INDEX.get(key)
    return hit[0] if hit else None


def is_dimensionless(raw: str | None) -> bool:
    """True when the row carries no unit at all (score, index, ratio, count)."""
    return normalize_unit(raw) == ""


def compatible(unit_a: str | None, unit_b: str | None) -> bool:
    """True when both units are recognised and share an equivalence group."""
    ga, gb = unit_group(unit_a), unit_group(unit_b)
    return ga is not None and ga == gb


def convert(value: float, from_unit: str | None, to_unit: str | None) -> float:
    """Convert `value` from one unit to another within the same group.

    Raises UnitError when either unit is unknown or they are in different
    groups. Callers are expected to treat UnitError as "cannot evaluate",
    never as "assume they match".
    """
    ka, kb = normalize_unit(from_unit), normalize_unit(to_unit)
    if ka == kb:
        return value

    ha, hb = _UNIT_INDEX.get(ka), _UNIT_INDEX.get(kb)
    if ha is None:
        raise UnitError(f"unrecognised unit: {from_unit!r}")
    if hb is None:
        raise UnitError(f"unrecognised unit: {to_unit!r}")
    if ha[0] != hb[0]:
        raise UnitError(
            f"incompatible units: {from_unit!r} ({ha[0]}) vs {to_unit!r} ({hb[0]})"
        )
    return value * ha[1] / hb[1]
