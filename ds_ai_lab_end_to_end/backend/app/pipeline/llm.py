import os
import json
import re
from typing import Dict, List, Optional

from app.config import (
    BIOMISTRAL_BASE_MODEL,
    BIOMISTRAL_ADAPTER_PATH,
    STUB_MODELS,
    READABILITY_TARGET_GRADE,
    READABILITY_MAX_ROUNDS,
)
from app.reference_ranges.range_lookup import (
    build_grounding_block,
    get_lookup,
    reason_text,
    NOT_EVALUATED,
)
from app.pipeline.readability import revise_to_grade, flesch_kincaid_grade

# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------
# IMPORTANT: this text is prepended to the first USER turn, never sent as a
# {"role": "system"} message. The adapter's chat_template.jinja ends with
#   raise_exception('Only user and assistant roles are supported!')
# so a system role makes apply_chat_template throw, which previously surfaced
# only as a silent fallback in the Space logs.
SYSTEM_PROMPT = """You explain medical lab results to a patient who has no medical training.

HOW TO WRITE
- Write at a US grade 8 reading level or simpler.
- Keep sentences under 15 words. Prefer short, everyday words.
- Be calm and factual. Do not alarm the reader.

NEVER PRINT THESE - they are internal codes, not English:
- Status codes. Write "normal", "higher than normal", "lower than normal",
  or "we could not check this one" instead of NORMAL / HIGH / LOW /
  NOT_EVALUATED.
- Reason codes such as TEST_NOT_IN_REFERENCE_TABLE or UNIT_MISMATCH. Say what
  they mean in plain words.
- Always spell out a test the first time: "MCHC (the amount of hemoglobin
  packed into each red blood cell)". Never leave a bare abbreviation.
- Write units the way people say them: "10.1 thousand per microlitre", not
  "10.1 x10^3/uL".

WHAT YOU MAY AND MAY NOT SAY
- The STATUS of each result below was computed for you and is correct.
  Explain what it means. Never recalculate it and never contradict it.
- If a result is marked NOT_EVALUATED, say that this report's reference table
  does not cover that test, and that their doctor can interpret it. Never guess
  whether it is high or low.
- Say what each test measures and what can make it move. Do not diagnose, and
  do not name a disease as if the patient has it.
- Repeat any caveats shown with a result.
- End with one short line telling the patient to discuss the results with their
  doctor.
"""

CHAT_PROMPT = """You are a medical assistant helping a patient understand their lab
results. The patient has ALREADY been shown the explanation that follows, so this is a
continuation of that conversation, not a new report.

- Answer the follow-up question and nothing else. Never restate results that were
  already explained, and never reproduce the report layout, headings or bullet list.
- Reply in two or three short sentences, the way a person would speak.
- Answer using only these results. Never invent a value or a range.
- Never change a status you are given. If a test could not be checked, say the
  reference table does not cover it.
- Write at a US grade 8 reading level. Keep sentences short.
- Never print status or reason codes such as NORMAL, HIGH, NOT_EVALUATED or
  TEST_NOT_IN_REFERENCE_TABLE. Use plain words.
- Do not diagnose. Encourage the patient to talk to their doctor about anything
  that worries them.
- If the patient mentions how they feel, acknowledge it, connect it to the
  relevant result only if the connection is real, and suggest they mention it to
  their doctor.

LAB RESULTS (JSON):
{results_json}
"""

