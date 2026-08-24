import os
import sys
import tempfile
import traceback
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure backend directory is in the python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import ALLOWED_EXTENSIONS
from app.pipeline.pipeline import process_medical_report
from app.pipeline.llm import generate_medical_summary

app = FastAPI(title="Medical AI Report Lab Backend")

# CORS middleware configuration to allow the frontend development URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/reports/analyze")
async def analyze_report(file: UploadFile = File(...)):
    # 1. Validate file field
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    # 2. Validate file type extension
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type '.{ext}'. Supported types are: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 3. Create a secure temporary file to write binary stream
    temp_fd, temp_path = tempfile.mkstemp(suffix=f".{ext}")
    try:
        # Write contents to temporary file
        with os.fdopen(temp_fd, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 4. Invoke OCR + NER pipeline
        try:
            report_json = process_medical_report(temp_path)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"OCR pipeline processing failed: {str(e)}")

        # 5. Invoke LLM summary generation
        try:
            summary = generate_medical_summary(report_json)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"LLM medical summary generation failed: {str(e)}")

        # 6. Return combined results
        return {
            "report": report_json,
            "summary": summary
        }

    except HTTPException:
        # Re-raise FastAPIs HTTPExceptions directly
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Cleanup temporary uploaded file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"Temporary file cleaned up: {temp_path}")
            except Exception as e:
                print(f"Failed to delete temp file: {e}")


# Pydantic schemas for the Chat endpoint
class ChatMessage(BaseModel):
    sender: str  # "user" or "assistant"
    text: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]
    report_context: Optional[Dict] = None


@app.post("/api/chat")
async def chat_with_assistant(req: ChatRequest):
    try:
        query = req.message.strip().lower()
        if not query:
            raise HTTPException(status_code=400, detail="Message cannot be empty.")

        # Simulate LLM response for chat questions based on context
        # In a real environment, we'd load conversation history into BioMistral
        # and append report context as system prompt instructions.
        # Fallback responses match the frontend expected keyword mock
        response_text = ""
        if "hemoglobin" in query or "anemia" in query or "oxygen" in query:
            response_text = (
                "Your hemoglobin level is **10.2 g/dL**, which is below the normal range of **12.0–16.0 g/dL**. "
                "Hemoglobin carries oxygen throughout your body, and lower levels can cause mild fatigue. "
                "This is typically addressable through iron-rich dietary adjustments or supplements under doctor supervision."
            )
        elif "platelet" in query or "clot" in query:
            response_text = (
                "Your platelet count is **520 10^9/L**, which is slightly higher than the normal limit of **450 10^9/L**. "
                "Platelets are key blood clotting cells. Mild elevations can be reactive to inflammation or iron changes. "
                "Discussing this with your physician can clarify if a repeat test is needed."
            )
        elif "cholesterol" in query or "fat" in query or "cardio" in query:
            response_text = (
                "Your Total Cholesterol is **240 mg/dL**, exceeding the recommended target of **200 mg/dL**. "
                "Managing cholesterol is important for long-term heart health and is commonly approached with "
                "cardiovascular exercise, fiber-rich diets, or medical advice."
            )
        elif "vitamin d" in query or "deficiency" in query or "bone" in query:
            response_text = (
                "Your Vitamin D is **18 ng/mL**, falling below the ideal threshold of **30 ng/mL**. "
                "Vitamin D deficiency is very common and affects bone and immune health. It is typically resolved "
                "through dietary supplements or safe sun exposure."
            )
        elif "wbc" in query or "white blood" in query:
            response_text = (
                "Your WBC (White Blood Cells) count is **7.8 10^9/L**, which is perfectly normal (range: 4.5–11.0 10^9/L). "
                "This indicates a normal immune response count."
            )
        elif "tsh" in query or "thyroid" in query or "metabolism" in query:
            response_text = (
                "Your TSH is **2.1 uIU/mL**, which lies comfortably within the normal reference range (0.4–4.5 uIU/mL). "
                "This suggests healthy thyroid performance."
            )
        else:
            response_text = (
                "I am your MedReport AI Assistant. Ask me questions about your lab results, like "
                "'Should I worry about my hemoglobin?' or 'How can I improve my Vitamin D?'"
            )

        return {"response": response_text}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat assistant failed: {str(e)}")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Medical AI Analysis Backend is running."}
