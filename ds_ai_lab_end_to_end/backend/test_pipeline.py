import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add backend directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Dynamic mocking of heavy ML / Image libraries if they are missing
# to allow running tests and demonstrating the exact JSON output.
try:
    import torch
except ImportError:
    sys.modules['torch'] = MagicMock()
    sys.modules['torch.device'] = MagicMock()
try:
    import transformers
except ImportError:
    sys.modules['transformers'] = MagicMock()
try:
    import peft
except ImportError:
    sys.modules['peft'] = MagicMock()
try:
    from paddleocr import PaddleOCR
except ImportError:
    sys.modules['paddleocr'] = MagicMock()
try:
    from pdf2image import convert_from_path
except ImportError:
    sys.modules['pdf2image'] = MagicMock()
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = MagicMock()
try:
    import numpy as np
except ImportError:
    sys.modules['numpy'] = MagicMock()

# Explicitly import app.pipeline modules to register them in sys.modules
import app.pipeline.ocr as ocr_module
import app.pipeline.pipeline as pipe_module
import app.pipeline.ner as ner_module
import app.pipeline.llm as llm_module


class TestPipelineFlow(unittest.TestCase):
    def setUp(self):
        # Ensure sys.path contains the backend/app folder
        if 'backend' not in sys.path:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    def test_missing_file(self):
        from app.pipeline.pipeline import process_medical_report
        with self.assertRaises(FileNotFoundError):
            process_medical_report("non_existent_report.pdf")

    def test_invalid_file_type(self):
        from app.pipeline.pipeline import process_medical_report
        # .docx, not .txt: in MEDREPORT_STUB_MODELS mode a plain .txt IS a
        # valid upload (it feeds report text straight in, bypassing OCR), so
        # this test used to pass or fail depending on the environment.
        dummy_file = "dummy_test_report.docx"
        with open(dummy_file, "w") as f:
            f.write("Some dummy content")
        
        try:
            with self.assertRaises(ValueError) as context:
                process_medical_report(dummy_file)
            self.assertIn("Invalid file type", str(context.exception))
        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)

    @patch('app.pipeline.pipeline.MedicalReportPipeline.load_models')
    @patch('app.pipeline.ocr.MedicalReportOCR.extract')
    def test_successful_extraction_flow(self, mock_ocr_extract, mock_load_models):
        from app.pipeline.pipeline import process_medical_report
        
        # 1. Mock OCR to return typical lab lines
        mock_ocr_extract.return_value = (
            "Hemoglobin 10.2 g/dL\n"
            "Platelet Count 520 10^9/L\n"
            "WBC 7.8 10^9/L"
        )
        
        # 2. Mock ClinicalBERTNER predictions
        # Simulate token classification tokens and labels
        # NB "WBC Count", not "WBC": the lexicon corrector rewrites the OCR
        # line to its canonical name BEFORE the NER sees it, so a mock that
        # returns bare "WBC" is not what the real model would be given.
        mock_tokens = [
            "Hemoglobin", "10.2", "g/dL",
            "Platelet", "Count", "520", "10^9/L",
            "WBC", "Count", "7.8", "10^9/L"
        ]
        mock_tags = [
            "B-TEST", "B-VALUE", "B-UNIT",
            "B-TEST", "I-TEST", "B-VALUE", "B-UNIT",
            "B-TEST", "I-TEST", "B-VALUE", "B-UNIT"
        ]
        
        # Instantiate a mock NER model and patch it inside pipeline
        mock_ner = MagicMock()
        mock_ner.predict.return_value = (mock_tokens, mock_tags)
        
        # Apply patch on the global pipeline instance
        import app.pipeline.pipeline as pipe_module
        if pipe_module._pipeline_instance is None:
            pipe_module._pipeline_instance = pipe_module.MedicalReportPipeline()
        
        pipe_module._pipeline_instance.ner = mock_ner
        
        # Create a dummy PNG file to pass checks
        dummy_png = "dummy_report.png"
        with open(dummy_png, "wb") as f:
            f.write(b"PNG_HEADER_DATA")
            
        try:
            # Execute pipeline
            result = process_medical_report(dummy_png)
            
            # Verify results dictionary
            self.assertTrue(result['success'])
            self.assertEqual(result['summary']['total_tests'], 3)
            self.assertEqual(result['summary']['abnormal_count'], 2)  # Hemoglobin (LOW), Platelets (HIGH)
            
            # Verify Hemoglobin low range and Platelet high range mapping
            results_dict = {r['test_name']: r for r in result['lab_results']}
            # Ranges come from the reference workbook now, not from the
            # hardcoded table this test was written against. Hemoglobin is one
            # of the 20 sex-specific rows; no sex is stated in this text, so
            # the union of the male and female ranges is used and the patient
            # is told so, rather than a male range being assumed.
            self.assertEqual(results_dict['Hemoglobin']['status'], 'LOW')
            self.assertEqual(results_dict['Hemoglobin']['ref_min'], 11.6)
            self.assertEqual(results_dict['Hemoglobin']['ref_max'], 16.6)

            # Test names are normalised to their canonical workbook spelling,
            # so "Platelet Count" and "WBC Count", not "Platelets" and "WBC".
            self.assertEqual(results_dict['Platelet Count']['status'], 'HIGH')
            self.assertEqual(results_dict['Platelet Count']['ref_min'], 150.0)
            self.assertEqual(results_dict['Platelet Count']['ref_max'], 400.0)

            self.assertEqual(results_dict['WBC Count']['status'], 'NORMAL')
            
            # Print exact JSON output structure
            import json
            print("\n" + "="*50)
            print("EXACT JSON RETURNED BY process_medical_report()")
            print("="*50)
            print(json.dumps(result, indent=2))
            print("="*50 + "\n")
            
        finally:
            if os.path.exists(dummy_png):
                os.remove(dummy_png)

    @patch('app.pipeline.llm.BioMistralPipeline.load_models')
    def test_generate_medical_summary(self, mock_load_models):
        import torch
        from app.pipeline.llm import generate_medical_summary
        
        # Instantiate mock tokenizer and model inside pipeline
        mock_tokenizer = MagicMock()
        mock_tokenizer.apply_chat_template.return_value = MagicMock()
        mock_model = MagicMock()
        mock_model.device = "cpu"
        
        # Mock generate return values
        mock_model.generate.return_value = torch.tensor([[0, 1, 2, 3]])
        mock_tokenizer.decode.return_value = "### Patient Friendly Summary\n\nYour lab results look okay..."
        
        import app.pipeline.llm as llm_module
        if llm_module._llm_pipeline is None:
            llm_module._llm_pipeline = llm_module.BioMistralPipeline()
            
        llm_module._llm_pipeline.tokenizer = mock_tokenizer
        llm_module._llm_pipeline.model = mock_model
        
        # Prepare structured lab results
        mock_report = {
            "success": True,
            "lab_results": [
                {
                    "test_name": "Hemoglobin",
                    "value": "10.2",
                    "unit": "g/dL",
                    "status": "LOW"
                }
            ]
        }
        
        # Execute summary generation
        summary = generate_medical_summary(mock_report)

        # Assert the contract, not the mock's call count. Two things changed
        # since this was written: MEDREPORT_STUB_MODELS routes to the grounded
        # rule-based writer without touching the model at all, and in model
        # mode the readability loop may call generate more than once to reach
        # grade 8. Both are correct, and both broke assert_called_once.
        self.assertTrue(summary.strip(), "summary must not be empty")

        from app.config import STUB_MODELS
        if STUB_MODELS:
            # The grounded writer builds the summary from the results, so it
            # must name the abnormal test and say it is not a clinical opinion.
            self.assertIn("Hemoglobin", summary)
            self.assertIn("10.2", summary)
            self.assertIn("physician", summary.lower())
        else:
            # In model mode the summary IS the model's decode output, which
            # here is the canned mock string - so assert the model was driven
            # and its text survived post-processing, not that it mentions a
            # test the mock never wrote.
            self.assertIn("Patient Friendly Summary", summary)
            self.assertTrue(mock_tokenizer.apply_chat_template.called)
            self.assertTrue(mock_model.generate.called)


if __name__ == "__main__":
    unittest.main()
