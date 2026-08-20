# DS&AI Lab Project [Term May 2026]
## Intelligent Medical Report Analysis System

### Milestone - 6 Report: User Guide

![Alt text](./images/image2.gif)

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

# User Guide: Intelligent Medical Report Analysis System

Welcome to the **Intelligent Medical Report Analysis System**!  
This guide will walk you through how to upload your medical lab reports, interpret your results, ask follow-up questions, and ensure your private data remains secure.

---

## 1. Getting Started

The **Intelligent Medical Report Analysis System** is an accessible, privacy-focused application designed to help you make sense of complex laboratory test results.

### What You Need
* **Supported Files:** PDF documents or image files (`.jpg`, `.jpeg`, `.png`).
* **Document Types:** Routine blood panels, metabolic profiles, lipid panels, electrolyte panels, complete blood counts (CBC), and general diagnostic lab sheets.
* **Device:** Desktop browser, tablet, or smartphone.
* **Privacy Note:** The application runs local, on-device processing. Your lab reports and medical values are never uploaded to or stored on public cloud servers.

---

## 2. Step-by-Step Usage Instructions

### Step 1: Upload Your Document
1. Open the application dashboard in your browser.
2. Click the **"Upload Report"** button or drag and drop your file directly into the designated upload area.
3. If uploading a photo taken with a phone camera, ensure the document is flat and well-lit.

> **Tip:** Don't worry if your image is rotated or tilted. The system automatically corrects image orientation before reading the text.

![Alt text](./images/Screenshot%202026-08-14%20120255.png)
---

### Step 2: Review Your Interactive Health Scorecard
Once the report is processed, the system will extract test names, numerical values, and units, presenting them in a simplified summary table.
* **Normal Results:** Displayed with standard formatting.
* **Flagged Results (High / Low):** Color coded and highlighted so you can immediately see which values fall outside standard reference ranges.


![Alt text](./images/WhatsApp%20Image%202026-08-14%20at%202.16.08%20AM.jpeg)
---

### Step 3: Read Plain-English Explanations
Below the scorecard, click on any test to expand its detailed explanation. The system translates medical terminology into clear, accessible language:
* **What the test measures:** Plain-language explanation of the organ or biological system involved (e.g., kidney function, blood sugar control).
* **Why it might be flagged:** Potential common reasons for high or low readings.
* **Suggested Next Steps:** General lifestyle context or questions to ask your doctor.

#### Example Explanation
> **Glucose (Fasting) - 105 mg/dL (High)**
> * **What it measures:** Glucose is your body's main source of energy. This test measures the amount of sugar in your blood after fasting (not eating) for 8-12 hours.
> * **Why it might be high:** A slightly elevated fasting glucose may indicate prediabetes, recent meal consumption, stress, or certain medications. Your reference range (70-99 mg/dL) is the typical target for healthy individuals.
> * **What to ask your doctor:** *"Should I repeat this test? Are there lifestyle changes I should consider? Do you recommend a hemoglobin A1c test to check my average blood sugar over time?"*

---

### Step 4: Ask Follow-Up Questions (Interactive Chat)
Have specific questions about a term or result? Use the built-in chat window at the bottom of the screen.

#### Example Prompts You Can Try:
* *"What does 'Serum Creatinine' actually measure in the body?"*
* *"What are some questions I should ask my doctor about my glucose level?"*
* *"Does being dehydrated affect these results?"*
* *"How does my cholesterol compare to healthy ranges for my age?"*
* *"What lifestyle changes can help improve my LDL cholesterol?"*

---

## 3. Best Practices for Best Results

* **Clear Lighting:** When taking photos of printed pages, avoid dark shadows or harsh camera glares.
* **Full Capture:** Ensure all four corners of the page including test names, values, and units are visible.
* **Single Document Focus:** Upload one lab report at a time for optimal extraction accuracy.
* **Check File Size:** Keep files under 20MB for fastest processing.
* **Use Standard Formats:** PDF, JPG, JPEG, and PNG files work best.

