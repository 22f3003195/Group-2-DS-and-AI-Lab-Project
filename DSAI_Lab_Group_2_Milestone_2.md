# DS&AI Lab Project [Term May 2026]
## Intelligent Medical Report Analysis System

---

# MILESTONE-2: Dataset Identification & Preparation

---

**Indian Institute of Technology Madras**

**GROUP: 2**

| Name | Email | GitHub Usernames | Signature |
|------|-------|------------------|-----------|
| Bryan David Robinson | 22f3002277@ds.study.iitm.ac.in | brilo1819 | |
| Ritwik Trivedi | 22f1000120@ds.study.iitm.ac.in | ritwiktrivedi | |
| Rajat Shrivastava | 22f3003195@ds.study.iitm.ac.in
 | 22f3003195 | |
| Samta Ranka | 23f1001316@ds.study.iitm.ac.in | 23f1001316 | S.R. |
| Shivendra Patel | 21f2001310@ds.study.iitm.ac.in | shivendra1717 | S.P.|

---

## 1. Data Sources

For this project, we have identified and utilized datasets for two distinct purposes: training the NER model and testing the complete end-to-end pipeline.

### 1.1 Training Data Sources

#### 1.1.1 Dataset for NER Model Training (ClinicalBERT)

**Objective:** Fine-tune ClinicalBERT to accurately identify and extract lab test names, numerical values, units, and reference ranges from medical report text.

**Dataset Used:** MTSamples and MIMIC-III (combined and annotated).

**MTSamples Dataset**

| Attribute | Details |
|-----------|---------|
| **Source** | Scraped from mtsamples.com, available on Kaggle (tboyle10/medicaltranscriptions) |
| **Format** | CSV with 6 columns: `description`, `medical_specialty`, `sample_name`, `transcription`, `keywords` |
| **Size** | 4,999 total records; 2,416 lab-related records identified through keyword filtering (48.3% of total) |
| **License** | Open access (HIPAA-compliant, de-identified) |
| **Specialties** | 40 unique medical specialties (Top: Surgery 1,103, Consult 516, Cardiovascular/Pulmonary 372) |

**MIMIC-III Dataset**

