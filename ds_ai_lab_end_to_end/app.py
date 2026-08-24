import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

try:
    import spaces
except ImportError:
    # Safe mock fallback for running/testing locally without ZeroGPU environment
    class spaces:
        @staticmethod
        def GPU(fn=None, **kwargs):
            if fn is None:
                return lambda f: f
            return fn

import gradio as gr
from app.config import STUB_MODELS
from app.pipeline.pipeline import process_medical_report
from app.pipeline.llm import generate_medical_summary, generate_chat_response

# In stub mode a plain .txt of report text is accepted so the whole pipeline can
# be exercised on a CPU-only machine without PaddleOCR.
UPLOAD_TYPES = [".pdf", ".png", ".jpg", ".jpeg"] + ([".txt"] if STUB_MODELS else [])


def _prefetch_weights():
    """Download model weights at startup, before any GPU is held.

    ZeroGPU charges the caller's daily quota for the whole duration of a
    @spaces.GPU function. Model loading is lazy, so without this the FIRST
    request would download ~14GB of BioMistral inside its 120s allocation:
    it would time out and spend quota to do it. Fetching to disk here costs no
    quota (this runs at container startup, outside any GPU function), leaving
    the GPU call to do only a fast cache -> VRAM load.
    """
    if STUB_MODELS:
        return
    from huggingface_hub import snapshot_download
    from app.config import BIOMISTRAL_BASE_MODEL, BIOMISTRAL_ADAPTER_PATH, CLINICALBERT_NER_PATH

    for repo, label in (
        (CLINICALBERT_NER_PATH, "ClinicalBERT NER"),
        (BIOMISTRAL_ADAPTER_PATH, "BioMistral LoRA adapter"),
        (BIOMISTRAL_BASE_MODEL, "BioMistral base"),
    ):
        try:
            print(f"[PREFETCH] {label}: {repo}")
            snapshot_download(repo, token=os.environ.get("HF_TOKEN"))
        except Exception as exc:  # noqa: BLE001 - never block startup on this
            print(f"[PREFETCH] {label} failed ({exc}); it will download on first use.")
    print("[PREFETCH] done")


_prefetch_weights()

# ZeroGPU reserves the DECLARED duration against the caller's daily quota, not
# the time actually used, AND aborts a call that runs past it. Generation time
# grows with the number of results - a 16-test report measured 109s - so a flat
# cap either aborts big reports or wastes quota on small ones. ZeroGPU accepts a
# callable, so the reservation is sized per request.
def _analyze_duration(file_obj) -> int:
    """Bigger files carry more results, so allow more GPU time for them."""
    try:
        size_mb = os.path.getsize(file_obj.name) / 1e6
    except Exception:  # noqa: BLE001
        return 150
    return 120 if size_mb < 0.5 else (180 if size_mb < 2 else 240)


@spaces.GPU(duration=_analyze_duration)
def analyze_report(file_obj):
    if file_obj is None:
        return {"error": "No file uploaded."}, None

    import time
    t0 = time.time()
    file_path = file_obj.name
    try:
        print(f"Processing uploaded file: {file_path}")
        report_json = process_medical_report(file_path)
        t_extract = time.time()
        summary = generate_medical_summary(report_json)
        t_done = time.time()
        # Printed so the Space log shows WHERE the time goes rather than leaving
        # it to guesswork: extraction is OCR + NER + grounding, generation is the
        # 7B model plus any readability revision rounds.
        print(f"[TIMING] extract={t_extract - t0:.1f}s "
              f"generate={t_done - t_extract:.1f}s "
              f"total={t_done - t0:.1f}s "
              f"results={len(report_json.get('lab_results', []))}")
        
        result = {
            "report": report_json,
            "summary": summary
        }
        # The chat context carries the summary as well as the results, so the
        # assistant can refer to what the patient has already read instead of
        # re-deriving it. The bare-list shape is still accepted by /chat.
        return result, {
            "lab_results": report_json.get("lab_results", []),
            "summary": summary,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, None

# 2. API: Chat (ZeroGPU-wrapped)
@spaces.GPU(duration=45)
def run_chat(message, history, report_context):
    """report_context is either the results list or {lab_results, summary}."""
    if not message:
        return "Please ask a question."
    try:
        response = generate_chat_response(message, report_context, history)
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}"

