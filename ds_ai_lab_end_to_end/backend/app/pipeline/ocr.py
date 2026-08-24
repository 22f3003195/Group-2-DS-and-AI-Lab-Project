import os
import re
import tempfile
import cv2
import numpy as np
from typing import Dict, List, Tuple

try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class EdgeBasedRotationCorrector:
    def __init__(self):
        pass
    
    def detect_rotation(self, image_path: str) -> int:
        try:
            img = cv2.imread(image_path)
            if img is None:
                return 0
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Use Canny edge detection
            edges = cv2.Canny(gray, 50, 150)
            # Use Hough Line Transform to detect lines
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=30, maxLineGap=10)
            if lines is None:
                return 0
            horizontal_lines = 0
            vertical_lines = 0
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                # Horizontal lines (text lines)
                if abs(angle) < 20 or abs(abs(angle) - 180) < 20:
                    horizontal_lines += 1
                # Vertical lines (rotated text)
                elif abs(abs(angle) - 90) < 20:
                    vertical_lines += 1
            # If horizontal lines dominate, image is upright or 180 rotated
            if horizontal_lines > vertical_lines * 2:
                return 0  # Upright
            # If vertical lines dominate, image is 90 or 270 rotated
            elif vertical_lines > horizontal_lines * 2:
                # Check aspect ratio to determine 90 vs 270
                if img.shape[0] > img.shape[1]:
                    return 90
                else:
                    return 90  # Default to 90
            else:
                return 0  # Not clear, assume upright
        except Exception as e:
            print(f"Edge-based rotation detection failed: {e}")
            return 0
    
    def correct(self, image_path: str) -> Tuple[str, int]:
        angle = self.detect_rotation(image_path)
        if angle == 0:
            return image_path, 0
        print(f"Edge detection suggests {angle}° rotation - correcting...")
        img = cv2.imread(image_path)
        if img is None:
            return image_path, 0
        if angle == 90:
            rotated = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif angle == 180:
            rotated = cv2.rotate(img, cv2.ROTATE_180)
        elif angle == 270:
            rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        else:
            return image_path, 0
        output_path = os.path.join(tempfile.gettempdir(), "rotated_medical_report.png")
        cv2.imwrite(output_path, rotated)
        print(f"Rotation correction applied")
        return output_path, angle


