"""CPU-only tests for the grounded pipeline. No GPU, no model downloads.

Run:  cd backend && python test_grounding.py
      cd backend && python -m pytest test_grounding.py -q

Everything here is a regression test for a defect that shipped:

  F1   substring range matching reported four healthy CBC values as HIGH
  F2   the summary prompt had no instructions at all
  F3   report context never reached the chat (gr.State is not an API input)
  F3b  the UI's greeting made every chat generation throw and fall back
  F5   patient surnames from one sample PDF were hardcoded into a skip list
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MEDREPORT_STUB_MODELS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.pipeline.ner import NERProcessor, REPORT_FURNITURE          # noqa: E402
from app.pipeline.pipeline import extract_patient_sex, MedicalReportPipeline  # noqa: E402
from app.pipeline.llm import (                                        # noqa: E402
    build_chat_conversation,
    build_summary_prompt,
    enforce_alternation,
    generate_fallback_chat_response,
    normalize_history,
)
from app.pipeline.readability import (                                # noqa: E402
    flesch_kincaid_grade,
    numbers_preserved,
    revise_to_grade,
)


def _panel(rows):
    """Turn (test, value, unit) tuples into the BIO token stream NER emits."""
    tokens, tags = [], []
    for test, value, unit in rows:
        words = test.split()
        tokens.append(words[0]); tags.append('B-TEST')
        for w in words[1:]:
            tokens.append(w); tags.append('I-TEST')
        tokens.append(value); tags.append('B-VALUE')
        if unit:
            tokens.append(unit); tags.append('B-UNIT')
    return tokens, tags


# ---------------------------------------------------------------------------
# F1 - the regression that started all this
# ---------------------------------------------------------------------------

def test_healthy_cbc_has_no_false_abnormals():
    proc = NERProcessor(patient_sex='M')
    tokens, tags = _panel([
        ('MCHC', '33.0', 'g/dL'),
        ('ABSOLUTE NEUTROPHILS', '4500', 'cells/mcL'),
        ('ABSOLUTE LYMPHOCYTES', '2200', 'cells/mcL'),
        ('ABSOLUTE EOSINOPHILS', '150', 'cells/mcL'),
        ('HEMOGLOBIN', '14.2', 'g/dL'),
        ('PLATELET COUNT', '250', '10^9/L'),
    ])
    results = proc.process(tokens, tags)['lab_results']
    flagged = [r for r in results if r['status'] in ('HIGH', 'LOW')]
    assert flagged == [], f"healthy panel flagged as abnormal: {flagged}"


def test_absolute_counts_convert_rather_than_compare_to_percentages():
    proc = NERProcessor()
    tokens, tags = _panel([('ABSOLUTE NEUTROPHILS', '4500', 'cells/mcL')])
    r = proc.process(tokens, tags)['lab_results'][0]
    assert r['status'] == 'NORMAL', r
    assert r['unit'] == 'x10^3/µL', r
    assert r['value'] == '4.5', r          # 4500 /uL == 4.5 x10^3/uL


def test_mchc_uses_its_own_range_not_mch_s():
    """MCHC and MCH are now separate rows; each must resolve to itself."""
    proc = NERProcessor()
    r = proc.process(*_panel([('MCHC', '33.0', 'g/dL')]))['lab_results'][0]
    assert r['test_name'] == 'MCHC', r
    assert r['status'] == 'NORMAL', r
    assert (r['ref_min'], r['ref_max']) == (31.0, 36.0), r


def test_cbc_rbc_is_not_scored_against_urine_microscopy():
    """A blood RBC count reaches the blood row, never the 0-3 /HPF urine row."""
    proc = NERProcessor()
    r = proc.process(*_panel([('RBC', '4.9', 'x10^6/uL')]))['lab_results'][0]
    assert r['test_name'] == 'RBC Count', r
    assert r['status'] == 'NORMAL', r
    assert (r['ref_min'], r['ref_max']) != (0.0, 3.0), r     # not the urine row

    # Without a unit the two cannot be told apart, so nothing is claimed.
    r2 = proc.process(*_panel([('RBC', '4.9', '')]))['lab_results']
    assert r2 == [] or r2[0]['status'] == 'UNKNOWN', r2


# ---------------------------------------------------------------------------
# F5 - no patient names in the filter
# ---------------------------------------------------------------------------

def test_no_patient_or_lab_names_are_hardcoded():
    leaked = {'YASH', 'PATEL', 'HIREN', 'SHAH', 'DRLOGY', 'MUMBAI'}
    assert not (REPORT_FURNITURE & leaked), REPORT_FURNITURE & leaked


def test_real_patient_named_patel_keeps_their_results():
    proc = NERProcessor()
    tokens, tags = _panel([('PATEL', '14.2', 'g/dL'), ('HEMOGLOBIN', '14.2', 'g/dL')])
    results = proc.process(tokens, tags)['lab_results']
    assert any(r['test_name'] == 'Hemoglobin' for r in results)


def test_furniture_without_a_unit_is_dropped():
    proc = NERProcessor()
    tokens, tags = _panel([('Sample Collected On', '2023', '')])
    assert proc.process(tokens, tags)['lab_results'] == []


# ---------------------------------------------------------------------------
# Sex-specific ranges
# ---------------------------------------------------------------------------

def test_patient_sex_is_read_from_the_report_header():
    assert extract_patient_sex("Patient Name : A B\nSex : Male\nAge : 21") == 'M'
    assert extract_patient_sex("Name: X   Gender: Female") == 'F'
    assert extract_patient_sex("no demographics here") is None


def test_sex_changes_the_hemoglobin_verdict():
    tokens, tags = _panel([('HEMOGLOBIN', '12.1', 'g/dL')])
    male = NERProcessor(patient_sex='M').process(tokens, tags)['lab_results'][0]
    female = NERProcessor(patient_sex='F').process(tokens, tags)['lab_results'][0]
    assert male['status'] == 'LOW', male
    assert female['status'] == 'NORMAL', female


def test_unknown_sex_widens_the_range_and_says_so():
    tokens, tags = _panel([('HEMOGLOBIN', '12.1', 'g/dL')])
    r = NERProcessor(patient_sex=None).process(tokens, tags)['lab_results'][0]
    assert r['status'] == 'NORMAL', r
    assert any('sex not provided' in c for c in r['caveats']), r


# ---------------------------------------------------------------------------
# F2 - the prompt actually instructs the model
# ---------------------------------------------------------------------------

def test_summary_prompt_is_grounded_and_instructed():
    """Results go as JSON in the shape the adapter was fine-tuned on."""
    import json as _json
    report = {'lab_results': [
        {'test': 'Hemoglobin', 'value': '10.2', 'unit': 'g/dL'},
        {'test': 'MCHC', 'value': '33', 'unit': 'g/dL'},
    ], 'patient_sex': 'F'}
    prompt = build_summary_prompt(report)

    assert 'grade 8' in prompt                       # readability instruction
    assert 'Never recalculate' in prompt             # explain-don't-judge

    payload = _json.loads(prompt[prompt.index('['):prompt.rindex(']') + 1])
    by_test = {r['test']: r for r in payload}
    hb = by_test['Hemoglobin']
    # The status is COMPUTED and supplied; the model never derives it.
    assert hb['status'] == 'LOW', hb
    # Adapter 2's key, with its en dash, and the female range applied.
    assert hb['reference_range'] == '11.6\u201315 g/dL', hb
    # MCHC is in the table now, so it classifies rather than being refused.
    assert by_test['MCHC']['status'] in ('NORMAL', 'HIGH', 'LOW'), by_test['MCHC']


def test_summary_payload_matches_adapter_2_training_records():
    """Adapter 2 was fine-tuned on records of exactly this shape:

        {"test": "Glucose", "value": 179.0, "unit": "mg/dL",
         "test_name": "Glucose", "status": "HIGH",
         "reference_range": "70\u201399 mg/dL"}
    """
    from app.pipeline.llm import build_results_payload
    rec = build_results_payload(
        {'lab_results': [{'test': 'Glucose', 'value': '179', 'unit': 'mg/dL'}],
         'patient_sex': 'M'})[0]

    assert list(rec)[:6] == ['test', 'value', 'unit', 'test_name',
                             'status', 'reference_range'], list(rec)
    assert rec['test'] == rec['test_name'] == 'Glucose', rec
    assert isinstance(rec['value'], float) and rec['value'] == 179.0, rec
    assert rec['status'] == 'HIGH', rec
    assert rec['reference_range'] == '70\u201399 mg/dL', rec   # EN DASH, as trained


def test_the_model_receives_the_range_alongside_the_status():
    """Both must be present so the model can corroborate, not just assert."""
    from app.pipeline.llm import build_results_payload
    for rec in build_results_payload({'lab_results': [
        {'test': 'Glucose', 'value': '179', 'unit': 'mg/dL'},
        {'test': 'Platelet Count', 'value': '280', 'unit': '10^9/L'},
    ], 'patient_sex': 'M'}):
        assert rec['status'] in ('HIGH', 'LOW', 'NORMAL'), rec
        assert rec['reference_range'], rec


def test_status_is_computed_before_the_model_sees_anything():
    """The model is handed the verdict; it does not decide it.

    Proven by classifying with no model available at all.
    """
    proc = NERProcessor(patient_sex='M')
    r = proc.process(*_panel([('Glucose', '179', 'mg/dL')]))['lab_results'][0]
    assert r['status'] == 'HIGH', r
    assert r['reference_text'] == '70-99 mg/dL', r


def test_refused_results_carry_a_reason_not_a_range():
    from app.pipeline.llm import build_results_payload
    payload = build_results_payload(
        {'lab_results': [{'test': 'Cholesterol Ratio (Total/HDL)',
                          'value': '42', 'unit': 'mg/dL'}]})
    rec = payload[0]
    assert rec['status'] == 'NOT_CHECKED', rec
    assert 'reference' not in rec, rec
    assert 'ratio' in rec['why'], rec


def test_summary_prompt_never_uses_a_system_role():
    """BioMistral's template raises on any role other than user/assistant."""
    report = {'lab_results': [{'test': 'Glucose', 'value': '92', 'unit': 'mg/dL'}]}
    assert isinstance(build_summary_prompt(report), str)