# Gradio Blocks UI Layout
with gr.Blocks(title="Medical AI Report Lab Backend (HF Spaces)") as demo:
    gr.Markdown("# Medical AI Report Lab Backend")
    gr.Markdown("Gradio API wrapper equipped with ZeroGPU support for Medical Report Analysis.")
    
    # Session state drives the interactive tab only.
    report_context_state = gr.State(value=None)

    # The API endpoint is deliberately built from plain gr.JSON components
    # rather than the UI widgets, for two independent reasons:
    #
    #  1. gr.State is EXCLUDED from Gradio's published API signature, so an
    #     external client's report_context argument was silently dropped and
    #     always arrived as None.
    #  2. gr.Chatbot's payload schema is version-dependent. Under Gradio 6 it
    #     validates `content` as a list of content parts, so the frontend's
    #     {"role": ..., "content": "some string"} history fails schema
    #     validation before the handler is ever called.
    #
    # gr.JSON is a real published component with a permissive schema, which
    # keeps the wire contract stable across Gradio versions.
    api_context = gr.JSON(value=None, visible=False)
    api_history = gr.JSON(value=[], visible=False)
    
    with gr.Tab("Report Analysis"):
        file_input = gr.File(label="Upload Medical Report", file_types=UPLOAD_TYPES)
        analyze_btn = gr.Button("Analyze Report")
        analysis_output = gr.JSON(label="Extracted Lab Data & Summary")
        
        analyze_btn.click(
            fn=analyze_report,
            inputs=[file_input],
            outputs=[analysis_output, report_context_state],
            api_name="analyze_report"
        )
        
    with gr.Tab("Interactive Chat"):
        try:
            chatbot = gr.Chatbot(label="Chatbot History", type="messages")
        except TypeError:
            chatbot = gr.Chatbot(label="Chatbot History")
        msg_input = gr.Textbox(label="Ask about your report", placeholder="What does my hemoglobin level mean?")
        submit_btn = gr.Button("Send Message")
        
        # Local UI callback to append to chatbot
        def run_chat_ui(message, history, report_context):
            response = run_chat(message, history, report_context)
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response})
            return "", history
            
        submit_btn.click(
            fn=run_chat_ui,
            inputs=[msg_input, chatbot, report_context_state],
            outputs=[msg_input, chatbot],
            api_name=False,   # interactive tab only; not part of the public API
        )
        
        # Expose the API endpoint directly for the React frontend
        # The api_name="chat" allows client libraries to call it directly
        # It expects: message (str), history (list), report_context (list)
        # It returns: response (str)
        api_chat_btn = gr.Button("API Chat Endpoint", visible=False)
        api_chat_output = gr.Textbox(visible=False)
        api_msg = gr.Textbox(visible=False)
        api_chat_btn.click(
            fn=run_chat,
            inputs=[api_msg, api_history, api_context],
            outputs=[api_chat_output],
            api_name="chat"
        )

if __name__ == "__main__":
    # show_error surfaces handler tracebacks to the client instead of the
    # opaque "upstream Gradio app has raised an exception" message. Worth having
    # on a private backend: without it, a failure inside the pipeline is
    # invisible to the proxy and to local testing.
    #
    # Port and host come from Gradio's own GRADIO_SERVER_PORT / GRADIO_SERVER_NAME
    # environment variables, which Spaces sets automatically. If 7860 is already
    # taken locally, Gradio moves to 7861 and its localhost reachability check
    # can fail with "When localhost is not accessible, a shareable link must be
    # created" - free the port, or set GRADIO_SERVER_PORT explicitly.
    demo.launch(show_error=True)