class MedicalReportOCR:
    def __init__(self):
        self.ocr = None
        self.rotation_corrector = EdgeBasedRotationCorrector()
        if PADDLE_AVAILABLE:
            try:
                self.ocr = PaddleOCR(
                    lang="en",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    enable_mkldnn=False,
                    text_det_limit_side_len=1920,
                    text_det_limit_type="max",
                    text_det_thresh=0.25,
                    text_det_box_thresh=0.40,
                    text_rec_score_thresh=0.30
                )
                print("PaddleOCR initialized successfully.")
            except Exception as e:
                print(f"PaddleOCR initialization failed: {e}")
                self.ocr = None
        else:
            print("PaddleOCR not available")
    
    def _preprocess_image(self, image_path):
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not read image: {image_path}")
        original_height, original_width = image.shape[:2]
        if original_width >= 1800:
            return image_path
        print(f"Image quality: {original_width}x{original_height} - applying enhancements...")
        scale = 1800 / original_width
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
        sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
        output_path = os.path.join(tempfile.gettempdir(), "preprocessed_medical_report.png")
        cv2.imwrite(output_path, sharpened)
        return output_path

    @staticmethod
    def _extract_result_dictionary(result_item) -> Dict:
        if isinstance(result_item, dict):
            if isinstance(result_item.get("res"), dict):
                return result_item["res"]
            return result_item
        if hasattr(result_item, "json"):
            try:
                data = result_item.json
                if callable(data):
                    data = data()
                import json
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, dict):
                    if isinstance(data.get("res"), dict):
                        return data["res"]
                    return data
            except Exception:
                pass
        if hasattr(result_item, "res"):
            try:
                data = result_item.res
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    @staticmethod
    def _make_ordered_lines(boxes, texts, scores=None, minimum_score: float = 0.30) -> List[str]:
        entries = []
        for index, raw_text in enumerate(texts):
            text = str(raw_text).strip()
            if not text:
                continue
            score = 1.0
            if scores is not None and index < len(scores):
                try:
                    score = float(scores[index])
                except (TypeError, ValueError):
                    score = 1.0
            if score < minimum_score:
                continue
            x_left = 0.0
            y_center = index * 20.0
            box_height = 20.0
            if boxes is not None and index < len(boxes):
                try:
                    box = boxes[index]
                    xs = [float(point[0]) for point in box]
                    ys = [float(point[1]) for point in box]
                    x_left = min(xs)
                    y_top = min(ys)
                    y_bottom = max(ys)
                    box_height = max(1.0, y_bottom - y_top)
                    y_center = (y_top + y_bottom) / 2
                except (TypeError, ValueError, IndexError):
                    pass
            entries.append({
                "text": text,
                "x": x_left,
                "y": y_center,
                "height": box_height
            })
        if not entries:
            return []
        entries.sort(key=lambda item: (item["y"], item["x"]))
        rows = []
        for entry in entries:
            matching_row = None
            for row in rows:
                tolerance = max(10.0, row["average_height"] * 0.60, entry["height"] * 0.60)
                if abs(entry["y"] - row["average_y"]) <= tolerance:
                    matching_row = row
                    break
            if matching_row is None:
                rows.append({
                    "items": [entry],
                    "average_y": entry["y"],
                    "average_height": entry["height"]
                })
            else:
                matching_row["items"].append(entry)
                matching_row["average_y"] = sum(item["y"] for item in matching_row["items"]) / len(matching_row["items"])
                matching_row["average_height"] = sum(item["height"] for item in matching_row["items"]) / len(matching_row["items"])
        rows.sort(key=lambda row: row["average_y"])
        ordered_lines = []
        for row in rows:
            row["items"].sort(key=lambda item: item["x"])
            line = " ".join(item["text"] for item in row["items"])
            line = line.replace('10%9/L', '10^9/L')
            line = line.replace('10°9/L', '10^9/L')
            line = re.sub(r'\s+', ' ', line).strip()
            if line:
                ordered_lines.append(line)
        return ordered_lines

    def extract_text_from_image(self, image_path):
        if self.ocr is None:
            raise RuntimeError("PaddleOCR is not initialized/installed.")
        try:
            print("\nDetecting rotation using edge detection...")
            corrected_path, rotation_angle = self.rotation_corrector.correct(image_path)
            if rotation_angle != 0:
                print(f"Rotation corrected by {rotation_angle}°")
            else:
                print("No rotation detected")
            processed_path = self._preprocess_image(corrected_path)
            results = list(self.ocr.predict(processed_path))
            all_lines = []
            for result_item in results:
                data = self._extract_result_dictionary(result_item)
                texts = data.get("rec_texts") or data.get("texts") or []
                scores = data.get("rec_scores") or data.get("scores") or []
                boxes = data.get("rec_polys") or data.get("dt_polys") or data.get("boxes") or []
                if texts:
                    all_lines.extend(self._make_ordered_lines(boxes=boxes, texts=texts, scores=scores))
            full_text = "\n".join(all_lines)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()
            if not full_text:
                print("No text detected in image")
                return ""
            print(f"PaddleOCR recognized {len(all_lines)} reconstructed rows.")
            return full_text
        except Exception as e:
            print(f"Error extracting text from image: {e}")
            return self._fallback_ocr(image_path)
    
    def _fallback_ocr(self, image_path):
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            return text.strip()
        except Exception as e:
            print(f"Fallback OCR failed: {e}")
            return ""
    
    def extract_text_from_pdf(self, pdf_path):
        if not PDF_AVAILABLE:
            raise RuntimeError("pdf2image library is not installed or poppler-utils is not available.")
        try:
            pages = convert_from_path(pdf_path)
            texts = []
            for i, page in enumerate(pages):
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                    temp_name = f.name
                try:
                    page.save(temp_name)
                    text = self.extract_text_from_image(temp_name)
                    if text:
                        texts.append(text)
                        print(f"  Processed page {i+1}/{len(pages)}")
                finally:
                    if os.path.exists(temp_name):
                        os.remove(temp_name)
            return '\n'.join(texts)
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""
    
    def extract(self, file_path):
        if file_path.lower().endswith('.pdf'):
            return self.extract_text_from_pdf(file_path)
        else:
            return self.extract_text_from_image(file_path)


