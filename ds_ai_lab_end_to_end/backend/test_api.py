import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add backend directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Dynamic mocking of ML libraries in case they are not installed
try:
    import torch
except ImportError:
    sys.modules['torch'] = MagicMock()
try:
    import transformers
except ImportError:
    sys.modules['transformers'] = MagicMock()
try:
    import peft
except ImportError:
    sys.modules['peft'] = MagicMock()
try:
    import paddleocr
except ImportError:
    sys.modules['paddleocr'] = MagicMock()
try:
    import pdf2image
except ImportError:
    sys.modules['pdf2image'] = MagicMock()
try:
    import cv2
except ImportError:
    sys.modules['cv2'] = MagicMock()
try:
    import numpy
except ImportError:
    sys.modules['numpy'] = MagicMock()

# Import FastAPI's test client (will fail if fastapi is not installed, so we handle it)
try:
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class TestAPI(unittest.TestCase):
    def setUp(self):
        if not FASTAPI_AVAILABLE:
            self.skipTest("FastAPI is not installed in the environment.")
        
        from app.main import app
        self.client = TestClient(app)

    def test_cors_headers(self):
        # Send an OPTIONS request to check CORS headers
        response = self.client.options(
            "/api/reports/analyze",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access-control-allow-origin", response.headers)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_upload_missing_file(self):
        response = self.client.post("/api/reports/analyze")
        # Missing file field in form upload should return 422 Unprocessable Entity (FastAPI validation)
        self.assertEqual(response.status_code, 422)

    def test_upload_invalid_file_type(self):
        # Upload an unsupported file type (.txt)
        files = {"file": ("test.txt", b"dummy content", "text/plain")}
        response = self.client.post("/api/reports/analyze", files=files)
        
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file type", response.json()["detail"])

    @patch("app.main.generate_medical_summary")
    @patch("app.main.process_medical_report")
    def test_upload_success_flow(self, mock_process, mock_generate):
        # 1. Setup mock returns
        mock_process.return_value = {
            "success": True,
            "lab_results": [
                {"test_name": "Hemoglobin", "value": "10.2", "unit": "g/dL", "status": "LOW"}
            ],
            "summary": {"total_tests": 1, "abnormal_count": 1, "text": "Found 1 lab tests."}
        }
        mock_generate.return_value = "### Summary\n\nYour hemoglobin is slightly low."

        # 2. Perform upload of dummy image file
        files = {"file": ("report.png", b"PNG_DATA", "image/png")}
        response = self.client.post("/api/reports/analyze", files=files)

        # 3. Assertions
        self.assertEqual(response.status_code, 200)
        res_json = response.json()
        self.assertTrue(res_json["report"]["success"])
        self.assertEqual(res_json["summary"], "### Summary\n\nYour hemoglobin is slightly low.")
        mock_process.assert_called_once()
        mock_generate.assert_called_once()

    @patch("app.main.process_medical_report")
    def test_ocr_failure_handling(self, mock_process):
        # OCR raising ValueError (e.g. empty OCR result)
        mock_process.side_effect = ValueError("We couldn't read any text from this file. Try a clearer photo.")

        files = {"file": ("report.png", b"PNG_DATA", "image/png")}
        response = self.client.post("/api/reports/analyze", files=files)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "We couldn't read any text from this file. Try a clearer photo.")

    @patch("app.main.process_medical_report")
    def test_internal_error_handling(self, mock_process):
        # OCR or backend raising arbitrary runtime exception
        mock_process.side_effect = Exception("Database connection failed")

        files = {"file": ("report.png", b"PNG_DATA", "image/png")}
        response = self.client.post("/api/reports/analyze", files=files)

        self.assertEqual(response.status_code, 500)
        self.assertIn("OCR pipeline processing failed", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