class BioMistralPipeline:
    def __init__(self, base_model: str = BIOMISTRAL_BASE_MODEL, adapter_path: str = BIOMISTRAL_ADAPTER_PATH):
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.tokenizer = None
        self.model = None

    def load_models(self):
        """Lazy loads the base model and fine-tuned LoRA adapter once."""
        if self.model is None:
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
            from peft import PeftModel

            print(f"Loading BioMistral base model: {self.base_model}")
            
            # BitsAndBytes 4-bit configuration matching notebook specifications
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )

            token = os.environ.get("HF_TOKEN")

            try:
                self.tokenizer = AutoTokenizer.from_pretrained(self.base_model, token=token)
                self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

                base = AutoModelForCausalLM.from_pretrained(
                    self.base_model,
                    quantization_config=bnb_config,
                    device_map="auto",
                    torch_dtype=torch.bfloat16,
                    token=token,
                )
            except Exception as e:
                raise RuntimeError(f"Failed to load BioMistral base model '{self.base_model}': {e}")

            if not ('/' in self.adapter_path and not os.path.exists(self.adapter_path)):
                if not os.path.exists(self.adapter_path):
                    raise FileNotFoundError(
                        f"LoRA adapter folder not found at: '{self.adapter_path}'. "
                        f"Please verify you have downloaded the fine-tuned adapter weights."
                    )

            print(f"Applying LoRA adapter from: {self.adapter_path}")
            try:
                self.model = PeftModel.from_pretrained(base, self.adapter_path, token=token)
                self.model.eval()
            except Exception as e:
                raise RuntimeError(f"Failed to apply LoRA adapter: {e}")

            print("Fine-tuned BioMistral model loaded successfully.")

    def generate(self, prompt: str, max_new_tokens: int = 1024) -> str:
        self.load_models()
        
        import torch
        messages = [{"role": "user", "content": prompt}]
        
        # Formats output with the chat templates of BioMistral
        inputs = self.tokenizer.apply_chat_template(
            messages, 
            add_generation_prompt=True, 
            tokenize=True,
            return_dict=True, 
            return_tensors="pt"
        ).to(self.model.device)
        
        input_len = inputs["input_ids"].shape[-1]
        
        with torch.no_grad():
            output = self.model.generate(
                **inputs, 
                max_new_tokens=max_new_tokens, 
                do_sample=False
            )
            output = output[:, input_len:]
            
        return trim_generation(self.tokenizer.decode(output[0], skip_special_tokens=True))

    def generate_chat(self, message: str, report_context=None, history: Optional[List] = None, max_new_tokens: int = 512, summary: Optional[str] = None) -> str:
        self.load_models()
        import torch

        conversation = build_chat_conversation(message, report_context, history, summary)

        inputs = self.tokenizer.apply_chat_template(
            conversation,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device)
        
        input_len = inputs["input_ids"].shape[-1]
        
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                # The adapter is fine-tuned on the SUMMARY task, so in chat it
                # tends to replay that format. These penalise phrases and
                # n-grams it has already produced - which is what a restated
                # report is made of.
                repetition_penalty=1.3,
                no_repeat_ngram_size=3,
            )
            output = output[:, input_len:]
            
        return trim_generation(self.tokenizer.decode(output[0], skip_special_tokens=True))


# Markers that mean the model has stopped answering and started replaying its
# training format. BioMistral was fine-tuned on the summary task (lab JSON in,
# markdown summary out), so after a short chat answer it tends to emit another
# [INST] turn and re-summarise. "[INST]" is literal text in the Mistral chat
# template, not a special token, so skip_special_tokens does not remove it.
_GENERATION_STOPS = ("[INST]", "[/INST]", "</s>", "<s>")


def trim_generation(text: str) -> str:
    """Cut a generation at the first point the model runs past its turn.

    Without this the chat surfaces raw scaffolding to the patient, e.g.
        Your hemoglobin is 14.2 g/dL. This result is normal.
        [/INST] [INST] [{"test": "Hemoglobin", ...}] [/INST]## Your Lab Results...
    """
    if not text:
        return ""
    cut = len(text)
    for marker in _GENERATION_STOPS:
        idx = text.find(marker)
        if idx != -1:
            cut = min(cut, idx)
    trimmed = text[:cut].strip()
    # A chat reply that drifts into the summary layout is also over-running.
    for heading in ("## Your Lab Results", "## Your Results Overview"):
        idx = trimmed.find(heading)
        if idx > 0:
            trimmed = trimmed[:idx].strip()
    return trimmed


def looks_like_a_summary(reply: str) -> bool:
    """True when a chat reply is really the whole-report summary.

    Detected by shape rather than wording: the summary format is a bulleted
    list of `Test (value unit, STATUS):` lines, so several such lines in a chat
    answer means the model reverted to its training task.
    """
    if not reply:
        return False
    if reply.lstrip().startswith(("## Your Lab Results", "## Your Results Overview")):
        return True
    bullets = re.findall(r"^[-*]\s+\*{0,2}[A-Z][^\n:]{2,60}\(", reply, re.MULTILINE)
    return len(bullets) >= 3


