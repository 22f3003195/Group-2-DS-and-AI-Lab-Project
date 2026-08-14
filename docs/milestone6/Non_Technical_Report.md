# DS&AI Lab Project [Term May 2026]
## Intelligent Medical Report Analysis System

### Milestone - 6 Report: Non-Technical Report

**Indian Institute of Technology Madras**  
**GROUP: 2**

---

### Team Members

| Name | Email | GitHub Username | Signature |
| :--- | :--- | :--- | :--- |
| **Shivendra Patel** | `21f2001310@ds.study.iitm.ac.in` | `shivendra1717` | S.P |
| **Rajat Srivastava** | `22f3003195@ds.study.iitm.ac.in` | `22f3003195` | R.S |
| **Samta Ranka** | `23f1001316@ds.study.iitm.ac.in` | `23f1001316` | S.R |
| **Ritwik Trivedi** | `22f1000120@ds.study.iitm.ac.in` | `ritwiktrivedi` | R.T |
| **Bryan David Robinson** | `22f3002277@ds.study.iitm.ac.in` | `brilo1819` | B.D.R |

---

# Non-Technical Report: Intelligent Medical Report Analysis System

## Executive Summary

Medical laboratory reports are designed primarily for healthcare professionals, filled with complex medical jargon (e.g., creatinine, triglycerides), dense reference ranges, and tabular layouts. For ordinary patients, reading these reports can trigger anxiety or lead to misinterpretations. Furthermore, relying on generic conversational AI tools can be risky because they may alter or fabricate ("hallucinate") critical numerical health figures.

To bridge this communication gap, we developed an **Intelligent Medical Report Analysis System**. This system automatically processes uploaded lab report documents (PDFs or images), extracts numerical values and test names without alteration, flags abnormal health metrics, and provides clear, plain-English explanations written at an accessible reading level. It achieves this while strictly prioritizing patient privacy by enabling local, on-device execution so sensitive health records never need to be uploaded to public cloud servers.


---

## The Problem

When patients receive their lab results, they face three primary challenges:

1. **Language & Comprehension Barrier:** Terms like *alkaline phosphatase* or *hemoglobin A1c* are not everyday language. Patients often search online for answers, leading to unnecessary worry over minor, non-critical deviations.
2. **Numerical Risk in AI:** Standard public AI chatbots can misread tables or alter specific numbers when generating long text summaries. In medical contexts, misreading a value like 1.4 as 14 can significantly alter the meaning of a test result.
3. **Privacy Concerns:** Uploading private medical documents to third-party online AI services raises serious data privacy and regulatory concerns.

---

## Our Solution

Our system provides a reliable, patient-friendly assistant that transforms raw medical lab documents into a structured summary and clear explanations.

![Alt text](./images/Screenshot%202026-08-10%20172418.png)
### How It Works (Step-by-Step)

1. **Document Reading:** The user uploads a lab report (as an image file, scanned photo, or digital PDF).
2. **Text & Table Parsing:** The system scans the document using optical character recognition (OCR) technology, handling rotated images, table structures, and low-resolution text.
3. **Medical Information Extraction:** A specialized clinical medical model identifies entity details: test names, numerical values, and measurement units (such as $\text{mg/dL}$).
4. **Guaranteed Numerical Accuracy (No Hallucinations):** The extraction of numbers is completely separated from text generation. A rule-based verification script evaluates whether the extracted lab value is normal, high, or low based on established medical reference ranges. The AI language model is strictly forbidden from changing any numerical figures.
5. **Plain-English Explanations:** A specialized medical language model converts the flagged results into clear, empathetic descriptions that explain what the test measures, why a result might be high or low, and what sensible next steps to take.
6. **Interactive Multi-Turn Conversation:** Patients can ask follow-up questions (e.g., *"What does 'filtered by the kidneys' mean?"* or *"Should I be worried?"*) in a stateful chat session. The assistant provides contextual, calm explanations and consistently reminds users to consult their physician for clinical decisions.

---

## Key Benefits & Real-World Impact

| Key Feature | Generic Public AI | Our Medical Assistant |
| :--- | :--- | :--- |
| **Numerical Accuracy** | Risk of hallucinating or changing lab numbers | **100% Numerical Fidelity** via strict separation of code and AI generation |
| **Patient Privacy** | Requires uploading documents to cloud servers | **Local Execution**, keeping sensitive data on your device |
| **Document Support** | Prefers copied/pasted text; struggles with bad scans | **Handles Rotated Scans, Images, & PDFs** automatically |
| **Output Structure** | Dense, broad text paragraphs | **Visual Scorecard + Plain-Language Explanations** |
| **Safety Guardrails** | May offer unverified advice or diagnoses | **Deferral to Physicians**; never offers diagnoses or prescriptions |

---

## Target Audience & Uses

* **Patients & Families:** Helps individuals understand their routine blood work, metabolic panels, or lipid profiles before meeting with their physician, reducing uncertainty and enabling informed conversations.
* **Healthcare Students & Trainees:** Serves as an educational tool to quickly parse structured laboratory data, learn clinical acronyms, and practice identifying abnormal findings efficiently.
* **Clinicians & Practice Staff:** Indirectly benefits doctors by providing patients with better pre-meeting comprehension, reducing administrative explanation burden during consultations.

---

## System Performance at a Glance

* **Medical Entity Extraction Accuracy:** Exceeded **99.9% F1-score** across clinical datasets, correctly capturing test names, values, and units.
* **Image Robustness:** Successfully parsed **100% of rotated documents** and maintained a high overall success rate across standard scans, mobile screenshots, and low-quality photos.
* **Safety & Precision:** Achieved **100% numerical fidelity**, reproducing every extracted number, unit, and health status without fabricating data.

---

## Ethical Boundaries & Disclaimers

> ⚠️ **IMPORTANT MEDICAL DISCLAIMER**
> 
> * **Assistive Tool Only:** This application is designed purely to assist in report comprehension and patient education. It is not a clinical diagnostic tool and does not provide medical diagnoses, treatment recommendations, or prescriptions.
> * **Physician Collaboration:** The system explicitly encourages users to discuss all findings with a qualified healthcare professional, serving as a bridge to better doctor-patient communication rather than a replacement for professional care.
