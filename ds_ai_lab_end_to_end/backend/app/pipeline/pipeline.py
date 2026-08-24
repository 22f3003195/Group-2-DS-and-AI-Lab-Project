import os
import re
import traceback
from typing import Dict

from app.config import CLINICALBERT_NER_PATH, ALLOWED_EXTENSIONS, STUB_MODELS
from app.pipeline.ocr import MedicalReportOCR, ValueLineFilter
from app.pipeline.ner import LexiconCorrectorAllTests, ClinicalBERTNER, NERProcessor
from app.reference_ranges.build_reference_db import normalize_name

# 20 rows in the reference table are sex-specific, including Hemoglobin and
# Hematocrit - the two headline values on any CBC. Without sex the lookup falls
# back to the union of the male and female ranges and attaches a caveat saying
# so, which is safe but weaker, so it is worth reading off the report header.
_SEX_PATTERNS = [
    re.compile(r'\b(?:sex|gender)\s*[:\-]?\s*(male|female|m|f)\b', re.I),
    re.compile(r'\b(\d{1,3})\s*(?:years?|yrs?|y)\s*[/,]\s*(male|female|m|f)\b', re.I),
    re.compile(r'\b(male|female)\b', re.I),
]


def extract_patient_sex(raw_text: str) -> str | None:
    """Read patient sex from the report header. Returns 'M', 'F' or None.

    Deliberately conservative: an unreadable or absent header yields None, and
    the lookup then widens the range rather than assuming one.
    """
    if not raw_text:
        return None
    head = raw_text[:1500]  # demographics live in the header, not the results
    for pattern in _SEX_PATTERNS:
        m = pattern.search(head)
        if m:
            token = m.group(m.lastindex or 1)
            if token and token[0].upper() in ('M', 'F'):
                return token[0].upper()
    return None


# The reference column the LAB ITSELF printed. Matching it means a test we do
# not hold can still be checked, and it is strictly better evidence than our
# broad published values: it is that laboratory's own validated range, on that
# instrument. "4.0 - 11.0", "< 200", "> 40", "0.70-1.30".
_REPORT_RANGE = re.compile(
    r"(?:"
    r"(?P<lo>\d+(?:\.\d+)?)\s*[-\u2013\u2014]\s*(?P<hi>\d+(?:\.\d+)?)"
    r"|(?P<op>[<>]=?|\u2264|\u2265)\s*(?P<bound>\d+(?:\.\d+)?)"
    r")\s*$"
)


def extract_report_ranges(text: str) -> Dict[str, str]:
    """Map a test name to the reference range printed beside it on the report.

    Keyed by the same normalisation the lookup uses, so the two can be joined.
    Only a range at the END of a line is taken: on a lab report the reference
    column is the last one, and anchoring there avoids mistaking the RESULT for
    a range on lines like "Glucose 98 mg/dL 70 - 99".
    """
    found: Dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip().rstrip("*|")
        if not line:
            continue
        m = _REPORT_RANGE.search(line)
        if not m:
            continue
        head = line[:m.start()].strip()
        # The test name is the leading non-numeric text of the line.
        name = re.match(r"^([A-Za-z][A-Za-z0-9 ,./()#%+&-]*?)(?=\s+[\d<>])", head)
        if not name:
            continue
        key = normalize_name(name.group(1))
        if not key or key in found:
            continue
        found[key] = m.group(0).strip()
    return found


