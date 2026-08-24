# MedReport AI

Turns a photo or PDF of a lab report into a plain-English explanation, plus a
chat assistant grounded in the patient's own results.

> This root README is the **developer guide**. It carries no Hugging Face Space
> frontmatter on purpose — each Space gets its own README from `deploy/`, since
> one directory cannot be three Spaces.

## Architecture

```
browser ──► medical-report-ai-ui      (public, static)   React + Vite, no secrets
        ──► medical-report-ai-proxy   (public, ZeroGPU)  holds HF_TOKEN
        ──► medical-report-ai         (private, ZeroGPU) the pipeline
```

The proxy exists so the token never reaches a browser. Do not "simplify" it by
calling the backend directly from the frontend.

### The pipeline

| Stage | What runs | Needs GPU |
|---|---|---|
| 1. OCR | PaddleOCR + rotation correction | yes |
| 2. NER | fine-tuned ClinicalBERT, BIO tagging | yes |
| 3. **Grounding** | `backend/app/reference_ranges/` — status by arithmetic | **no** |
| 4. Explanation | BioMistral-7B QLoRA + readability loop | yes |

**Stage 3 is the safety boundary.** HIGH / LOW / NORMAL is computed by comparing
numbers to a 653-row reference table, never by the language model. The model is
given the status and asked to explain it. Where a status cannot be computed the
result is `UNKNOWN` with a machine-readable `reason`, and the model is
instructed to say so rather than guess.

## Local development without a GPU

Everything most likely to be wrong is CPU-testable. Only model *quality* needs a
GPU.

```bash
pip install -r requirements-dev.txt
export MEDREPORT_STUB_MODELS=1        # `export`, not a bare assignment - a
                                      # plain VAR=1 line is not passed to
                                      # child processes

cd backend
python3 test_grounding.py                         # 27 tests: grounding, chat, readability
python3 app/reference_ranges/test_range_lookup.py # 32 tests: ranges, units, refusals

cd .. && python3 app.py                           # real endpoints, no models
```

Or set it for a single command without exporting:

```bash
MEDREPORT_STUB_MODELS=1 python3 app.py
```

Confirm stub mode is actually on - the startup log must contain:

```
[STUB] Reading report text directly, skipping OCR.
[STUB] MEDREPORT_STUB_MODELS=1 - using the template summary writer.
```

If those lines are missing the app will try to download BioMistral and
ClinicalBERT.

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Command 'python' not found` | Ubuntu/WSL ships `python3` only | use `python3`, or `sudo apt install python-is-python3` |
| `When localhost is not accessible, a shareable link must be created` | port 7860 was busy, so Gradio moved to 7861 and its own reachability check failed | free 7860 (`pkill -f app.py`), or `GRADIO_SERVER_PORT=7870 python3 app.py` |
| Same error with a corporate proxy set | `http_proxy` intercepts localhost | `export NO_PROXY=localhost,127.0.0.1` |
| Summaries look identical every time | stub mode is on | unset `MEDREPORT_STUB_MODELS` |

In stub mode the app also accepts a `.txt` of report text, so you can exercise
OCR-downstream behaviour without PaddleOCR:

```
Patient Name : A Patient        Sex : Male
Hemoglobin               14.2      g/dL         13.0-17.0
Absolute Neutrophils     4500      cells/mcL    1500-7500
```

Drive both endpoints exactly as the proxy does:

```python
from gradio_client import Client, handle_file
c = Client("http://127.0.0.1:7860")
print(c.view_api())                              # /chat MUST list 3 parameters
res = c.predict(handle_file("report.txt"), api_name="/analyze_report")
ctx = res["report"]["lab_results"] if isinstance(res, dict) else res[0]["report"]["lab_results"]
print(c.predict("what is my hemoglobin?", [], ctx, api_name="/chat"))
```

### Frontend

```bash
npm install
npm run dev        # http://localhost:5173
npx vitest run     # 41 tests
npm run build
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HF_TOKEN` | — | **required on the backend and proxy Spaces** |
| `MEDREPORT_STUB_MODELS` | unset | `1` = no models; CPU dev only, never in production |
| `MEDREPORT_TARGET_GRADE` | `8.0` | Flesch-Kincaid target |
| `MEDREPORT_MAX_REVISIONS` | `2` | revision rounds; each is a full 7B generation |

## Deploying

```bash
./deploy/push_space.sh backend     # push first, then verify view_api()
./deploy/push_space.sh proxy
./deploy/push_space.sh frontend
```

After the backend deploy, confirm `/chat` publishes **three** parameters
(`message`, `history`, `report_context`). If it publishes two, a `gr.State` has
crept back into the endpoint's `inputs` and the chatbot will answer with no
knowledge of the patient's report — without raising any error.

## Things that will bite you

- **`gr.State` is not an API input.** Gradio omits it from the published
  signature and silently drops the client's argument. API endpoints use
  `gr.JSON`; `gr.State` is for the interactive tab only.
- **No system role.** BioMistral's chat template raises
  `Only user and assistant roles are supported!`. Instructions are prepended to
  the first user turn. Roles must also strictly alternate, so
  `enforce_alternation()` repairs the history server-side.
- **Pin Gradio.** Unpinned resolves to 6.x, where `gr.Chatbot(type="messages")`
  raises and the Chatbot payload schema changes.
- **Reference ranges are broad published adult values**, not lab-validated, and
  contain no paediatric or pregnancy ranges. See
  `backend/app/reference_ranges/README.md`.

## Tests

| Suite | Count | Needs GPU |
|---|---|---|
| `backend/test_grounding.py` | 27 | no |
| `backend/app/reference_ranges/test_range_lookup.py` | 32 | no |
| `npx vitest run` | 41 | no |