# ---------------------------------------------------------------------------
# F3b - conversation shape the chat template will accept
# ---------------------------------------------------------------------------

def test_leading_assistant_greeting_is_dropped():
    conv = enforce_alternation([
        {'role': 'assistant', 'content': 'Hello! I am your MedReport AI Assistant.'},
        {'role': 'user', 'content': 'hi'},
    ])
    assert [m['role'] for m in conv] == ['user']


def test_consecutive_user_turns_are_merged_not_lost():
    conv = enforce_alternation([
        {'role': 'user', 'content': 'first'},
        {'role': 'user', 'content': 'second'},
    ])
    assert len(conv) == 1
    assert 'first' in conv[0]['content'] and 'second' in conv[0]['content']


def test_conversation_always_alternates_from_a_user_turn():
    """The exact invariant BioMistral's chat template enforces."""
    messy = [
        {'role': 'assistant', 'content': 'greeting'},
        {'role': 'assistant', 'content': 'another'},
        {'role': 'user', 'content': 'q1'},
        {'role': 'assistant', 'content': 'a1'},
    ]
    conv = build_chat_conversation('q2', None, messy)
    assert conv[0]['role'] == 'user'
    for i, msg in enumerate(conv):
        assert msg['role'] == ('user' if i % 2 == 0 else 'assistant'), conv