class MedicalReportPipeline:
    def __init__(self, model_path: str = CLINICALBERT_NER_PATH):
        self.ocr = MedicalReportOCR()
        self.filter = ValueLineFilter()
        self.lexicon = LexiconCorrectorAllTests()
        self.processor = NERProcessor()
        self.model_path = model_path
        self.ner = None

    def load_models(self):
        """Lazy loads the ClinicalBERT model to ensure we only load it once."""
        if self.ner is None:
            from app.config import DEVICE
            try:
                self.ner = ClinicalBERTNER(self.model_path, device=DEVICE)
            except Exception as e:
                raise RuntimeError(f"Failed to load ClinicalBERT model: {e}")

    def process_file(self, file_path: str) -> Dict:
        # 1. Missing file check
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: '{file_path}'")

        # 2. Invalid file type check
        ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
        allowed = set(ALLOWED_EXTENSIONS) | ({'txt'} if STUB_MODELS else set())
        if ext not in allowed:
            raise ValueError(f"Invalid file type '.{ext}'. Supported types: {', '.join(sorted(allowed))}")

        # 3. Text extraction
        if STUB_MODELS and ext == 'txt':
            # CPU-only development path: feed the pipeline report text directly
            # so PaddleOCR (and a GPU) are not needed to exercise everything
            # downstream of extraction.
            print("\n[STUB] Reading report text directly, skipping OCR.")
            raw_text = open(file_path, encoding='utf-8', errors='replace').read()
        else:
            try:
                print("\nExtracting text with OCR...")
                raw_text = self.ocr.extract(file_path)
            except Exception as e:
                traceback.print_exc()
                raise RuntimeError(f"OCR processing failed: {str(e)}")

        # 4. Empty OCR result check
        if not raw_text or not raw_text.strip():
            raise ValueError("We couldn't read any text from this file. Try a clearer photo with good lighting.")

        # 5. Read demographics BEFORE filtering strips the header away
        patient_sex = extract_patient_sex(raw_text)
        self.processor.patient_sex = patient_sex
        print(f"Patient sex detected: {patient_sex or 'not found (union range will be used)'}")

        print("Filtering lines with numerical values...")
        filtered_text = self.filter.filter_lines(raw_text)
        
        print("Applying lexicon correction...")
        corrected_text = self.lexicon.correct_text(filtered_text)

        # Capture the lab's own reference column before NER discards the layout.
        self.processor.report_ranges = extract_report_ranges(corrected_text)
        if self.processor.report_ranges:
            print(f"Reference ranges printed on the report: "
                  f"{len(self.processor.report_ranges)}")

        # 6. Model Inference with error handling
        try:
            if STUB_MODELS:
                raise RuntimeError("MEDREPORT_STUB_MODELS=1: skipping ClinicalBERT")
            self.load_models()  # Ensures model is loaded once
            print("Running ClinicalBERT NER inference...")
            tokens, ner_tags = self.ner.predict(corrected_text)
            print("Processing NER results...")
            result = self.processor.process(tokens, ner_tags)
        except Exception as e:
            print(f"[FALLBACK_WARNING] Failed to load ClinicalBERT model or run inference: {e}")
            print("[FALLBACK] Running rule-based fallback parser...")
            result = self.run_rule_based_fallback(corrected_text)

        if not result.get('lab_results'):
            raise ValueError("We couldn't detect any lab results in this report. Verify it is a laboratory report.")
        result['success'] = True
        result['patient_sex'] = patient_sex
        
        if result['lab_results']:
            result['summary'] = {
                'total_tests': len(result['lab_results']),
                'abnormal_count': len([l for l in result['lab_results'] if l.get('status') in ['HIGH', 'LOW']]),
                'text': f"Found {len(result['lab_results'])} lab tests."
            }
        else:
            result['summary'] = {
                'total_tests': 0,
                'abnormal_count': 0,
                'text': 'No lab results found.'
            }
            
        return result

    # A reference-range column looks like "13.0-17.0" or "4.0 - 11.0" and must
    # never be mistaken for a unit.
    _RANGE_LIKE = re.compile(r'^\d+(?:\.\d+)?\s*[-–—]\s*\d')
    _RESULT_LINE = re.compile(
        # `+` matters: without it "Sodium (Na+)" and "Potassium (K+)" fail to
        # match at all and the two commonest electrolytes vanish silently.
        r'^(?P<name>[A-Za-z][A-Za-z0-9 ,./()#%+&-]*?)\s+'    # test name
        r'(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)\s*'             # first number = result
        r'(?P<rest>.*)$'                                      # unit, then maybe a range
    )

    def run_rule_based_fallback(self, text: str) -> dict:
        """Parse `Name  value  unit  [reference range]` lines without a model.

        Used when ClinicalBERT is unavailable and by MEDREPORT_STUB_MODELS=1.
        The unit is taken as the first token after the value that is not itself
        a numeric range, so the report's own reference column is discarded
        rather than being glued onto the unit.
        """
        lab_results = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            match = self._RESULT_LINE.match(line)
            if not match:
                continue

            test_name = match.group('name').strip(' .:-')
            val = match.group('value').strip()
            unit = ''
            for token in match.group('rest').split():
                if self._RANGE_LIKE.match(token):
                    break          # reached the reference column; stop
                if re.fullmatch(r'\d+(?:\.\d+)?', token):
                    break          # a bare number is not a unit
                unit = token
                break
            if test_name:
                lab_results.append({
                    'test': test_name,
                    'value': val,
                    'unit': unit
                })
        
        tokens = []
        ner_tags = []
        for lab in lab_results:
            test_words = lab['test'].split()
            if not test_words:
                continue
            tokens.append(test_words[0])
            ner_tags.append('B-TEST')
            for word in test_words[1:]:
                tokens.append(word)
                ner_tags.append('I-TEST')
            tokens.append(lab['value'])
            ner_tags.append('B-VALUE')
            if lab['unit']:
                unit_words = lab['unit'].split()
                if unit_words:
                    tokens.append(unit_words[0])
                    ner_tags.append('B-UNIT')
                    for uw in unit_words[1:]:
                        tokens.append(uw)
                        ner_tags.append('I-UNIT')
        return self.processor.process(tokens, ner_tags)


# Thread-safe global pipeline instance cache
_pipeline_instance = None

def process_medical_report(file_path: str) -> Dict:
    """
    Exposes a clean single entry point to process a medical report.
    Loads ClinicalBERT model once when needed.
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = MedicalReportPipeline()
    return _pipeline_instance.process_file(file_path)