| Attribute | Details |
|-----------|---------|
| **Source** | MIT Lab for Computational Physiology, available via PhysioNet |
| **Version** | v1.4 (released September 2016) |
| **Access** | Credentialed access required (CITI training, Data Use Agreement) |
| **Ethics** | De-identified, IRB-approved, HIPAA-compliant |
| **Sample from Kaggle** | Available on Kaggle [https://www.kaggle.com/datasets/ihssanened/mimic-iii-clinical-databaseopen-access] |
| **Format** | CSV files including LABEVENTS, D_LABITEMS, ADMISSIONS, PATIENTS |
| **Size (as loaded from Kaggle sample)** | LABEVENTS: 76,074 rows; D_LABITEMS: 753 rows (laboratory test definitions); ADMISSIONS: 129 rows (patient admission records) |
| **Patients** | 100 unique patients |

#### 1.1.2 Dataset for LLM Fine-Tuning (Patient-Friendly Explanation Generation)

**Objective:** Fine-tune a small, open-source LLM (e.g., FLAN-T5 or LLaMA-3.2-1B) to generate contextual, educational explanations from extracted lab data (e.g., "Creatinine is a waste product filtered by your kidneys. A result of 1.8 mg/dL is above the normal range...").

**Dataset Type:** Medical Knowledge Dataset.

**Dataset Sources:**

- **MTSamples (Secondary):** Lab-related transcriptions containing explanatory text about what test results mean (e.g., "The elevated creatinine level is consistent with acute renal failure"). Used to extract additional explanation-text pairs.

### 1.2 Testing Data Sources

**Sample Medical Report PDFs/Images**

| Attribute | Details |
|-----------|---------|
| **Source** | Curated collection from publicly available diagnostic lab websites and sample report repositories |
| **Format** | PDF and image files (PNG, JPG) containing structured laboratory reports |
| **Sample Sources** | Labsmart Sample Reports (https://www.labsmartlis.com/sample-reports); Drlogy Pathology Lab Report Templates (https://www.drlogy.com/pathology-lab-software/report-format); Additional diagnostic lab sample reports from Google Images and other publicly available sources |
| **Size** | 50-100 sample reports covering diverse layouts, test panels, and formats |
| **Purpose** | To evaluate the complete pipeline (OCR → NER → Abnormality Detection → Dashboard Generation) on realistic report formats that mimic what end-users would upload |

**Why Testing Data is Separate from Training Data:**

| Aspect | Training Data (MTSamples/MIMIC-III) | Testing Data (Sample PDFs/Images) |
|--------|--------------------------------------|-----------------------------------|
| **Format** | Plain text/CSV | PDF/Image |
| **Content** | Clinical narratives and structured lab notes | Complete lab reports with layout, formatting, branding |
| **Purpose** | Train NER model to recognize entities in text | Test end-to-end pipeline on realistic documents |
| **Privacy** | De-identified; publicly available | Publicly available samples; no real patient data |

**Justification for Using Sample Reports for Testing:**

Since real patient medical reports cannot be used due to privacy regulations (HIPAA, GDPR) and patient confidentiality, we have curated a collection of sample reports from publicly available sources. These samples accurately represent the real-world format and structure of laboratory reports, allowing us to effectively test our pipeline without compromising patient privacy.

---

## 2. Dataset Description

### 2.1 MTSamples Features

- `transcription`: Full clinical note text (primary feature for our entity extraction task)
- `medical_specialty`: Medical specialty category (40 unique specialties)
- `description`: Brief description of the case
- `keywords`: Associated medical terms

**Data Distribution (from script output):**

- Total records: 4,999
- Lab-related records (filtered): 2,416 (48.3%)
- Medical specialties: 40 unique

**Top 10 specialties:**

| Specialty | Count |
|-----------|-------|
| Surgery | 1,103 |
| Consult - History and Phy. | 516 |
| Cardiovascular / Pulmonary | 372 |
| Orthopedic | 355 |
| Radiology | 273 |
| General Medicine | 259 |
| Gastroenterology | 230 |
| Neurology | 223 |
| SOAP / Chart / Progress Notes | 166 |
| Obstetrics / Gynecology | 160 |

### 2.2 MIMIC-III Features (relevant to our project)

**LABEVENTS:** 76,074 lab event records with columns:
- `subject_id`: Patient identifier
- `hadm_id`: Hospital admission identifier
- `itemid`: Laboratory test code
- `charttime`: Timestamp
- `value`: Text value
- `valuenum`: Numeric value
- `valueuom`: Unit of measurement
- `flag`: Abnormal flag

**D_LABITEMS:** 753 laboratory test definitions with:
- `itemid`: Test code
- `label`: Test name
- `fluid`: Fluid type
- `category`: Test category

**ADMISSIONS:** 129 admission records

**Preprocessed MIMIC-III Data (from script output):**

- Valid numerical results: 65,280 rows (after filtering for `valuenum` not null, > 0, < 10000)
- Lab tests matched to common reference ranges: 18 common lab tests
- Synthetic reports created from patient data: 100 reports
- Patients: 100 unique patients

### 2.3 Testing Dataset Features

- **Document Format:** PDF/Image with embedded text
- **Components:** Patient details section, test results table (test name, value, unit, reference range, abnormal flags), doctor/signature section, report metadata
- **Layout Diversity:** Multiple templates from different labs
- **Customization Elements:** Various combinations of: Turnaround time display (with/without TAT), QR code presence, Page numbers, Highlighting styles for abnormal results (red text vs. bold text), Test order variations

---

## 3. Dataset Preprocessing

### 3.1 MTSamples Preprocessing

1. Load the MTSamples CSV file from Kaggle (4,999 rows)
2. Filter for lab-related reports using keyword matching:
   - Keywords: `'lab'`, `'laboratory'`, `'test'`, `'result'`, `'value'`, `'glucose'`, `'hemoglobin'`, `'creatinine'`, `'potassium'`, `'sodium'`, `'lipid'`, `'cholesterol'`, `'triglyceride'`, `'thyroid'`, `'cbc'`, `'complete blood count'`, `'metabolic panel'`, `'chemistry'`
3. Extract lab-related reports: 2,416 records (48.3% of total)
4. Validate reports have lab values using regex pattern matching

### 3.2 MIMIC-III Preprocessing

1. Load LABEVENTS (76,074 rows), D_LABITEMS (753 rows), and ADMISSIONS (129 rows) CSV files from Kaggle
2. Merge LABEVENTS with D_LABITEMS to map `itemid` to human-readable test labels
3. Filter for valid numerical results:
   - `valuenum` is not null
   - `valuenum` > 0
   - `valuenum` < 10000
4. Result: 65,280 valid numerical lab events
5. Create synthetic reports for each patient:
   - Group by `subject_id` (100 unique patients)
   - Filter for 18 common lab tests with predefined reference ranges
   - Require at least 3 lab tests per patient
   - Create structured report text with test names, values, units, and abnormality flags
6. Result: 100 synthetic reports from MIMIC-III data

### 3.3 Combined Dataset Creation

- Combine MIMIC-III synthetic reports (100) and MTSamples lab-related reports (2,412)
- Total: 2,512 combined reports
  - MIMIC-III: 100 (4.0%)
  - MTSamples: 2,412 (96.0%)
- Add source labels to distinguish between datasets
- Export to CSV and JSONL formats

### 3.4 Entity Annotation

- Rule-based annotation using `MedicalEntityAnnotator` class with regex patterns for:
  - TEST names (31 patterns)
  - UNIT patterns (13 patterns)
  - REFERENCE range patterns
  - VALUE patterns (numerical values)

**Results:**

- Training: 1,759 reports annotated
- Validation: 376 reports annotated
- Test: 377 reports annotated
- Total entities found: 52,768

### 3.5 Dataset Splitting

- **Split Strategy:** 70/15/15 (train/validation/test)
- **Stratification:** Maintain source distribution across splits
- **Implementation:** Train-test split with `test_size=0.15`, then split remaining with `test_size=0.176` (to achieve 15% validation)
- **Results:**
  - Training: 1,759 reports (70%)
  - Validation: 376 reports (15%)
  - Test: 377 reports (15%)
- **Random Seed:** 42 (for reproducibility)

### 3.6 Testing Dataset (Sample Reports)

- **Quality:** All samples are sourced from legitimate lab software providers and diagnostic labs
- **Format Consistency:** Reports follow standard lab report formats, ensuring realistic representation
- **Completeness:** Each sample contains all required elements (test names, values, units, reference ranges)
- **Limitation:** Limited number of templates available from public sources (mitigated by collecting from multiple sources)

---

## 4. Dataset Statistics (from Script Output)

### 4.1 Text Length Statistics

| Split | Mean | Min | Max | Std Dev |
|-------|------|-----|-----|---------|
| Training | 3,534 chars | 318 chars | 18,425 chars | 2,132 |
| Validation | 3,550 chars | 318 chars | 15,216 chars | 2,223 |
| Test | 3,552 chars | 347 chars | 12,852 chars | 1,974 |

### 4.2 Source Distribution

| Source | Count | Percentage |
|--------|-------|------------|
| MTSamples | 2,412 | 96.0% |
| MIMIC-III | 100 | 4.0% |
| **Total** | **2,512** | **100%** |

### 4.3 Entity Annotation Results

| Split | Reports | Total Entities |
|-------|---------|----------------|
| Training | 1,759 | 52,768 |
| Validation | 376 | (processed) |
| Test | 377 | (processed) |

---

## 5. Dataset Adequacy Assessment

### 5.1 Training Data Adequacy

The combined dataset is adequate for training our medical entity extraction model:

| Requirement | MTSamples | MIMIC-III | Combined |
|-------------|-----------|-----------|----------|
| Clinical text with lab values |  Yes |  Yes (synthetic reports) |  Yes |
| Lab test names |  Varies |  Structured |  Comprehensive |
| Numeric values |  Varies |  Structured |  Good coverage |
| Reference ranges |  Limited |  Included |  Available |
| Report length |  Average 3,500 chars |  Average 3,500 chars |  Consistent |

### 5.2 Testing Data Adequacy

The curated sample report collection is adequate for testing the complete pipeline:

| Requirement | Sample Reports |
|-------------|----------------|
| Realistic report layout |  Yes (actual lab templates) |
| Diverse formats |  Yes (multiple sources, versions) |
| OCR testability |  Yes (PDF/Image format) |
| All required fields |  Yes (test, value, unit, range) |

### 5.3 Justification for Current Approach

- **MTSamples** provides rich clinical narratives with natural language variations of lab results
- **MIMIC-III** provides structured lab data with accurate test names, values, and units
- **Combined approach** ensures the NER model learns both:
  - Structured lab report format (from MIMIC-III)
  - Natural language variations (from MTSamples)

### 5.4 Future Data Expansion Plans

**Datasets Currently Being Sought:**
- Complete MIMIC-III (Full PhysioNet version): Credentialed access in progress
- MIMIC-IV: Updated version with more recent data
- eICU Collaborative Research Database: Multi-center ICU lab results

**Justification for Future Data:**
- **MIMIC-III Complete:** Will provide larger patient cohort for better model generalization
- **MIMIC-IV:** More recent data for improved clinical relevance
- **eICU:** Different patient population (ICU focus) for broader validation

**Synthea Dataset:**
- **Status:** Downloaded but not used for training
- **Reason:** Contains synthetic data; real patient data (MIMIC-III, MTSamples) is preferred for training a clinically accurate model

**Testing Data:**
- **Status:** Actively being collected from publicly available sources
- **Purpose:** Validate complete pipeline on realistic document layouts

### 5.5 Augmentation Strategy

**For Training:**
- Combine MTSamples (narrative) with MIMIC-III (structured) to enhance coverage of lab-related entities
- Additional datasets planned: MIMIC-IV, Synthea, eICU, NHANES
- Expand reference range dictionary to cover more lab tests as needed

**For Testing:**
- Expand collection by sourcing additional sample reports from more diagnostic lab websites
- Generate additional synthetic reports (using the template approach) to supplement rare report formats
- Create variations of existing samples by modifying test values to cover abnormal scenarios

---

## 6. Reference Ranges

Predefined reference ranges for **29 common lab tests** have been compiled for the deterministic abnormality detection module:

Hemoglobin, Creatinine, Glucose, Platelets, Potassium, Sodium, Chloride, Calcium, Magnesium, Albumin, Bilirubin, WBC, RBC, HCT, BUN, INR, PT, PTT, AST, ALT, Alkaline Phosphatase, Total Protein, Globulin, Iron, Ferritin, TSH, T4, HbA1c, Uric Acid, Phosphorus

These ranges will be expanded as more lab tests are encountered in the sample reports and future datasets.

---

## 7. Data Leakage Prevention

- **Patient-based splitting:** MIMIC-III reports are grouped by patient ID (100 unique patients)
- **No overlap:** Each patient's data appears in only one split
- **Stratified splitting:** Source distribution maintained across splits
- **Testing samples** are completely separate from training data
- Training and testing data come from **different sources** (training: MTSamples/MIMIC-III, testing: sample report PDFs)
- **Random seed (42):** Ensures reproducibility
- **Source labels:** Allow tracking of dataset origin

---

## 8. Sources to be Added

The following additional datasets will be added to expand training data coverage:

- MIMIC-IV (updated lab data, more recent records)
- Synthea (synthetic health records, open access)
- eICU Collaborative Research Database (ICU lab results)
- NHANES Laboratory Data (US national health survey)
- Additional sample report templates for testing

---

## 9. Reproducibility Documentation

| Aspect | Implementation |
|--------|----------------|
| **Random Seed** | 42 (set in `train_test_split`) |
| **Data Loading** | Direct CSV loading from Kaggle paths |
| **Preprocessing** | Fully documented in script with print statements |
| **Splitting** | Stratified splitting with `stratify=combined_df['source']` |
| **Output Formats** | CSV (tabular) and JSONL (training-ready) |
| **Annotation** | Rule-based with regex patterns (fully documented) |

---

## 10. Summary: Training vs Testing Data

| Dataset | Status | Records | Usage |
|---------|--------|---------|-------|
| MTSamples |  Loaded | 2,416 lab-related | Training |
| MIMIC-III (Kaggle sample) |  Loaded | 100 synthetic reports | Training |
| Combined Dataset |  Created | 2,512 reports | Training/Val/Test |
| Annotated Dataset |  Created | 52,768 entities | NER Training |
| Sample Reports (Testing) |  Collecting | 50-100 planned | Testing |
| MIMIC-III Complete |  In progress | Full dataset | Future expansion |
| MIMIC-IV |  Planned | Full dataset | Future expansion |
| eICU |  Planned | Full dataset | Future expansion |
| Synthea |  Available but not used | - | Synthetic data (not preferred) |