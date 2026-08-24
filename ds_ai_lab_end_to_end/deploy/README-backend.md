---
title: Medical Report AI
emoji: 🩺
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.49.1
python_version: "3.10.13"
app_file: app.py
pinned: false
short_description: Private GPU backend - OCR, NER and grounded explanations
---

# Medical Report AI — backend

Private Space. Runs the full pipeline and exposes two API endpoints. It is not
called by browsers directly: the public proxy Space holds the token and forwards
to it.

| Endpoint | Inputs | Returns |
|---|---|---|
| `/analyze_report` | `file` | `{report: {...}, summary: "..."}` |
| `/chat` | `message`, `history`, `report_context` | `str` |

## Pipeline

1. **OCR** — PaddleOCR + rotation correction
2. **NER** — fine-tuned ClinicalBERT BIO token classifier
3. **Grounding** — `app/reference_ranges/` computes HIGH/LOW/NORMAL by
   arithmetic against a 653-row reference table. The model never decides status.
4. **Explanation** — BioMistral-7B QLoRA, then a Flesch-Kincaid loop that
   revises until the text reads at US grade 8 or below.

## Hardware

Set **ZeroGPU** in Space settings. Free personal accounts may host up to 2
ZeroGPU Spaces (verified email, account older than 30 days).

Quota is charged to the **visitor**, not the Space owner: unauthenticated
visitors get 2 minutes of GPU time per day, free accounts 5, PRO 40. Keep the
`@spaces.GPU(duration=...)` values tight - a shorter declared duration also
improves queue priority.

## Required secrets

- `HF_TOKEN` — read access for the base model and the LoRA adapter.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MEDREPORT_STUB_MODELS` | unset | `1` skips all model loading (CPU dev only) |
| `MEDREPORT_TARGET_GRADE` | `8.0` | readability target |
| `MEDREPORT_MAX_REVISIONS` | `2` | revision rounds; each is a full generation |
| `BIOMISTRAL_ADAPTER_PATH` | `samtaaihub/biomistral-medical-summary-lora` | LoRA adapter |
| `CLINICALBERT_NER_PATH` | `samtaaihub/clinicalbert-medical-report-ner` | NER model |

**Do not set `MEDREPORT_STUB_MODELS` on the deployed Space.** It disables the
models and serves template output.
