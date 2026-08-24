import os

# Base directory of the backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Stage 2: the fine-tuned token classifier that turns OCR text into
# (TEST, VALUE, UNIT) triples. From clinicalbert_ner_enhanced_final.zip,
# uploaded to this account so the pipeline does not depend on a repo owned by
# someone else - the weights are identical to samtaaihub's copy
# (sha256 25e57834abb0c2ec...), which is what it used to load.
#
# DistilBERT-based (its base, medicalai/ClinicalBERT, is a DistilBERT), 5 BIO
# labels: O, B-TEST, I-TEST, B-VALUE, B-UNIT. Reported F1 0.9997 - but on a
# held-out split of the same GENERATED corpus it was trained on, so it does not
# describe accuracy on real OCR output. See test_classification_report.txt and
# training_configuration.json in the model repo.
CLINICALBERT_NER_PATH = os.environ.get(
    "CLINICALBERT_NER_PATH",
    "ritwiktrivedi/clinicalbert-ner-enhanced"
)

BIOMISTRAL_BASE_MODEL = os.environ.get(
    "BIOMISTRAL_BASE_MODEL",
    "BioMistral/BioMistral-7B"
)

# Adapter (2). Chosen because its fine-tuning records carry BOTH the computed
# status and the reference range:
#
#   [{"test": "Glucose", "value": 179.0, "unit": "mg/dL", "test_name": "Glucose",
#     "status": "HIGH", "reference_range": "70\u201399 mg/dL"}]
#
# so the model can quote the range it is explaining. Adapter (3) was trained on
# the four bare keys (test/value/unit/status) and never saw a range.
#
# IMPORTANT: `status` is still computed by app.reference_ranges before the model
# is called - see NERProcessor.apply_reference_range. The model is given the
# verdict and the range so it can explain them; it does not decide either.
# The alternative is ritwiktrivedi/biomistral-lora-grounded (adapter 3).
BIOMISTRAL_ADAPTER_PATH = os.environ.get(
    "BIOMISTRAL_ADAPTER_PATH",
    "ritwiktrivedi/biomistral-lora-infers-flags"
)

# ---------------------------------------------------------------------------
# Local development without a GPU
# ---------------------------------------------------------------------------
# MEDREPORT_STUB_MODELS=1 skips loading BioMistral and ClinicalBERT entirely and
# runs the deterministic paths instead: the rule-based NER fallback and the
# template summary writer. Everything that is most likely to be wrong - the
# reference-range lookup, unit conversion, status arithmetic, the grounding
# block, the readability loop, and every wire contract between the three Spaces
# - is exercised unchanged. Only model *quality* needs a GPU.
STUB_MODELS = os.environ.get("MEDREPORT_STUB_MODELS", "").strip() in ("1", "true", "yes")

# Readability target for the patient explanation (US grade level).
READABILITY_TARGET_GRADE = float(os.environ.get("MEDREPORT_TARGET_GRADE", "8.0"))
# Each revision round is another full 7B generation against the ZeroGPU budget,
# so this stays deliberately small.
READABILITY_MAX_ROUNDS = int(os.environ.get("MEDREPORT_MAX_REVISIONS", "2"))

# File configuration
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB limit

# PaddleOCR configuration
PADDLE_LANG = "en"

# Computing device configuration
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    DEVICE = "cpu"
