"""Conservative checks on numeric ECG prose, outside the frozen DSP modules.

Numbers must match supplied values at their displayed rounding precision and
in compatible units. Named metrics cannot borrow another metric's value.
This is a numeric guard, not a proof of clinical or semantic correctness.
"""

import math
import re
from dataclasses import dataclass
from decimal import Decimal


SECTIONS = ("Summary", "What the numbers mean", "Possible findings", "Limitations", "When to see a doctor")
NUMBER_PATTERN = r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
NUMBERS = re.compile(NUMBER_PATTERN)
UNIT_PATTERN = (r"(?:beats?\s*(?:per\s*minute|/\s*min)|bpm|milliseconds?|msec|ms|"
                r"seconds?|secs?|s\b|hertz|hz|decibels?|db|millivolts?|mv|"
                r"percent|%|beats?|pairs?|px/mm|mm/s|mm/mv)")
UNITS = re.compile(r"^\s*(?:[-–]\s*)?(" + UNIT_PATTERN + r")(?![\w/])", re.I)
RANGE_UNIT = re.compile(r"^\s*(?:to|[-–])\s*" + NUMBER_PATTERN + r"\s*(" + UNIT_PATTERN + r")(?![\w/])", re.I)
THRESHOLD_CUE = re.compile(r"\b(?:threshold|cutoff|cut-off|below|above|exceeds?|less than|more than|greater than|outside)\b|[<>]", re.I)
UNMEASURED = re.compile(r"\b(?:PR(?:\s+interval)?|QTc?(?:\s+interval)?|ST(?:\s+(?:segment|elevation|depression))?|"
                        r"QRS[-\s]+(?:width|duration)|(?:electrical\s+)?axis)\b", re.I)
UNMEASURED_ASSERTION = re.compile(r"\b(?:normal|abnormal|prolonged|shortened|elevated|depressed|widened|narrow|deviated)\b", re.I)
NEGATION = re.compile(r"\b(?:no|not|never|cannot|unavailable|unmeasured|without)\b", re.I)
MEASUREMENT_ABSENCE = re.compile(r"\b(?:no|unavailable|unmeasured|without)\b|"
                                 r"\bnot\s+(?:measured|assessed|provided|available|evaluated)\b|"
                                 r"\bcannot\s+(?:measure|assess|determine|evaluate)\b", re.I)
DISEASE_PROBABILITY = re.compile(r"\b(?:chance|probability|risk)\b", re.I)
DEFINITE_CONDITION = re.compile(r"\b(?:you\s+have|the\s+patient\s+has|this\s+confirms)\s+"
                                r"(?:AFib|atrial\s+fibrillation|bradycardia|tachycardia|arrhythmia)\b", re.I)

# Specific labels take precedence over generic HR/RR prose. Units provide the
# fallback for sentences such as 'rates from 71.8 to 72.1 bpm'.
LABELS = (
    ("hr_mean", r"\b(?:mean|average)\s+(?:heart\s*rate|HR)\b|\b(?:heart\s*rate|HR)\s+(?:mean|average)\b"),
    ("hr_min", r"\b(?:minimum|min|lowest)\s+(?:heart\s*rate|HR|rate)\b"),
    ("hr_max", r"\b(?:maximum|max|highest)\s+(?:heart\s*rate|HR|rate)\b"),
    ("mean_rr", r"\bmean\s+RR\b|\bRR\s+mean\b"),
    ("sdnn", r"\bSDNN\b"), ("rmssd", r"\bRMSSD\b"), ("pnn50", r"\bpNN50\b"),
    ("rr_cv", r"\b(?:RR\s+(?:CV|coefficient\s+of\s+variation)|CV|coefficient\s+of\s+variation)\b"),
    ("snr", r"\b(?:SNR|signal[-\s]+to[-\s]+noise(?:\s+ratio)?)\b"),
    ("confidence", r"\bconfidence(?:\s+badge)?\b"),
    ("beat_count", r"\bbeat\s+count\b"), ("duration", r"\bduration\b"),
    ("fs", r"\b(?:sampling\s+(?:rate|frequency)|sampled\s+at|fs)\b"),
    ("rr", r"\bRR\s+intervals?\b"),
    ("r_time", r"\bR[-\s]+peak\s+times?\b"),
    ("signal_range", r"\b(?:signal|voltage)\s+range\b"),
)
LABEL_REGEX = [(metric, re.compile(pattern, re.I)) for metric, pattern in LABELS]