def normalize_history(history: Optional[List]) -> List[Dict]:
    """Coerce whatever the client sent into a list of {role, content} dicts.

    Accepts Gradio's messages format, the older (user, assistant) tuple format,
    and the frontend's {sender, text} shape.
    """
    out: List[Dict] = []
    for turn in history or []:
        if isinstance(turn, dict):
            role = turn.get("role") or turn.get("sender")
            content = turn.get("content") or turn.get("text")
            if role in ("user", "assistant") and content:
                out.append({"role": role, "content": str(content)})
        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            user_text, assistant_text = turn
            if user_text:
                out.append({"role": "user", "content": str(user_text)})
            if assistant_text:
                out.append({"role": "assistant", "content": str(assistant_text)})
    return out


def enforce_alternation(conversation: List[Dict]) -> List[Dict]:
    """Force a strict user/assistant/user/... sequence starting with user.

    BioMistral's chat template raises on any other shape:

        raise_exception('Conversation roles must alternate user/assistant/...')

    The UI opens with an assistant greeting, so the history it sends starts with
    an assistant turn and every generation used to throw and fall back silently.
    Repairing this server-side means no client can break generation by sending a
    reasonable-looking history.
    """
    repaired: List[Dict] = []
    for msg in conversation:
        if not repaired:
            # A leading assistant message (the UI's greeting) has no user turn
            # to answer, so it is dropped rather than reordered.
            if msg["role"] != "user":
                continue
            repaired.append(msg)
            continue
        if msg["role"] == repaired[-1]["role"]:
            # Two turns from the same speaker: merge rather than discard, so no
            # user question is lost.
            repaired[-1]["content"] += "\n\n" + msg["content"]
        else:
            repaired.append(msg)
    return repaired


# Mistral's window is finite and the seeded turn is large (results JSON plus the
# summary), so old turns are dropped rather than left to overflow it silently.
MAX_HISTORY_TURNS = 8


def _coerce_json(value):
    """Parse a value that may have arrived as a JSON string.

    gr.JSON does not guarantee a parsed object: a client can send the context
    as a string and it arrives as one. The old code then did
    `list(report_context)`, which splits a STRING INTO CHARACTERS - so the
    first "result" was the character '{' and classification died with
    "'str' object has no attribute 'get'".
    """
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "replace")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None            # a bare string is not a report context
    return value


def split_report_context(report_context) -> tuple[List[Dict], Optional[str]]:
    """Accept {lab_results, summary}, a bare results list, or a JSON string.

    The frontend used to send just the array. Sending the summary alongside it
    lets the assistant refer to what the patient has already read instead of
    re-deriving it, so every shape is supported - and anything unrecognised
    yields no context rather than an exception.
    """
    report_context = _coerce_json(report_context)

    if isinstance(report_context, dict):
        results = _coerce_json(report_context.get("lab_results")) or []
        summary = (report_context.get("summary")
                   or report_context.get("patient_explanation"))
        summary = summary if isinstance(summary, str) else None
    elif isinstance(report_context, (list, tuple)):
        results, summary = report_context, None
    else:
        return [], None

    # Only dict-shaped entries can be classified; anything else is dropped
    # rather than allowed to blow up mid-request.
    clean = [r for r in results if isinstance(r, dict)] if isinstance(results, (list, tuple)) else []
    return clean, (summary.strip() if summary else None)