class ValueLineFilter:
    def __init__(self):
        self.value_patterns = [
            r'\b\d+\.?\d*\s*(?:g/dL|mg/dL|mmol/L|mEq/L|K/uL|M/uL|U/L|IU/L|ng/mL|pg/mL|µg/mL|ug/mL|fL|pg|sec|%|mm Hg|mmHg|cells/mcL|cumm|mill/cumm)\b',
            r'\b\d+\.?\d*\s*[-–—]\s*\d+\.?\d*\b',
            r'\b\d+\.?\d*\s*[<>]?\s*\d+\.?\d*\b',
        ]
        self.lab_keywords = [
            'hemoglobin', 'hgb', 'rbc', 'wbc', 'platelet', 'plt', 'mcv', 'mch', 'mchc', 'rdw',
            'neutrophils', 'lymphocytes', 'eosinophils', 'monocytes', 'basophils',
            'glucose', 'sodium', 'potassium', 'chloride', 'bicarbonate', 'bun', 'creatinine',
            'calcium', 'magnesium', 'phosphorus', 'albumin', 'bilirubin', 'cholesterol',
            'triglycerides', 'hdl', 'ldl', 'uric acid', 'ast', 'alt', 'alkaline phosphatase',
            'ldh', 'ck', 'troponin', 'bnp', 'tsh', 't3', 't4', 'ferritin', 'iron', 'b12',
            'folate', 'vitamin d', 'cortisol', 'testosterone', 'hcg', 'prolactin', 'psa',
            'amylase', 'lipase', 'inr', 'pt', 'ptt', 'crp', 'esr', 'ph', 'pco2', 'po2',
            'absolute', 'packed cell', 'mean corpuscular', 'calculated'
        ]
        self.skip_patterns = [
            r'(?:DRLOGY|PATHOLOGY|LAB|SMART VISION|HEALTHCARE ROAD|MUMBAI|Yash|Patel|Sample Collected|Age|Bungalow|Registered|Collected|Reported|PID|Ref\. By|Instruments|Generated|Page|Sample Collection)',
            r'(?:Accurate|Caring|Instant|www\.drlogy\.com|drlogypathlab)',
        ]
    
    def line_has_value(self, line: str) -> bool:
        line_lower = line.lower()
        for pattern in self.skip_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return False
        for pattern in self.value_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        has_number = bool(re.search(r'\d+\.?\d*', line))
        has_unit = bool(re.search(r'(g/dL|mg/dL|mmol/L|mEq/L|K/uL|M/uL|U/L|IU/L|ng/mL|pg/mL|µg/mL|ug/mL|fL|pg|sec|%|mm Hg|mmHg|cells/mcL|cumm|mill/cumm)', line, re.IGNORECASE))
        if has_number and has_unit:
            return True
        for keyword in self.lab_keywords:
            if keyword in line_lower:
                if re.search(r'\d+\.?\d*', line):
                    return True
        if re.search(r'\d+\.?\d*\s*[-–—]\s*\d+\.?\d*', line):
            return True
        return False
    
    def filter_lines(self, text: str) -> str:
        if not text:
            return ""
        lines = text.split('\n')
        kept_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if self.line_has_value(line):
                line = line.replace('10%9/L', '10^9/L')
                line = line.replace('10°9/L', '10^9/L')
                line = line.replace('gfdl.', 'g/dL')
                line = line.replace('cells/mcl', 'cells/mcL')
                line = re.sub(r'(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)', r'\1-\2', line)
                line = re.sub(r'\s+', ' ', line).strip()
                kept_lines.append(line)
        print(f"  Kept {len(kept_lines)} lines with values")
        return '\n'.join(kept_lines)