---

## 4. Troubleshooting & FAQ

### Frequently Asked Questions

**Q: Can this system diagnose my condition?**  
**A:** No. This tool is strictly for educational and informational purposes. It explains what lab terms mean and flags values outside reference ranges, but it cannot diagnose diseases or prescribe treatment. Always consult a healthcare professional.

**Q: Why does my reference range look slightly different from another lab?**  
**A:** Different medical laboratories use different testing equipment and reference scales. The system uses the reference range from our database to determine whether a value is high, low, or normal.

**Q: What should I do if an image fails to upload?**  
**A:** Check that your file size is under the maximum limit (typically 20MB) and is saved as a standard format (`.pdf`, `.jpg`, `.png`). If the image is extremely blurry, retake the photo in better light.

**Q: How do I know if the system correctly read my report?**  
**A:** After upload, review the scorecard to verify that the extracted test names, values, and units match your original document. If something appears incorrect, you can re-upload a clearer image or PDF.

**Q: Is my data saved on the server?**  
**A:** No. The system processes your document using a cloud-based backend, but your lab report is not permanently stored. All processing happens in ephemeral memory—your document is analyzed, results are displayed, and then the data is cleared. No patient data is retained, logged, or used for training purposes.

**Q: Where does the processing actually happen?**  
**A:** The processing happens on cloud servers (Hugging Face ZeroGPU infrastructure). Your document is securely uploaded to the backend, processed through OCR and AI models, and results are returned to your browser. This is necessary because the AI models require GPU acceleration that cannot run in a browser.

**Q: Who can access my uploaded report??**  
**A:** Only you. Your report is processed in a temporary session and is not accessible to anyone else. The system does not store or share your medical information.

**Q: Who can access my uploaded report??**  
**A:** Only you. Your report is processed in a temporary session and is not accessible to anyone else. The system does not store or share your medical information.

**Q: What if my report has multiple pages?**  
**A:** If your report is a multi-page PDF, the system will process all pages sequentially. For image files, upload each page separately.

**Q: Can I use this on my phone?**  
**A:** Yes! The application is fully responsive and works on mobile browsers. You can take a photo directly from your phone and upload it immediately.

---

## 5. Safety & Medical Disclaimer

> ⚠️ **Important Safety Information**  
> The **Intelligent Medical Lab Report Analysis System** is an educational assistant designed to enhance health literacy and improve doctor-patient communication.  
> * **Do not** use this application for emergency medical situations.  
> * **Do not** alter, stop, or start any medication or treatment based on output from this tool.  
> * **Always** discuss your lab results directly with a licensed physician or healthcare provider.

### Quick Reference: When to Contact Your Doctor

| Symptom / Result | Action |
| :--- | :--- |
| **Any "High" or "Low" flag** | Discuss with your doctor at your next appointment. |
| **Multiple flags in one category** | Schedule an appointment for comprehensive review. |
| **Severe symptoms (chest pain, difficulty breathing, severe dizziness)** | **Seek emergency care immediately.** |
| **Results significantly outside reference ranges** | Contact your healthcare provider promptly. |
| **Unclear or confusing results** | Bring this analysis to your doctor and ask for clarification. |

---

## 6. Quick Start Checklist

- [ ] Have your lab report ready (PDF or image)
- [ ] Ensure the document is well-lit and fully captured
- [ ] Upload the report to the system
- [ ] Review the extracted results in the scorecard
- [ ] Read plain-English explanations for flagged tests
- [ ] Ask follow-up questions via the chat feature
- [ ] Discuss results with your healthcare provider
- [ ] Save or print your analysis for reference

---

## 7. Contact & Support

* **Website:** `[Project Website]`
* **Email:** `[Support Email]`
* **Documentation:** `[Documentation Link]`

---

*Thank you for using the Intelligent Medical Report Analysis System. We are committed to making medical information more accessible and understandable for everyone.*