def test_report_context_is_grounded_into_the_first_turn():
    ctx = [{'test': 'Hemoglobin', 'value': '10.2', 'unit': 'g/dL'}]
    conv = build_chat_conversation('what is my hemoglobin?', ctx, [])
    assert '"status": "LOW"' in conv[0]['content']
    assert 'what is my hemoglobin?' in conv[0]['content']


def test_chat_context_accepts_results_plus_summary():
    """The frontend now sends {lab_results, summary}; bare lists still work."""
    ctx = {'lab_results': [{'test': 'Hemoglobin', 'value': '10.2', 'unit': 'g/dL'}],
           'summary': 'Your hemoglobin is a little low.'}
    conv = build_chat_conversation('why is it low?', ctx, [])
    # Results ride on the first USER turn; the summary is its own ASSISTANT turn.
    assert '"status": "LOW"' in conv[0]['content'], conv[0]
    assert conv[1]['role'] == 'assistant', conv
    assert conv[1]['content'] == 'Your hemoglobin is a little low.', conv[1]

    # A bare list (no summary) seeds only the user turn.
    legacy = build_chat_conversation('why is it low?', ctx['lab_results'], [])
    assert '"status": "LOW"' in legacy[0]['content']
    assert [m['role'] for m in legacy] == ['user'], legacy


def test_the_current_question_is_the_last_turn():
    """With history, turn 1 is an OLD message; the question must not move."""
    ctx = {'lab_results': [{'test': 'Hemoglobin', 'value': '10.2', 'unit': 'g/dL'}],
           'summary': 'Your hemoglobin is a little low.'}
    hist = [{'role': 'assistant', 'content': 'Greeting'},
            {'role': 'user', 'content': 'hi'},
            {'role': 'assistant', 'content': 'Hello!'}]
    conv = build_chat_conversation('why is it low?', ctx, hist)
    # The question stays last; the seed (instructions + prior explanation) is
    # prepended, so turn 0 is no longer an old message.
    assert conv[-1]['content'] == 'why is it low?', conv[-1]
    assert conv[0]['role'] == 'user' and '"status": "LOW"' in conv[0]['content']
    assert 'hi' in " ".join(m['content'] for m in conv), conv