def build_chat_conversation(
    message: str,
    report_context=None,
    history: Optional[List] = None,
    summary: Optional[str] = None,
) -> List[Dict]:
    """Build a template-safe conversation seeded with the report context.

    Turn 1 carries the instructions, the results as JSON in the shape the
    adapter was fine-tuned on, and the summary the patient has already read.
    All of it rides on a USER turn because the adapter's template rejects a
    system role outright.
    """
    results, ctx_summary = split_report_context(report_context)
    summary = summary or ctx_summary

    conversation = normalize_history(history)
    if len(conversation) > MAX_HISTORY_TURNS:
        conversation = conversation[-MAX_HISTORY_TURNS:]
    conversation.append({"role": "user", "content": str(message)})
    conversation = enforce_alternation(conversation)

    if not conversation:  # pathological input; ask something answerable
        conversation = [{"role": "user", "content": str(message) or "Explain my results."}]

    if results or summary:
        payload = build_results_payload({"lab_results": results}) if results else []
        preamble = CHAT_PROMPT.format(
            results_json=json.dumps(payload, ensure_ascii=False)
        )
        # Seed as a REAL exchange: instructions + data as the user turn, and the
        # explanation the patient already read as the ASSISTANT turn. The model
        # then treats a follow-up as continuing something it already said,
        # rather than as a fresh request to describe the whole report - which is
        # why answers used to come back as another mini-report.
        #
        # No {"role": "system"} turn: this adapter's template raises
        # "Only user and assistant roles are supported!", so the instructions
        # ride on the first user turn instead.
        seed = [{"role": "user", "content": preamble}]
        if summary:
            seed.append({"role": "assistant", "content": summary.strip()})
        conversation = enforce_alternation(seed + conversation)

    return conversation


def generate_fallback_summary(report_json: Dict) -> str:
    lab_results = report_json.get("lab_results", [])
    if not lab_results:
        return "No lab results were detected in the report."
        
    total_tests = len(lab_results)
    abnormal = [l for l in lab_results if l.get('status') in ['HIGH', 'LOW']]
    abnormal_count = len(abnormal)
    
    abnormal_names = [l.get('test_name') or l.get('test') for l in abnormal]
    
    summary_text = "## Your Results Overview\n\n"
    summary_text += f"We analyzed your medical report and extracted **{total_tests} key test results**. "
    if abnormal_count > 0:
        summary_text += f"Overall, **{abnormal_count} {'value is' if abnormal_count == 1 else 'values are'} outside the normal reference ranges** ({', '.join(abnormal_names)}). "
    else:
        summary_text += "All of your values lie comfortably within the normal reference ranges. "
        
    normal = [l for l in lab_results if l.get('status') == 'NORMAL']
    if normal:
        normal_names = [l.get('test_name') or l.get('test') for l in normal]
        summary_text += f"The rest of your numbers, including {', '.join(normal_names[:3])}, look healthy and normal.\n\n"
    else:
        summary_text += "\n\n"
        
    summary_text += "Here is a breakdown of what this means for you:\n\n"
    
    # Detail abnormal results
    if abnormal:
        summary_text += "### Results Requiring Attention:\n\n"
        for lab in abnormal:
            name = lab.get('test_name') or lab.get('test')
            val = lab.get('value')
            unit = lab.get('unit', '')
            status = lab.get('status')
            ref_min = lab.get('ref_min')
            ref_max = lab.get('ref_max')
            
            ref_str = f" (Normal range: **{ref_min}–{ref_max} {unit}**)" if ref_min is not None else ""
            summary_text += f"*   **{name} ({status})**: Your level is **{val} {unit}**{ref_str}.\n"
            # Add general plain-language explanations
            name_lower = name.lower()
            if 'hemoglobin' in name_lower:
                summary_text += "    Hemoglobin is the iron-rich protein that helps red blood cells carry oxygen. A low level is common and often indicates mild anemia, which can make you feel more tired than usual.\n"
            elif 'platelet' in name_lower:
                summary_text += "    Platelets help your blood seal cuts. A high count can sometimes result from minor inflammation, iron deficiency, or recent stress on the body.\n"
            elif 'cholesterol' in name_lower:
                summary_text += "    Total cholesterol measures the fats in your blood. Elevated levels suggest a benefit from monitoring diet and lifestyle or discussing cardiovascular health with your doctor.\n"
            elif 'vitamin d' in name_lower:
                summary_text += "    Vitamin D is crucial for maintaining strong bones and supporting immune defense. Deficiency is highly common and can be improved with diet, safe sun exposure, or supplements.\n"
            elif 'wbc' in name_lower or 'white blood' in name_lower:
                summary_text += "    White blood cells are the core of your immune system. Abnormal levels can indicate your body is responding to an infection or inflammation.\n"
            elif 'tsh' in name_lower or 'thyroid' in name_lower:
                summary_text += "    TSH regulates your thyroid gland which controls your metabolism. Abnormal levels suggest checking thyroid hormone production.\n"
            else:
                summary_text += "    This value is outside the standard reference range. We recommend discussing this result with your healthcare provider to understand it in the context of your overall health.\n"
        summary_text += "\n"

    # Detail normal results
    if normal:
        summary_text += "### Normal Results:\n\n"
        for lab in normal:
            name = lab.get('test_name') or lab.get('test')
            val = lab.get('value')
            unit = lab.get('unit', '')
            ref_min = lab.get('ref_min')
            ref_max = lab.get('ref_max')
            
            ref_str = f" (Range: {ref_min}–{ref_max} {unit})" if ref_min is not None else ""
            summary_text += f"*   **{name}**: **{val} {unit}**{ref_str} — Healthy and normal.\n"
            
    summary_text += "\n> [!NOTE]\n"
    summary_text += "> This summary was generated automatically by the fallback parser. Always consult your primary care physician before making any clinical decisions."
    
    return summary_text


