import os
import re
import json
from typing import Dict, List, Optional, Tuple

from app.reference_ranges.range_lookup import get_lookup, parse_value, NOT_EVALUATED
from app.reference_ranges.build_reference_db import normalize_name, parse_range

# torch/transformers are only needed for the ClinicalBERT token classifier.
# Importing them lazily keeps NERProcessor - and therefore the whole grounded
# range-lookup path - usable on a CPU-only machine with no ML stack installed,
# which is what MEDREPORT_STUB_MODELS=1 relies on.
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForTokenClassification
except ImportError:  # pragma: no cover - exercised on CPU-only dev machines
    torch = None
    AutoTokenizer = AutoModelForTokenClassification = None

class LexiconCorrectorAllTests:
    """
    Applies lexicon correction to ALL tests WITHOUT corrupting units.
    """
    
    CORRECTIONS = [
        # ============================================
        # HEMATOLOGY - Complete Blood Count
        # ============================================
        (r'(?i)\bwbc\s*count\b', 'WBC Count'),
        (r'(?i)\bwbc\b', 'WBC Count'),
        (r'(?i)\bwhite\s+blood\s+cell\s+count\b', 'WBC Count'),
        (r'(?i)\bleukocytes?\b', 'WBC Count'),
        
        (r'(?i)\brbc\s*count\b', 'RBC'),
        (r'(?i)\brbc\b', 'RBC'),
        (r'(?i)\bred\s+blood\s+cell\s+count\b', 'RBC'),
        
        (r'(?i)\bhemoglobin\b', 'Hemoglobin'),
        (r'(?i)\bhaemoglobin\b', 'Hemoglobin'),
        (r'(?i)\bhgb\b', 'Hemoglobin'),
        
        (r'(?i)\bhematocrit\b', 'Hematocrit'),
        (r'(?i)\bhct\b', 'Hematocrit'),
        
        (r'(?i)\bplatelet\s+count\b', 'Platelet Count'),
        (r'(?i)\bplatelets?\s+count\b', 'Platelet Count'),
        (r'(?i)\bplt\b', 'Platelet Count'),
        (r'(?i)\bplatelet\b', 'Platelet Count'),

        # ============================================
        # RBC INDICES
        # ============================================
        (r'(?i)\bmcv\b', 'MCV'),
        (r'(?i)\bmean\s+corpuscular\s+volume\b', 'MCV'),
        
        (r'(?i)\bmch\b', 'MCH'),
        (r'(?i)\bmean\s+corpuscular\s+hemoglobin\b', 'MCH'),
        
        (r'(?i)\bmchc\b', 'MCHC'),
        (r'(?i)\bmean\s+corpuscular\s+hemoglobin\s+concentration\b', 'MCHC'),
        
        (r'(?i)\brdw\b', 'RDW'),
        (r'(?i)\bred\s+cell\s+distribution\s+width\b', 'RDW'),

        # ============================================
        # DIFFERENTIAL
        # ============================================
        (r'(?i)\bneutrophils?\b', 'Neutrophils'),
        (r'(?i)\bneutrphils?\b', 'Neutrophils'),
        (r'(?i)\bneutraphils?\b', 'Neutrophils'),
        
        (r'(?i)\blymphocytes?\b', 'Lymphocytes'),
        (r'(?i)\blymchecytes\b', 'Lymphocytes'),
        (r'(?i)\blympecytes\b', 'Lymphocytes'),
        (r'(?i)\blymphocites\b', 'Lymphocytes'),
        (r'(?i)\blymcytes\b', 'Lymphocytes'),
        (r'(?i)\blymphycytes\b', 'Lymphocytes'),
        
        (r'(?i)\bmonocytes?\b', 'Monocytes'),
        (r'(?i)\beosinophils?\b', 'Eosinophils'),
        (r'(?i)\beostnophils\b', 'Eosinophils'),
        (r'(?i)\bbasophils?\b', 'Basophils'),
        (r'(?i)\bbraophila\b', 'Basophils'),

        # ============================================
        # IRON STUDIES - SAFE
        # ============================================
        (r'(?i)\bserum\s+iron\b', 'Iron'),
        (r'(?i)\biron\b', 'Iron'),
        (r'(?i)\btibc\b', 'TIBC'),
        (r'(?i)\btotal\s+iron\s+binding\s+capacity\b', 'TIBC'),
        (r'(?i)\bferritin\.?\b', 'Ferritin'),
        (r'(?i)\bferritin\s+level\b', 'Ferritin'),
        (r'(?i)\btransferrin\s+saturation\b', 'Transferrin Saturation'),
        (r'(?i)\btransferrin\s+saturation\s*\(%\)\b', 'Transferrin Saturation'),
        (r'(?i)\biron\s+saturation\b', 'Transferrin Saturation'),

        # ============================================
        # VITAMINS - SAFE
        # ============================================
        (r'(?i)\bvitamin\s+b12\b', 'Vitamin B12'),
        (r'(?i)\bb12\b', 'Vitamin B12'),
        (r'(?i)\bvitamin812\b', 'Vitamin B12'),
        (r'(?i)\bcobalamin\b', 'Vitamin B12'),
        
        (r'(?i)\bfolate\b', 'Folate'),
        (r'(?i)\bfolic\s+acid\b', 'Folate'),
        
        (r'(?i)\b25-oh\s+vitamin\s+d\b', '25-OH Vitamin D'),
        (r'(?i)\b25\s+hydroxy\s+vitamin\s+d\b', '25-OH Vitamin D'),
        (r'(?i)\bvitamin\s+d\b', '25-OH Vitamin D'),
        (r'(?i)\b25-oh\s+d\b', '25-OH Vitamin D'),

        # ============================================
        # THYROID - SAFE
        # ============================================
        (r'(?i)\bthyroid\s+stimulating\s+hormone\b', 'Thyroid Stimulating Hormone'),
        (r'(?i)\bthyroid\s+stimulatinghormone\b', 'Thyroid Stimulating Hormone'),
        (r'(?i)\btsh\b', 'Thyroid Stimulating Hormone'),
        
        (r'(?i)\bthyroxine\s*\(t4\)\b', 'Thyroxine (T4)'),
        (r'(?i)\btotal\s+t4\b', 'Thyroxine (T4)'),
        (r'(?i)\bt4\b', 'Thyroxine (T4)'),
        (r'(?i)\bthyroxine\s+free\b', 'Thyroxine (T4), Free'),
        (r'(?i)\bfree\s+t4\b', 'Thyroxine (T4), Free'),
        
        (r'(?i)\btriiodothyronine\s*\(t3\)\b', 'Triiodothyronine (T3)'),
        (r'(?i)\btotal\s+t3\.?\b', 'Triiodothyronine (T3)'),
        (r'(?i)\bt3\.?\b', 'Triiodothyronine (T3)'),
        (r'(?i)\bfree\s+t3\b', 'Free T3'),

        # ============================================
        # LIPIDS - SAFE
        # ============================================
        # These rules are applied CUMULATIVELY, so a general rule placed before a
        # specific one corrupts the very names the specific rule exists to fix.
        # A bare \bcholesterol\b rule used to run first, so "HDL Cholesterol"
        # became "Cholesterol, HDL, Total" and "LDL Cholesterol (Calc.)" became
        # "Cholesterol, LDL, Calculated, Cholesterol, Total (Calc.)" - a name no
        # lookup can resolve. Two rules therefore apply here:
        #   1. most specific first;
        #   2. the catch-all is guarded so it cannot re-fire on a name an
        #      earlier rule already normalised (those all read "Cholesterol, X").
        (r'(?i)\bldl\s+cholesterol\s*,?\s*(?:\(\s*calc[a-z.]*\s*\)|calculated)', 'Cholesterol, LDL, Calculated'),
        (r'(?i)\bldl\s+cholesterol\b', 'Cholesterol, LDL, Calculated'),
        (r'(?i)\bldl\s+calculated\b', 'Cholesterol, LDL, Calculated'),
        (r'(?i)\bhdl\s+cholesterol\b', 'Cholesterol, HDL'),
        (r'(?i)\bcholesterol\s+ratio\b', 'Cholesterol Ratio (Total/HDL)'),
        (r'(?i)\bcholesterol\s*,\s*total\b', 'Cholesterol, Total'),
        (r'(?i)\btotal\s+cholesterol\b', 'Cholesterol, Total'),

        # Bare qualifiers, only where they are not already part of a corrected
        # name (i.e. not immediately after "Cholesterol,").
        (r'(?i)(?<!, )\bhdl\b(?!\s*[,)])', 'Cholesterol, HDL'),
        (r'(?i)(?<!, )\bldl\b(?!\s*[,)])', 'Cholesterol, LDL, Calculated'),

        # Catch-all LAST, and only for a bare "Cholesterol" that no earlier rule
        # has touched: not preceded by a qualifier, not already followed by a
        # comma or by "Ratio".
        (r'(?i)(?<!hdl )(?<!ldl )(?<!vldl )\bcholesterol\b(?!\s*(?:,|ratio))', 'Cholesterol, Total'),

        (r'(?i)\btriglycerides\b', 'Triglycerides'),
        (r'(?i)\btrig\b', 'Triglycerides'),

        # ============================================
        # CHEMISTRY - SAFE
        # ============================================
        (r'(?i)\bpotassium\b', 'Potassium'),
        (r'(?i)\bsodium\b', 'Sodium'),
        (r'(?i)\bchloride\b', 'Chloride'),
        (r'(?i)\bbicarbonate\b', 'Bicarbonate'),
        (r'(?i)\bcalcium\b', 'Calcium'),
        (r'(?i)\bmagnesium\b', 'Magnesium'),
        (r'(?i)\bphosphate\b', 'Phosphate'),
        (r'(?i)\bphosphorus\b', 'Phosphate'),

        # ============================================
        # RENAL - SAFE
        # ============================================
        (r'(?i)\bblood\s+urea\s+nitrogen\b', 'BUN'),
        (r'(?i)\burea\s+nitrogen\b', 'BUN'),
        (r'(?i)\bbun\b', 'BUN'),
        (r'(?i)\bcreatinine\b', 'Creatinine'),
        (r'(?i)\buric\s+acid\b', 'Uric Acid'),
        (r'(?i)\burate\b', 'Uric Acid'),
        (r'(?i)\banion\s+gap\b', 'Anion Gap'),

        # ============================================
        # LIVER - SAFE
        # ============================================
        (r'(?i)\b(alanine\s+aminotransferase\s*\(alt\)|alt)\b', 'Alanine Aminotransferase (ALT)'),
        (r'(?i)\b(aspartate\s+aminotransferase\s*\(ast\)|ast)\b', 'Asparate Aminotransferase (AST)'),
        (r'(?i)\balkaline\s+phosphatase\b', 'Alkaline Phosphatase'),
        (r'(?i)\balp\b', 'Alkaline Phosphatase'),
        (r'(?i)\btotal\s+bilirubin\b', 'Bilirubin, Total'),
        (r'(?i)\bdirect\s+bilirubin\b', 'Bilirubin, Direct'),
        (r'(?i)\bindirect\s+bilirubin\b', 'Bilirubin, Indirect'),
        (r'(?i)\balbumin\b', 'Albumin'),
        (r'(?i)\btotal\s+protein\b', 'Protein, Total'),
        (r'(?i)\bldh\b', 'LDH'),
        (r'(?i)\blactate\s+dehydrogenase\b', 'LDH'),

        # ============================================
        # COAGULATION - SAFE
        # ============================================
        (r'(?i)\binr\s*\(pt\)\b', 'INR(PT)'),
        (r'(?i)\binr\b', 'INR(PT)'),
        (r'(?i)\binternational\s+normalized\s+ratio\b', 'INR(PT)'),
        (r'(?i)\bpt\b', 'PT'),
        (r'(?i)\bprothrombin\s+time\b', 'PT'),
        (r'(?i)\bptt\b', 'PTT'),
        (r'(?i)\bpartial\s+thromboplastin\s+time\b', 'PTT'),
        (r'(?i)\baptt\b', 'PTT'),
        (r'(?i)\bfibrinogen\b', 'Fibrinogen'),
        (r'(?i)\bd-dimer\b', 'D-Dimer'),

        # ============================================
        # CARDIAC - SAFE
        # ============================================
        (r'(?i)\btroponin\s+i\b', 'Troponin I'),
        (r'(?i)\btroponin\s+t\b', 'Troponin T'),
        (r'(?i)\btroponin\b', 'Troponin I'),
        (r'(?i)\bbnp\b', 'BNP'),
        (r'(?i)\bbrain\s+natriuretic\s+peptide\b', 'BNP'),
        (r'(?i)\bnt-probnp\b', 'BNP'),
        (r'(?i)\bck\b', 'Creatine Kinase (CK)'),
        (r'(?i)\bcreatine\s+kinase\b', 'Creatine Kinase (CK)'),
        (r'(?i)\bck-mb\b', 'Creatine Kinase, MB Isoenzyme'),

        # ============================================
        # HORMONES - SAFE
        # ============================================
        (r'(?i)\bcortisol\b', 'Cortisol'),
        (r'(?i)\btestosterone\b', 'Testosterone'),
        (r'(?i)\bfree\s+testosterone\b', 'Testosterone, Free'),
        (r'(?i)\bestradiol\b', 'Estradiol'),
        (r'(?i)\bprogesterone\b', 'Progesterone'),
        (r'(?i)\bhcg\b', 'HCG'),
        (r'(?i)\bprolactin\b', 'Prolactin'),
        (r'(?i)\blh\b', 'LH'),
        (r'(?i)\bfsh\b', 'FSH'),
        (r'(?i)\bpth\b', 'PTH'),
        (r'(?i)\bparathyroid\s+hormone\b', 'PTH'),
        (r'(?i)\binsulin\b', 'Insulin'),
        (r'(?i)\baldosterone\b', 'Aldosterone'),
        (r'(?i)\brenin\b', 'Renin'),

        # ============================================
        # GASES - SAFE
        # ============================================
        (r'(?i)\bph\b', 'pH'),
        (r'(?i)\bpco2\b', 'pCO2'),
        (r'(?i)\bpartial\s+pressure\s+co2\b', 'pCO2'),
        (r'(?i)\bpo2\b', 'pO2'),
        (r'(?i)\bpartial\s+pressure\s+o2\b', 'pO2'),
        (r'(?i)\boxygen\s+saturation\b', 'Oxygen Saturation'),

        # ============================================
        # OTHER - SAFE
        # ============================================
        (r'(?i)\bamylase\b', 'Amylase'),
        (r'(?i)\blipase\b', 'Lipase'),
        (r'(?i)\bpsa\b', 'Prostate Specific Antigen'),
        (r'(?i)\bcrp\b', 'C-Reactive Protein'),
        (r'(?i)\besr\b', 'ESR'),
        (r'(?i)\blactate\b', 'Lactate'),
        (r'(?i)\bammonia\b', 'Ammonia'),
        (r'(?i)\bdigoxin\b', 'Digoxin'),
        (r'(?i)\blithium\b', 'Lithium'),
        (r'(?i)\bphenytoin\b', 'Phenytoin'),
        (r'(?i)\bcarbamazepine\b', 'Carbamazepine'),
        (r'(?i)\bvalproic\s+acid\b', 'Valproic Acid'),
        (r'(?i)\btheophylline\b', 'Theophylline'),
        (r'(?i)\bgentamicin\b', 'Gentamicin'),
        (r'(?i)\bvancomycin\b', 'Vancomycin'),
        (r'(?i)\bacetaminophen\b', 'Acetaminophen'),
        (r'(?i)\bsalicylate\b', 'Salicylate'),
        (r'(?i)\bethanol\b', 'Ethanol'),
        (r'(?i)\betoh\b', 'Ethanol'),

        # Fix "Vitamin812" -> "Vitamin B12"
        (r'Vitamin812', 'Vitamin B12'),
        
        # Fix "Lymphecytes" -> "Lymphocytes"
        (r'(?i)\blymchecytes\b', 'Lymphocytes'),
        (r'(?i)\blympecytes\b', 'Lymphocytes'),
        (r'(?i)\blymphycytes\b', 'Lymphocytes'),

        # ============================================
        # CLEAN UP - Remove duplicates
        # ============================================
        (r'\b(Cholesterol),\s+Total,\s+Total\b', r'\1, Total'),
        (r'\b(Cholesterol),\s+Cholesterol,\s+HDL,\s+Total\b', r'\1, HDL, Total'),
        (r'\b(LDL),\s+Calculated\s+Cholesterol,\s+Total\b', r'\1, Calculated, Cholesterol, Total'),
        (r'\b(Total)\s+(Total)\b', r'\1'),
        (r'\b(Cholesterol)\s+(Cholesterol)\b', r'\1'),
        (r'\b(HDL)\s+(HDL)\b', r'\1'),
        (r'\b(LDL)\s+(LDL)\b', r'\1'),
    ]
    
    def __init__(self):
        self.compiled_patterns = [(re.compile(pattern, re.IGNORECASE), replacement) for pattern, replacement in self.CORRECTIONS]
        self.corrections_made = []
    
    def correct_line(self, line: str) -> str:
        if not line:
            return line
        
        original = line
        corrected = line
        
        # Apply all corrections
        for pattern, replacement in self.compiled_patterns:
            if pattern.search(corrected):
                corrected = pattern.sub(replacement, corrected)
        
        # Clean up extra spaces
        corrected = re.sub(r'\s+', ' ', corrected).strip()
        
        # Remove duplicate words
        corrected = re.sub(r'\b(\w+)\s+\1\b', r'\1', corrected)
        
        if corrected != original:
            self.corrections_made.append((original[:40], corrected[:40]))
        
        return corrected
    
    def correct_text(self, text: str) -> str:
        if not text:
            return text
        
        self.corrections_made = []
        lines = text.split('\n')
        corrected_lines = [self.correct_line(line) for line in lines]
        
        if self.corrections_made:
            print(f"\n  Lexicon corrections applied: {len(self.corrections_made)}")
            for orig, fixed in self.corrections_made[:15]:
                print(f"    '{orig}' -> '{fixed}'")
        
        return '\n'.join(corrected_lines)