def test_long_history_is_trimmed():
    """The seeded turn is large; unbounded history would overflow the window."""
    from app.pipeline.llm import MAX_HISTORY_TURNS
    hist = []
    for i in range(30):
        hist.append({'role': 'user', 'content': f'q{i}'})
        hist.append({'role': 'assistant', 'content': f'a{i}'})
    conv = build_chat_conversation('latest?', None, hist)
    assert len(conv) <= MAX_HISTORY_TURNS + 2, len(conv)
    assert conv[-1]['content'] == 'latest?"'.rstrip('"')


def test_history_accepts_the_frontend_sender_text_shape():
    hist = [{'sender': 'user', 'text': 'hi'}, {'sender': 'assistant', 'text': 'hello'}]
    assert normalize_history(hist) == [
        {'role': 'user', 'content': 'hi'},
        {'role': 'assistant', 'content': 'hello'},
    ]


# ---------------------------------------------------------------------------
# Grounded rule-based responder (this IS the chat in stub mode)
# ---------------------------------------------------------------------------

def test_fallback_chat_uses_the_computed_status():
    ctx = [{'test_name': 'Hemoglobin', 'value': '10.2', 'unit': 'g/dL',
            'status': 'LOW', 'reference_text': '11.6-15 g/dL'}]
    reply = generate_fallback_chat_response('what is my hemoglobin?', ctx)
    assert '10.2' in reply and '11.6-15' in reply and 'lower' in reply.lower()


def test_fallback_chat_refuses_to_judge_unevaluated_results():
    ctx = [{'test_name': 'MCHC', 'value': '33', 'unit': 'g/dL',
            'status': 'UNKNOWN', 'reason': 'TEST_NOT_IN_REFERENCE_TABLE'}]
    reply = generate_fallback_chat_response('what about my MCHC?', ctx)
    assert 'not in our reference table' in reply
    assert "can't say" in reply.lower()
    assert 'doctor' in reply.lower()
    # Saying it cannot tell whether the value is "high or low" is fine. What it
    # must never do is deliver one of the verdict phrasings used for results
    # that WERE evaluated.
    for verdict in ('within the normal range', 'higher than the normal range',
                    'lower than the normal range'):
        assert verdict not in reply.lower(), f"asserted a verdict: {verdict!r}"


def test_symptoms_are_acknowledged_without_diagnosing():
    ctx = [{'test_name': 'Hemoglobin', 'value': '10.2', 'unit': 'g/dL', 'status': 'LOW'}]
    reply = generate_fallback_chat_response('I have been feeling very tired', ctx)
    assert "can't diagnose" in reply.lower()
    assert 'doctor' in reply.lower()
    assert 'Hemoglobin' in reply


# ---------------------------------------------------------------------------
# Readability loop
# ---------------------------------------------------------------------------

HARD = ("Notwithstanding the aforementioned haematological parameters, the erythrocyte "
        "concentration of 14.2 g/dL demonstrates conformity with the anticipated "
        "physiological reference interval established for adult male individuals.")
EASY = "Your hemoglobin is 14.2 g/dL. That is normal for an adult man."


def test_grade_is_measured():
    assert flesch_kincaid_grade(HARD) > flesch_kincaid_grade(EASY)


def test_loop_stops_once_the_target_is_met():
    calls = []
    def gen(prompt):
        calls.append(prompt)
        return EASY
    result = revise_to_grade(EASY, gen, target_grade=8.0, max_rounds=2)
    assert calls == [], "already at target; should not call the model"
    assert result.target_met


def test_loop_simplifies_and_reports_its_work():
    def gen(prompt):
        return EASY
    result = revise_to_grade(HARD, gen, target_grade=8.0, max_rounds=2)
    assert result.text == EASY
    assert result.grade < flesch_kincaid_grade(HARD)
    assert result.rounds >= 1
    assert any(step.get('accepted') for step in result.history[1:])


def test_rewrite_that_changes_a_number_is_rejected():
    """Numeric fidelity is non-negotiable: keep the harder text instead."""
    def gen(prompt):
        return "Your hemoglobin is 41.2 g/dL. That is normal."   # digits transposed
    result = revise_to_grade(HARD, gen, target_grade=8.0, max_rounds=1)
    assert result.text == HARD, "a rewrite that altered a value was accepted"
    assert any('numeric fidelity' in s.get('note', '') for s in result.history)


def test_best_attempt_wins_not_the_last():
    outputs = iter([EASY, HARD])          # improves, then regresses
    def gen(prompt):
        return next(outputs)
    result = revise_to_grade(HARD, gen, target_grade=1.0, max_rounds=2)
    assert result.text == EASY