@dataclass(frozen=True)
class AllowedNumber:
    value: float
    unit: str
    metric: str
    kind: str = "measurement"


def canonical_unit(unit: str) -> str:
    value = re.sub(r"\s+", "", unit.lower())
    if value == "bpm" or "minute" in value or "/min" in value:
        return "bpm"
    if value in ("ms", "msec", "millisecond", "milliseconds"):
        return "ms"
    if value in ("s", "sec", "secs", "second", "seconds"):
        return "s"
    if value in ("hz", "hertz"):
        return "hz"
    if value in ("db", "decibel", "decibels"):
        return "db"
    if value in ("mv", "millivolt", "millivolts"):
        return "mv"
    if value in ("%", "percent"):
        return "percent"
    if value.startswith("beat"):
        return "beats"
    if value.startswith("pair"):
        return "pairs"
    return value


def token_unit(text: str, end: int) -> str:
    suffix = text[end:]
    match = UNITS.match(suffix) or RANGE_UNIT.match(suffix)
    return canonical_unit(match.group(1)) if match else ""


def local_clause(text: str, start: int, end: int) -> tuple[str, int]:
    # Decimal points / thousands separators are not sentence boundaries.
    boundaries = [match.start() for match in re.finditer(r"[;!?\n]|(?<!\d)[.,]|[.,](?!\d)", text)]
    left = max([position + 1 for position in boundaries if position < start], default=0)
    right = min([position for position in boundaries if position >= end], default=len(text))
    return text[left:right], start - left


def labelled_metric(clause: str, number_start: int) -> str | None:
    labels = [(metric, match) for metric, regex in LABEL_REGEX for match in regex.finditer(clause)]
    labels = [(metric, match) for metric, match in labels if metric != "rr"
              or not any(other_metric == "mean_rr" and other.start() < match.end()
                         and match.start() < other.end() for other_metric, other in labels)]
    before = [(metric, match) for metric, match in labels if match.end() <= number_start
              and not NUMBERS.search(clause[match.end():number_start])]
    if before:
        return max(before, key=lambda item: item[1].end())[0]
    current = NUMBERS.match(clause, number_start)
    number_end = current.end() if current else number_start
    after = []
    for metric, match in labels:
        if match.start() < number_end:
            continue
        between = clause[number_end:match.start()]
        unit = UNITS.match(between)
        remainder = between[unit.end():] if unit else between
        if re.fullmatch(r"[\s:()=\-]*(?:(?:of|for|is|was)\s*)?", remainder):
            after.append((metric, match))
    return min(after, key=lambda item: item[1].start())[0] if after else None


def allowed_numbers(payload: dict) -> list[AllowedNumber]:
    numbers = []

    def add(value, unit, metric, kind="measurement"):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            numbers.append(AllowedNumber(float(value), unit, metric, kind))

    measured = payload.get("measurements", {})
    fields = {"hr_mean_bpm": ("bpm", "hr_mean"), "hr_min_bpm": ("bpm", "hr_min"),
              "hr_max_bpm": ("bpm", "hr_max"), "mean_rr_ms": ("ms", "mean_rr"),
              "sdnn_ms": ("ms", "sdnn"), "rmssd_ms": ("ms", "rmssd"),
              "pnn50_percent": ("percent", "pnn50"), "rr_cv": ("ratio", "rr_cv"),
              "beat_count": ("beats", "beat_count"), "duration_s": ("s", "duration"),
              "fs_hz": ("hz", "fs")}
    for field, (unit, metric) in fields.items():
        add(measured.get(field), unit, metric)
    for value in measured.get("rr_intervals_ms", []):
        add(value, "ms", "rr")
    for value in measured.get("r_peak_times_s", []):
        add(value, "s", "r_time")
    quality = payload.get("quality", {})
    for field, unit, metric in (("snr_db", "db", "snr"), ("beat_count", "beats", "beat_count"),
                                ("rr_plausible_fraction", "ratio", "rr_plausible"),
                                ("signal_range_mv", "mv", "signal_range")):
        add(quality.get(field), unit, metric)
    definitions = measured.get("definitions", {})
    definition_fields = {"pnn50_difference_threshold_ms": ("ms", "pnn50"),
                         "bradycardia_bpm": ("bpm", "hr"), "tachycardia_bpm": ("bpm", "hr"),
                         "irregular_rr_cv": ("ratio", "rr_cv"),
                         "premature_rr_ratio": ("ratio", "rr_ratio"),
                         "compensatory_rr_ratio": ("ratio", "rr_ratio"),
                         "minimum_quality_beats": ("beats", "beat_count"),
                         "minimum_snr_db": ("db", "snr"),
                         "plausible_rr_min_s": ("s", "rr"), "plausible_rr_max_s": ("s", "rr")}
    for field, (unit, metric) in definition_fields.items():
        add(definitions.get(field), unit, metric, "definition" if field.startswith("pnn50") else "threshold")
    literals = list(payload.get("warnings", [])) + list(quality.get("reasons", []))
    for finding in payload.get("findings", []):
        add(finding.get("confidence"), "ratio", "confidence")
        literals.extend(finding.get("evidence", []))
    for literal in literals:
        if not isinstance(literal, str):
            continue
        for token in NUMBERS.finditer(literal):
            clause, position = local_clause(literal, token.start(), token.end())
            add(float(token.group().replace(",", "")), token_unit(literal, token.end()),
                labelled_metric(clause, position) or "literal", "literal")
    return numbers