class ClinicalBERTNER:
    def __init__(self, model_path: str, device: str = "cpu"):
        print(f"\nLoading ClinicalBERT model from: {model_path}")
        # Check local folder path existence if it's not a Hugging Face repo ID format
        if not ('/' in model_path and not os.path.exists(model_path)):
            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"ClinicalBERT model folder not found at: '{model_path}'. "
                    f"Please ensure you place the model weights there."
                )
        
        token = os.environ.get("HF_TOKEN")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, token=token)
        self.model = AutoModelForTokenClassification.from_pretrained(
            model_path, 
            ignore_mismatched_sizes=True,
            token=token
        )
        self.model.eval()
        self.device = torch.device(device)
        self.model.to(self.device)
        self.id2label = self.model.config.id2label
        print(f"Model loaded on {self.device}")
    
    def predict(self, text: str) -> Tuple[List[str], List[str]]:
        if not text or len(text.strip()) < 5:
            return [], []
        all_tokens = []
        all_tags = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            tokens = line.split()
            if not tokens:
                continue
            chunk_size = 180
            for start in range(0, len(tokens), chunk_size):
                chunk = tokens[start:start + chunk_size]
                encoding = self.tokenizer(
                    chunk,
                    truncation=True,
                    padding='max_length',
                    max_length=256,
                    is_split_into_words=True,
                    return_tensors='pt'
                )
                word_ids = encoding.word_ids(batch_index=0)
                input_ids = encoding['input_ids'].to(self.device)
                attention_mask = encoding['attention_mask'].to(self.device)
                with torch.no_grad():
                    outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
                    predictions = torch.argmax(outputs.logits, dim=2)
                pred_tags = []
                prev_word_idx = None
                for i, word_idx in enumerate(word_ids):
                    if word_idx is not None and word_idx != prev_word_idx:
                        if word_idx < len(chunk):
                            pred_tags.append(self.id2label[predictions[0][i].item()])
                            prev_word_idx = word_idx
                while len(pred_tags) < len(chunk):
                    pred_tags.append('O')
                all_tokens.extend(chunk)
                all_tags.extend(pred_tags[:len(chunk)])
        return all_tokens, all_tags