def test_numbers_preserved_detects_changes():
    assert numbers_preserved("Hb 14.2 and WBC 7.2", "WBC 7.2, Hb 14.2")
    assert not numbers_preserved("Hb 14.2", "Hb 14.3")


# ---------------------------------------------------------------------------
# Rule-based parser used by stub mode
# ---------------------------------------------------------------------------

def test_reference_column_is_not_mistaken_for_a_unit():
    pipe = MedicalReportPipeline()
    parsed = pipe.run_rule_based_fallback("Hemoglobin               14.2      g/dL         13.0-17.0")
    lab = parsed['lab_results'][0]
    assert lab['test_name'] == 'Hemoglobin', lab
    assert lab['unit'] == 'g/dL', lab
    assert lab['status'] in ('NORMAL', 'LOW', 'HIGH'), lab



# ---------------------------------------------------------------------------
# Generation boundary (regression from the first live ZeroGPU deploy)
# ---------------------------------------------------------------------------

def test_trim_cuts_replayed_training_format():
    """The live Space returned the answer followed by raw scaffolding."""
    from app.pipeline.llm import trim_generation
    raw = (
        'Your hemoglobin is 14.2 g/dL. This result is normal, but the reference '
        'range for hemoglobin is different for men and women. [/INST] [INST] '
        '[{"test": "Hemoglobin", "value": 14.2, "unit": "g/dL", "status": "NORMAL"}] '
        '[/INST]## Your Lab Results Explained'
    )
    out = trim_generation(raw)
    assert out.endswith('men and women.'), out
    for leak in ('[INST]', '[/INST]', '"test":', '## Your Lab Results'):
        assert leak not in out, f'{leak!r} leaked: {out!r}'


def test_trim_leaves_clean_output_alone():
    from app.pipeline.llm import trim_generation
    clean = "Your hemoglobin is 14.2 g/dL. That is within the normal range."
    assert trim_generation(clean) == clean


def test_trim_keeps_a_legitimate_summary_heading():
    """A summary that STARTS with the heading must not be emptied."""
    from app.pipeline.llm import trim_generation
    s = "## Your Lab Results Explained\n\n* **Hemoglobin (14.2 g/dL, NORMAL):** ..."
    assert trim_generation(s).startswith("## Your Lab Results Explained")


def test_trim_handles_empty():
    from app.pipeline.llm import trim_generation
    assert trim_generation("") == ""
    assert trim_generation(None) == ""



# ---------------------------------------------------------------------------
# Chat must answer the question, not re-summarise the report
# ---------------------------------------------------------------------------

def test_summary_shaped_reply_is_detected():
    """Asking about one test returned a summary of all twelve."""
    from app.pipeline.llm import looks_like_a_summary
    reply = (
        "## Your Lab Results Explained\n\n"
        "- Hemoglobin (15.1 g/dL, NORMAL): Hemoglobin carries oxygen.\n"
        "- Hematocrit (46.3 %, NORMAL): Hematocrit measures red cells.\n"
        "- Platelet Count (275 x10^3/uL, NORMAL): Platelets help clotting.\n"
    )
    assert looks_like_a_summary(reply)


def test_bulleted_summary_without_heading_is_detected():
    from app.pipeline.llm import looks_like_a_summary
    reply = (
        "- Hemoglobin (15.1 g/dL, NORMAL): carries oxygen.\n"
        "- Hematocrit (46.3 %, NORMAL): measures red cells.\n"
        "- Platelets (275, NORMAL): help clotting.\n"
    )
    assert looks_like_a_summary(reply)


def test_a_real_answer_is_not_flagged_as_a_summary():
    from app.pipeline.llm import looks_like_a_summary
    for good in (
        "Your white blood cell count is 10.1 thousand per microlitre. That is normal.",
        "We could not check your MCHC. Our reference table does not include it.",
        "Thank you for telling me. Please mention that to your doctor.",
    ):
        assert not looks_like_a_summary(good), good


def test_prompts_forbid_printing_internal_codes():
    """Patients were shown raw NOT_EVALUATED and x10^3/uL tokens."""
    from app.pipeline.llm import SYSTEM_PROMPT, CHAT_PROMPT
    for prompt in (SYSTEM_PROMPT, CHAT_PROMPT):
        assert "NOT_EVALUATED" in prompt          # named so it can be banned
        assert "Never print" in prompt or "NEVER PRINT" in prompt



# ---------------------------------------------------------------------------
# Lexicon corruption (regression from the St Jude's report)
# ---------------------------------------------------------------------------
# The lexicon rules apply cumulatively. A bare \bcholesterol\b rule ran before
# the HDL/LDL rules, so it rewrote the word inside their names and the specific
# rules then rewrote their own output. The UI showed the wreckage as test names.