# Global singleton instance cache
_llm_pipeline = None

def _fmt_number(value):
    """A JSON number, as in the training data ("value": 179.0).

    Always a float, never a string: the fine-tuning records use floats
    throughout, so 280 is emitted as 280.0 rather than being tidied to an int.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _reference_range_text(c) -> Optional[str]:
    """Reference range in the adapter's own notation, e.g. "70\u201399 mg/dL".

    The fine-tuning data uses an EN DASH between bounds, so the same character
    is emitted here rather than the ASCII hyphen used elsewhere in this repo.
    """
    if c.status == NOT_EVALUATED or not c.reference_text:
        return None
    return c.reference_text.replace("-", "\u2013", 1) if _looks_two_sided(c) else c.reference_text


def _looks_two_sided(c) -> bool:
    return c.reference_low is not None and c.reference_high is not None


def build_results_payload(report_json: Dict) -> List[Dict]:
    """The lab results as JSON, in the exact shape adapter (2) was trained on.

        {"test": "Glucose", "value": 179.0, "unit": "mg/dL",
         "test_name": "Glucose", "status": "HIGH",
         "reference_range": "70\u201399 mg/dL"}

    Key order and key names follow that record. `test` and `test_name` are both
    the resolved table name, as they were identical throughout training.

    `status` is NOT the model's to decide: it is the value computed by the
    deterministic reference-range lookup and handed over as a given fact. The
    reference range travels with it so the model can quote and corroborate it.
    """
    sex = report_json.get("patient_sex")
    classifications = get_lookup().classify_many(
        report_json.get("lab_results", []), sex=sex
    )

    payload: List[Dict] = []
    for c in classifications:
        name = c.matched_test or c.test_query
        record: Dict = {
            "test": name,
            "value": _fmt_number(
                c.value_in_reference_unit if c.value_in_reference_unit is not None else c.value
            ),
            "unit": c.reference_unit or c.unit_query or "",
            "test_name": name,
            "status": "NOT_CHECKED" if c.status == NOT_EVALUATED else c.status,
        }
        rng = _reference_range_text(c)
        if rng:
            record["reference_range"] = rng
        else:
            # No range exists for a result we refused to check, so the reason
            # goes in its place rather than a fabricated range.
            record["why"] = reason_text(c.reason)
        if c.caveats:
            record["notes"] = c.caveats
        payload.append(record)
    return payload


def build_summary_prompt(report_json: Dict) -> str:
    """Compose the grounded user turn for the summary.

    Instructions first, then the results as a JSON array. The JSON format
    matches the fine-tuning data, so the model is asked to do the task it was
    trained on rather than to read a prose table it has never seen.
    """
    payload = build_results_payload(report_json)
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "LAB RESULTS (JSON). The status of each result was computed for you and "
        "is correct; explain it, never recalculate it.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Write the explanation now."
    )


def generate_medical_summary(report_json: Dict) -> str:
    """Generate a patient-friendly summary, grounded and read at grade 8.

    Pipeline: deterministic statuses -> grounded prompt -> BioMistral ->
    Flesch-Kincaid revision loop. Falls back to the template writer whenever the
    model cannot load or run, and in stub mode.
    """
    global _llm_pipeline

    lab_results = report_json.get("lab_results", [])
    if not lab_results:
        raise ValueError("Cannot generate summary: report contains no lab results.")

    if STUB_MODELS:
        print("[STUB] MEDREPORT_STUB_MODELS=1 - using the template summary writer.")
        return _finalise_readability(generate_fallback_summary(report_json), generate=None)

    prompt = build_summary_prompt(report_json)

    try:
        if _llm_pipeline is None:
            _llm_pipeline = BioMistralPipeline()
        draft = _llm_pipeline.generate(prompt)
        return _finalise_readability(draft, generate=_llm_pipeline.generate)
    except Exception as e:
        print(f"[FALLBACK_WARNING] Failed to run BioMistral LLM summary generation: {e}")
        print("[FALLBACK] Running template-based fallback summary generation...")
        return _finalise_readability(generate_fallback_summary(report_json), generate=None)


def _finalise_readability(text: str, generate) -> str:
    """Run the grade-8 revision loop and log the outcome.

    With `generate=None` (stub or fallback paths) this only measures, so the
    reported grade is still visible in the Space logs and in tests.
    """
    if generate is None:
        grade = flesch_kincaid_grade(text)
        if grade is not None:
            print(f"[READABILITY] grade {grade:.1f} (no revision - template output)")
        return text

    result = revise_to_grade(
        text,
        generate=generate,
        target_grade=READABILITY_TARGET_GRADE,
        max_rounds=READABILITY_MAX_ROUNDS,
    )
    print(f"[READABILITY] {result.summary()}")
    for step in result.history:
        print(f"[READABILITY]   {step}")
    return result.text


# Words that signal the patient is describing how they feel rather than asking
# about a number. The assigned novel task is a two-way conversation, so these
# are acknowledged instead of being parsed as a test name.
_SYMPTOM_WORDS = (
    'tired', 'fatigue', 'exhausted', 'weak', 'dizzy', 'headache', 'breath',
    'pain', 'ache', 'nausea', 'fever', 'cold', 'hair', 'sleep', 'appetite',
    'feel', 'feeling', 'symptom', 'worried', 'anxious',
)


def generate_fallback_chat_response(message: str, report_context=None) -> str:
    query = str(message or "").strip().lower()
    if not query:
        return "Please ask a question about your lab results."

    # Same normalisation as the model path: the context may arrive as a dict, a
    # bare list, or a JSON string, and only dict entries can be read.
    report_context, _ = split_report_context(report_context)

    # With no results at all we must not claim anything about them. The old
    # code fell through to "all your parameters are within the normal ranges",
    # which asserts a clean bill of health from zero information.
    if not report_context:
        return (
            "I don't have your results loaded yet. Please upload your report on "
            "the main screen, then ask me again."
        )

    results_by_name = {}
    if report_context:
        for result in report_context:
            for key in (result.get('test_name'), result.get('test')):
                if key:
                    results_by_name[str(key).lower()] = result

    # Longest name first, so "absolute neutrophil count" wins over "neutrophil".
    for test_key in sorted(results_by_name, key=len, reverse=True):
        if test_key in query:
            result = results_by_name[test_key]
            name = result.get('test_name') or result.get('test')
            val = result.get('value')
            unit = result.get('unit', '') or ''
            status = result.get('status', 'UNKNOWN')
            ref_text = result.get('reference_text')
            reason = result.get('reason')

            if status == 'UNKNOWN':
                why = {
                    'TEST_NOT_IN_REFERENCE_TABLE': "this test is not in our reference table",
                    'UNIT_MISMATCH': "the units on your report don't match our reference table",
                    'QUALITATIVE_ANALYTE': "this test is reported as a description, not a number",
                    'BODY_FLUID_NO_FIXED_RANGE': "body-fluid results are read against a matching blood sample",
                    'NOMOGRAM_REQUIRED': "this test is read against an age chart",
                    'SUSPECTED_UNIT_MISMATCH': "the units on your report look unusual for this test",
                }.get(reason, "we could not match it to a reference range")
                return (
                    f"Your report shows **{name}: {val} {unit}**. I can't say whether that is "
                    f"high or low, because {why}. Please ask your doctor to read this one for you."
                )

            ref_str = f" The normal range is **{ref_text}**." if ref_text else ""
            if status in ('HIGH', 'LOW'):
                status_desc = f"That is **{status.lower()}er than the normal range**."
            else:
                status_desc = "That is **within the normal range**."

            caveats = result.get('caveats') or []
            caveat_str = f"\n\nNote: {caveats[0]}" if caveats else ""

            return (
                f"Your **{name}** is **{val} {unit}**. {status_desc}{ref_str}{caveat_str}"
                "\n\nIf this concerns you, bring it up with your doctor."
            )

    # The patient is describing symptoms rather than naming a test.
    if any(word in query for word in _SYMPTOM_WORDS):
        abnormal = [
            r for r in (report_context or [])
            if r.get('status') in ('HIGH', 'LOW')
        ]
        if abnormal:
            names = ', '.join(
                f"**{r.get('test_name') or r.get('test')}** ({r.get('status').lower()})"
                for r in abnormal[:3]
            )
            return (
                "Thank you for telling me. I can't diagnose what is causing that, and how you "
                f"feel may have nothing to do with these results. Your report does show {names}. "
                "Please tell your doctor about this symptom and show them these results — that "
                "combination is exactly what helps them work it out."
            )
        return (
            "Thank you for telling me. I can't diagnose what is causing that. Every result in "
            "your report that we could check was within its normal range, so please describe "
            "this symptom to your doctor, who can look further."
        )

    if "abnormal" in query or "attention" in query or "worry" in query or "high" in query or "low" in query:
        abnormal_list = []
        if report_context:
            for result in report_context:
                status = result.get('status')
                if status in ['HIGH', 'LOW']:
                    name = result.get('test_name') or result.get('test')
                    val = result.get('value')
                    unit = result.get('unit', '')
                    abnormal_list.append(f"**{name}** ({val} {unit} - {status})")
        if abnormal_list:
            return (
                f"The results requiring attention in your report are: {', '.join(abnormal_list)}.\n\n"
                "Dynamic AI interpretation is temporarily unavailable. We recommend discussing these flagged results with a healthcare professional."
            )
        else:
            return "All the parsed parameters in your report lie comfortably within the normal reference ranges."

    # General fallback
    return (
        "I am your MedReport AI Assistant. Dynamic AI interpretation is temporarily unavailable, but I can report your extracted lab values. "
        "Ask me about specific tests (e.g. 'What is my hemoglobin level?') or ask 'Which values are abnormal?' "
        "Please discuss any concerning results with a healthcare professional."
    )



def generate_chat_response(message: str, report_context=None, history: Optional[List] = None, summary: Optional[str] = None) -> str:
    """
    Exposes a single clean entrypoint to get a chat response.
    Reuses the BioMistral model, falling back to a rule-based chatbot if unavailable.
    """
    global _llm_pipeline

    if STUB_MODELS:
        print("[STUB] MEDREPORT_STUB_MODELS=1 - using the rule-based chat responder.")
        return generate_fallback_chat_response(message, report_context)

    try:
        if _llm_pipeline is None:
            _llm_pipeline = BioMistralPipeline()
        reply = _llm_pipeline.generate_chat(message, report_context, history, summary=summary)

        # The adapter is fine-tuned on the SUMMARY task, so a chat prompt that
        # carries the full results can look enough like that task for it to
        # ignore the question and re-emit the whole report. Asking "Explain my
        # high White Blood Cells" returned a twelve-line summary of every
        # result. That is not an answer, so hand over to the deterministic
        # responder, which addresses the specific test that was asked about.
        if looks_like_a_summary(reply):
            print("[CHAT] model returned a report summary instead of an answer; "
                  "using the grounded rule-based responder.")
            return generate_fallback_chat_response(message, report_context)
        return reply
    except Exception as e:
        print(f"[FALLBACK_WARNING] BioMistral chat model failed to load or run: {e}")
        print("[FALLBACK] Running rule-based chatbot fallback...")
        return generate_fallback_chat_response(message, report_context)