# Generic lab-report layout words that are never analyte names. This list is
# deliberately free of patient and laboratory names: the previous version
# hardcoded YASH / PATEL / HIREN / SHAH / DRLOGY from one sample PDF, which did
# nothing for a fresh report and silently dropped rows for any real patient
# surnamed Patel or Shah. Words that are substrings of real test names
# (BLOOD, COUNT, ABSOLUTE, DIFFERENTIAL) are also gone - the structural filter
# in `process` handles those without risking a legitimate analyte.
REPORT_FURNITURE = {
    'AGE', 'YEARS', 'SEX', 'GENDER', 'PID', 'UHID', 'MRN',
    'REPORTED', 'REGISTERED', 'COLLECTED', 'COLLECTION', 'RECEIVED',
    'SAMPLE', 'SPECIMEN', 'GENERATED', 'PRINTED', 'PAGE',
    'INVESTIGATION', 'INVESTIGATIONS', 'RESULT', 'RESULTS',
    'REFERENCE', 'RANGE', 'VALUE', 'UNIT', 'UNITS', 'METHOD',
    'PATHOLOGY', 'LABORATORY', 'LAB', 'REF', 'BY', 'DR', 'DR.',
    'AM', 'PM', 'NAME', 'ADDRESS', 'PHONE', 'DOCTOR', 'PATIENT',
}