def test_lipid_names_survive_the_lexicon():
    from app.pipeline.ner import LexiconCorrectorAllTests
    lx = LexiconCorrectorAllTests()
    cases = {
        'HDL Cholesterol': 'Cholesterol, HDL',
        'LDL Cholesterol (Calc.)': 'Cholesterol, LDL, Calculated',
        'Total Cholesterol': 'Cholesterol, Total',
        'Cholesterol': 'Cholesterol, Total',
        'Cholesterol Ratio': 'Cholesterol Ratio (Total/HDL)',
        'Triglycerides': 'Triglycerides',
    }
    for raw, want in cases.items():
        assert lx.correct_text(raw).strip() == want, (raw, lx.correct_text(raw))


def test_lexicon_is_idempotent_for_lipids():
    """Running the corrector twice must not keep rewriting."""
    from app.pipeline.ner import LexiconCorrectorAllTests
    lx = LexiconCorrectorAllTests()
    for raw in ('HDL Cholesterol', 'LDL Cholesterol (Calc.)', 'Total Cholesterol'):
        once = lx.correct_text(raw).strip()
        assert lx.correct_text(once).strip() == once, (raw, once)


def test_corrected_lipid_names_actually_resolve():
    from app.pipeline.ner import LexiconCorrectorAllTests
    lx = LexiconCorrectorAllTests()
    proc = NERProcessor(patient_sex='M')
    for raw, value, unit, expected in (
        ('HDL Cholesterol', '42', 'mg/dL', 'NORMAL'),
        ('LDL Cholesterol (Calc.)', '145', 'mg/dL', 'HIGH'),
        ('Total Cholesterol', '215', 'mg/dL', 'HIGH'),
        ('Triglycerides', '138', 'mg/dL', 'NORMAL'),
    ):
        name = lx.correct_text(raw).strip()
        r = proc.process(*_panel([(name, value, unit)]))['lab_results'][0]
        assert r['status'] == expected, (raw, name, r)


def test_electrolytes_with_ion_symbols_are_parsed():
    """"Sodium (Na+)" used to fail the line regex entirely and vanish."""
    pipe = MedicalReportPipeline()
    text = ("Sodium (Na+)         141     mmol/L    135 - 145\n"
            "Potassium (K+)       4.3     mmol/L    3.5 - 5.1\n")
    names = [l['test_name'] for l in pipe.run_rule_based_fallback(text)['lab_results']]
    assert 'Sodium' in names and 'Potassium' in names, names



# ---------------------------------------------------------------------------
# Chat context arriving in the wrong shape (live "'str' object has no
# attribute 'get'" crash)
# ---------------------------------------------------------------------------
# gr.JSON does not guarantee a parsed object. When the context arrived as a
# JSON *string*, `list(report_context)` split it into CHARACTERS, so the first
# "result" was '{' and classification raised. Every shape must now be safe.

def _sodium_ctx():
    return {'lab_results': [{'test_name': 'Sodium', 'test': 'Sodium',
                             'value': '128', 'unit': 'mmol/L',
                             'status': 'LOW',
                             'reference_text': '136-145 mmol/L'}],
            'summary': 'Your sodium is a little low.'}


def test_chat_survives_every_context_shape():
    import json as _json
    from app.pipeline.llm import split_report_context
    ctx = _sodium_ctx()
    shapes = [
        ctx,                                   # dict
        _json.dumps(ctx),                      # JSON string  <- the live crash
        ctx['lab_results'],                    # bare list
        _json.dumps(ctx['lab_results']),       # list as JSON string
        None, '', 'not json at all', ['a', 'b'], 42,
    ]
    for shape in shapes:
        results, summary = split_report_context(shape)   # must not raise
        assert isinstance(results, list), shape
        assert all(isinstance(r, dict) for r in results), shape
        build_chat_conversation('explain my low sodium', shape, [])


def test_a_json_string_context_still_produces_a_grounded_answer():
    """Not merely 'does not crash' - the results must survive the round trip."""
    import json as _json
    conv = build_chat_conversation(
        'explain my low sodium', _json.dumps(_sodium_ctx()), [])
    body = conv[0]['content']
    assert '"status": "LOW"' in body, body[:300]
    assert 'Sodium' in body


def test_fallback_responder_accepts_the_same_shapes():
    import json as _json
    ctx = _sodium_ctx()
    for shape in (ctx, _json.dumps(ctx), ctx['lab_results']):
        reply = generate_fallback_chat_response('explain my low sodium', shape)
        assert '128' in reply and 'lower' in reply.lower(), (shape, reply)