def compatible_value(source: AllowedNumber, unit: str) -> float | None:
    if unit == source.unit or not unit and source.unit == "ratio":
        return source.value
    if source.unit == "ms" and unit == "s":
        return source.value / 1000
    if source.unit == "s" and unit == "ms":
        return source.value * 1000
    if source.unit == "ratio" and unit == "percent":
        return source.value * 100
    if source.unit == "percent" and not unit:
        return source.value / 100
    if not unit:
        return source.value
    return None


def matches_rounding(number: str, value: float) -> bool:
    displayed = Decimal(number.replace(",", ""))
    tolerance = Decimal("0.5").scaleb(displayed.as_tuple().exponent)
    return abs(Decimal(str(value)) - displayed) <= tolerance + Decimal("1e-9")


def check_explanation(explanation: dict, payload: dict) -> dict:
    """Return audit metadata; rejected prose never reaches the API response.

    Explicit numeric tokens are checked, including rounded values, seconds/ms
    and fraction/percent conversions. Written-out numbers and arbitrary medical
    prose are outside this guard's scope and still require clinician review.
    """
    if not isinstance(explanation, dict) or any(not isinstance(explanation.get(section), str)
                                               or not explanation[section].strip() for section in SECTIONS):
        return {"status": "rejected", "checked_numeric_claims": 0, "reasons": ["invalid_sections"]}
    sources = allowed_numbers(payload)
    checked = 0
    reasons = []
    for section in SECTIONS:
        text = explanation[section]
        if DEFINITE_CONDITION.search(text):
            reasons.append(f"{section}:definite_condition_claim")
        for term in UNMEASURED.finditer(text):
            clause, _ = local_clause(text, term.start(), term.end())
            if not MEASUREMENT_ABSENCE.search(clause) and (NUMBERS.search(clause) or UNMEASURED_ASSERTION.search(clause)):
                reasons.append(f"{section}:unavailable_waveform_measurement")
        for token in NUMBERS.finditer(text):
            checked += 1
            unit = token_unit(text, token.end())
            clause, position = local_clause(text, token.start(), token.end())
            metric = labelled_metric(clause, position)
            threshold = bool(THRESHOLD_CUE.search(clause))
            if unit == "percent" and DISEASE_PROBABILITY.search(clause) and not NEGATION.search(clause):
                reasons.append(f"{section}:unsupported_disease_probability")
            candidates = sources
            if metric:
                candidates = [source for source in sources if source.metric == metric
                              or metric == "rr" and source.metric == "mean_rr"
                              or threshold and source.kind == "threshold"
                              and (source.metric == "hr" and metric.startswith("hr")
                                   or source.metric == metric)]
            if not unit and not metric:
                candidates = [source for source in sources if source.kind == "literal" and not source.unit]
            # Definitions and screening thresholds must not become observations.
            candidates = [source for source in candidates if source.kind != "threshold" or threshold]
            if not any(value is not None and matches_rounding(token.group(), value)
                       for source in candidates if (value := compatible_value(source, unit)) is not None):
                reasons.append(f"{section}:unsupported_numeric_claim")
    return {"status": "rejected" if reasons else "passed", "checked_numeric_claims": checked,
            "method": "metric-and-unit-aware numeric matching with displayed-precision rounding",
            "reasons": list(dict.fromkeys(reasons))}