class NERProcessor:
    """Assembles BIO entities into lab results and attaches a grounded status.

    Reference-range comparison is delegated entirely to
    `app.reference_ranges`, which parses the 653-row workbook once at build
    time and compares with arithmetic. This class no longer carries its own
    range table: the previous 21-row dict was matched with
    `if key in test_upper or test_upper in key`, which resolved MCHC to MCH's
    range and every ABSOLUTE <cell> count to that cell's percentage range,
    reporting four healthy CBC values as HIGH.
    """

    def __init__(self, patient_sex: str | None = None, report_ranges: Dict | None = None):
        self.lookup = get_lookup()
        self.patient_sex = patient_sex
        # {normalized test name: range text the LAB printed}, filled by the
        # pipeline from the report's own reference column.
        self.report_ranges: Dict[str, str] = report_ranges or {}

    def process(self, tokens: List[str], ner_tags: List[str]) -> Dict:
        if not tokens or not ner_tags:
            return {'lab_results': []}
        entities = []
        i = 0
        while i < len(tokens):
            if ner_tags[i].startswith('B-'):
                entity_type = ner_tags[i][2:]
                entity_tokens = [tokens[i]]
                j = i + 1
                while j < len(tokens) and ner_tags[j].startswith('I-'):
                    entity_tokens.append(tokens[j])
                    j += 1
                entities.append({
                    'type': entity_type,
                    'text': ' '.join(entity_tokens),
                    'start': i,
                    'end': j
                })
                i = j
            else:
                i += 1
        lab_results = []
        i = 0
        while i < len(entities):
            if entities[i]['type'] == 'TEST':
                lab = {'test': entities[i]['text']}
                i += 1
                while i < len(entities):
                    curr = entities[i]
                    if curr['type'] == 'TEST':
                        break
                    if curr['type'] == 'VALUE' and 'value' not in lab:
                        lab['value'] = curr['text']
                        i += 1
                    elif curr['type'] == 'UNIT' and 'unit' not in lab:
                        lab['unit'] = curr['text']
                        i += 1
                    else:
                        i += 1
                if 'value' in lab:
                    lab_results.append(lab)
            else:
                i += 1
        cleaned_results = []
        seen_tests = set()
        for lab in lab_results:
            test = lab.get('test', '').upper()
            if test in REPORT_FURNITURE:
                continue
            if test in seen_tests:
                continue
            seen_tests.add(test)
            if 'MCHC' in test and lab.get('unit') == 'pg':
                lab['unit'] = 'g/dL'
            test_lower = test.lower()
            if 'hemoglobin' in test_lower:
                lab['test'] = 'Hemoglobin'
            elif 'packed cell' in test_lower or 'pcv' in test_lower:
                lab['test'] = 'HCT'
                lab['test_name'] = 'Hematocrit'
            elif 'mean corpuscular' in test_lower or 'mcv' in test_lower:
                lab['test'] = 'MCV'
            elif 'absolute neutrophils' in test_lower:
                lab['test'] = 'Absolute Neutrophils'
            elif 'absolute lymphocytes' in test_lower:
                lab['test'] = 'Absolute Lymphocytes'
            elif 'absolute eosinophils' in test_lower:
                lab['test'] = 'Absolute Eosinophils'
            elif 'absolute monocytes' in test_lower:
                lab['test'] = 'Absolute Monocytes'
            elif 'absolute basophils' in test_lower:
                lab['test'] = 'Absolute Basophils'
            elif 'platelet' in test_lower and 'count' in test_lower:
                lab['test'] = 'Platelet Count'
            elif 'rbc' in test_lower and 'count' in test_lower:
                lab['test'] = 'RBC Count'
            
            self.apply_reference_range(lab)

            # Structural filter, replacing the old hardcoded name blacklist:
            # a row that resolves to no reference test AND carries no unit is
            # almost always report furniture (a header, a date, a patient name)
            # rather than an analyte.
            if lab.get('status') == 'UNKNOWN' and not lab.get('unit'):
                continue

            cleaned_results.append(lab)
        return {'lab_results': cleaned_results}

    def _classify_from_report_range(self, lab: Dict) -> Optional[Dict]:
        """Judge a result against the range printed on the report itself.

        Returns None when the report showed no usable range for this test, so
        the caller keeps the honest refusal. No unit conversion is attempted:
        the printed range is in the report's own units, which are by definition
        the units of the value beside it.
        """
        if not self.report_ranges:
            return None
        key = normalize_name(lab.get('test', ''))
        raw = self.report_ranges.get(key)
        if not raw:
            return None

        parsed = parse_range(raw)
        bound = parsed.get('bounds', {}).get('any')
        if parsed['kind'] == 'non_numeric' or not bound:
            return None

        value = parse_value(lab.get('value'))
        if value is None:
            return None

        low, high = bound['low'], bound['high']
        if low is not None and value < low:
            status = 'LOW'
        elif high is not None and value > high:
            status = 'HIGH'
        else:
            status = 'NORMAL'

        unit = lab.get('unit') or ''
        return {
            'test_name': lab.get('test'),
            'status': status,
            'ref_min': low,
            'ref_max': high,
            'reference_text': f"{raw} {unit}".strip(),
            'reference_source': 'report',
            'reason': None,
            'caveats': ["range taken from your report, not from our reference table"],
        }

    def apply_reference_range(self, lab: Dict) -> Dict:
        """Attach a deterministic status, reference range and provenance to one result.

        The status is computed by arithmetic against the reference table. It is
        never inferred, and where it cannot be computed the result says so with
        a machine-readable reason instead of guessing.
        """
        c = self.lookup.classify(
            lab.get('test', ''),
            lab.get('value'),
            lab.get('unit'),
            sex=self.patient_sex,
        )

        # Our table could not judge this one - but the report may have printed
        # its own reference range, which is better evidence than anything we
        # hold: it is that lab's validated range on that instrument. This is
        # what rescues tests we simply do not carry (Anion Gap) and results
        # whose units OCR mangled beyond repair.
        if c.status == NOT_EVALUATED:
            fallback = self._classify_from_report_range(lab)
            if fallback:
                lab.update(fallback)
                return lab

        lab['test_name'] = c.matched_test or lab.get('test')
        # The frontend's union is HIGH | LOW | NORMAL | UNKNOWN, so the two
        # extra states are mapped onto it. `reason` carries the detail.
        lab['status'] = {
            'NOT_EVALUATED': 'UNKNOWN',
            'PRESENT': 'HIGH',
        }.get(c.status, c.status)

        lab['ref_min'] = c.reference_low
        lab['ref_max'] = c.reference_high
        lab['reference_text'] = c.reference_text
        lab['reason'] = c.reason
        lab['caveats'] = c.caveats
        lab['match_confidence'] = c.match_confidence

        if c.reference_unit:
            lab['unit'] = c.reference_unit
        if c.value_in_reference_unit is not None:
            lab['value'] = f"{c.value_in_reference_unit:g}"
        return lab