def test_no_context_never_claims_everything_is_normal():
    """Zero information must not become a clean bill of health."""
    for empty in (None, '', [], 'garbage'):
        reply = generate_fallback_chat_response('are my results ok?', empty)
        assert 'within the normal' not in reply.lower(), (empty, reply)
        assert 'upload' in reply.lower(), (empty, reply)



# ---------------------------------------------------------------------------
# Real-report unit notations (the "lots of Not checked" report)
# ---------------------------------------------------------------------------

def test_indian_and_legacy_unit_notations_resolve():
    """gm/dL, /cumm and mill/cumm are how most labs actually print units."""
    from app.reference_ranges.range_lookup import RangeLookup
    lk = RangeLookup()
    for name, value, unit in (
        ("Hemoglobin", 15.2, "gm/dL"),
        ("WBC Count", 8100, "/cumm"),
        ("RBC Count", 5.37, "mill/cumm"),
        ("Platelet Count", 280000, "/cumm"),
    ):
        r = lk.classify(name, value, unit, sex="M")
        assert r.status == "NORMAL", (name, unit, r.status, r.reason)


def test_meq_converts_only_for_ions_of_known_charge():
    """mEq/L is 1:1 with mmol/L for monovalent ions, and refused otherwise."""
    from app.reference_ranges.range_lookup import RangeLookup
    lk = RangeLookup()
    for name, value in (("Sodium", 141), ("Potassium", 4.3),
                        ("Chloride", 105), ("Bicarbonate", 26)):
        r = lk.classify(name, value, "mEq/L")
        assert r.status == "NORMAL", (name, r.status, r.reason)
        assert r.value_in_reference_unit == value, r      # 1 mEq == 1 mmol

    # An analyte whose charge we do not know stays refused rather than guessed.
    assert lk.classify("Ferritin", 95, "mEq/L").status == "NOT_EVALUATED"


def test_low_sodium_in_meq_is_flagged():
    """The case from the live report: Sodium 128 mEq/L must read LOW."""
    from app.reference_ranges.range_lookup import RangeLookup
    r = RangeLookup().classify("Sodium", 128, "mEq/L")
    assert r.status == "LOW", r


def test_parenthetical_synonyms_resolve():
    """Reports write "SGPT (ALT)"; neither half alone is the whole name."""
    from app.reference_ranges.range_lookup import RangeLookup
    lk = RangeLookup()
    for name, value, unit in (("SGPT (ALT)", 32, "U/L"), ("SGOT (AST)", 28, "U/L"),
                              ("BUN (Blood Urea Nitrogen)", 16, "mg/dL"),
                              ("Glucose (Fasting)", 98, "mg/dL")):
        r = lk.classify(name, value, unit, sex="M")
        assert r.status == "NORMAL", (name, r.status, r.reason)


def test_normalize_name_only_strips_balanced_wrappers():
    """A blind strip ate the ')' of "SGPT (ALT)", leaving "sgpt (alt"."""
    from app.reference_ranges.build_reference_db import normalize_name
    assert normalize_name("SGPT (ALT)") == "sgpt (alt)"
    assert normalize_name("Thyroxine (T4)") == "thyroxine (t4)"
    assert normalize_name("(Albumin)") == "albumin"      # workbook junk row
    assert normalize_name("<Albumin>") == "albumin"



# ---------------------------------------------------------------------------
# The report's own reference column
# ---------------------------------------------------------------------------
# Our table cannot hold every test, and OCR sometimes damages a unit beyond
# repair. But the lab printed its own reference range next to the value, and
# that is better evidence than our broad published figures: it is that lab's
# validated range on that instrument.

def test_report_ranges_are_extracted_from_the_reference_column():
    from app.pipeline.pipeline import extract_report_ranges
    text = ("WBC Count            6.7     x10 9/L    4.0 - 11.0\n"
            "Anion Gap            11      mmol/L     8 - 16\n"
            "Total Cholesterol    215     mg/dL      < 200\n"
            "HDL Cholesterol      42      mg/dL      > 40\n")
    got = extract_report_ranges(text)
    assert got["wbc count"] == "4.0 - 11.0", got
    assert got["anion gap"] == "8 - 16", got
    assert got["total cholesterol"] == "< 200", got
    assert got["hdl cholesterol"] == "> 40", got


def test_the_result_is_not_mistaken_for_a_range():
    """A line's LAST number pair is the reference column, not the result."""
    from app.pipeline.pipeline import extract_report_ranges
    got = extract_report_ranges("Glucose 98 mg/dL 70 - 99\n")
    assert got.get("glucose") == "70 - 99", got


def test_a_test_we_do_not_hold_is_checked_against_the_report():
    """Anion Gap is not in the workbook at all."""
    proc = NERProcessor(patient_sex='M', report_ranges={'anion gap': '8 - 16'})
    r = proc.process(*_panel([('Anion Gap', '11', 'mmol/L')]))['lab_results'][0]
    assert r['status'] == 'NORMAL', r
    assert r['reference_source'] == 'report', r
    assert any('from your report' in c for c in r['caveats']), r

    high = NERProcessor(patient_sex='M', report_ranges={'anion gap': '8 - 16'})
    r2 = high.process(*_panel([('Anion Gap', '22', 'mmol/L')]))['lab_results'][0]
    assert r2['status'] == 'HIGH', r2


def test_a_damaged_unit_is_rescued_by_the_report_range():
    """"x100/L" is OCR damage we refuse to guess at - but the report's own
    range needs no unit resolution at all."""
    proc = NERProcessor(patient_sex='M', report_ranges={'wbc count': '4.0 - 11.0'})
    r = proc.process(*_panel([('WBC Count', '6.7', 'x100/L')]))['lab_results'][0]
    assert r['status'] == 'NORMAL', r
    assert r['reference_source'] == 'report', r


def test_our_table_still_wins_when_it_can_judge():
    """The report range is a FALLBACK, not an override."""
    proc = NERProcessor(patient_sex='M', report_ranges={'hemoglobin': '1.0 - 2.0'})
    r = proc.process(*_panel([('Hemoglobin', '14.2', 'g/dL')]))['lab_results'][0]
    assert r['status'] == 'NORMAL', r                    # not HIGH per the bogus range
    assert r.get('reference_source') != 'report', r


def test_no_report_range_keeps_the_honest_refusal():
    proc = NERProcessor(patient_sex='M', report_ranges={})
    r = proc.process(*_panel([('Anion Gap', '11', 'mmol/L')]))['lab_results'][0]
    assert r['status'] == 'UNKNOWN', r
    assert r['reason'], r



# ---------------------------------------------------------------------------
# Chat is a CONTINUATION, not a fresh report
# ---------------------------------------------------------------------------

def test_summary_is_seeded_as_an_assistant_turn():
    """The explanation the patient read must be the model's OWN previous turn.

    Putting it inside the user turn as quoted text made the model treat each
    follow-up as a new request to describe the report, so "More about
    Eosinophils" came back as another mini-report with headings.
    """
    ctx = {'lab_results': [{'test': 'Eosinophils', 'value': '2.0', 'unit': '%'}],
           'summary': '## Your Lab Results Explained\n- Eosinophils (2.0 %, Normal): ...'}
    conv = build_chat_conversation('More about Eosinophils', ctx, [])
    assert [m['role'] for m in conv] == ['user', 'assistant', 'user'], conv
    assert conv[1]['content'].startswith('## Your Lab Results'), conv[1]
    assert conv[-1]['content'] == 'More about Eosinophils', conv[-1]


def test_chat_prompt_forbids_restating_the_report():
    from app.pipeline.llm import CHAT_PROMPT
    low = CHAT_PROMPT.lower()
    assert 'never restate' in low or 'do not restate' in low, CHAT_PROMPT
    assert 'layout' in low or 'headings' in low, CHAT_PROMPT


def test_no_system_role_is_ever_emitted():
    """This adapter's template raises on any role but user/assistant."""
    ctx = {'lab_results': [{'test': 'Eosinophils', 'value': '2.0', 'unit': '%'}],
           'summary': 'Your eosinophils are normal.'}
    for hist in ([], [{'role': 'assistant', 'content': 'Greeting'},
                      {'role': 'user', 'content': 'hi'},
                      {'role': 'assistant', 'content': 'hello'}]):
        conv = build_chat_conversation('More about Eosinophils', ctx, hist)
        assert all(m['role'] in ('user', 'assistant') for m in conv), conv
        # ...and the strict alternation the template also demands.
        for i, m in enumerate(conv):
            assert m['role'] == ('user' if i % 2 == 0 else 'assistant'), conv


def test_chat_context_is_per_request_not_global():
    """Two patients must never see each other's results.

    A module-level conversation_history would leak across users on a shared
    Space; the context is passed in on every call instead.
    """
    a = build_chat_conversation('q', {'lab_results': [{'test': 'Glucose', 'value': '179', 'unit': 'mg/dL'}]}, [])
    b = build_chat_conversation('q', {'lab_results': [{'test': 'Sodium', 'value': '141', 'unit': 'mEq/L'}]}, [])
    assert 'Glucose' in a[0]['content'] and 'Glucose' not in b[0]['content']
    assert 'Sodium' in b[0]['content'] and 'Sodium' not in a[0]['content']


def _run():
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith('test_')]
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


if __name__ == '__main__':
    raise SystemExit(_run())
