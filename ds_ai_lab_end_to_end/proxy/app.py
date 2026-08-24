import os

import gradio as gr
import spaces
from gradio_client import Client, handle_file


# ZeroGPU Spaces require at least one @spaces.GPU function.
# This function is only here to satisfy that startup requirement.
@spaces.GPU
def _zerogpu_startup_check():
    return True


HF_TOKEN = os.environ.get("HF_TOKEN")

if not HF_TOKEN:
    raise RuntimeError(
        "HF_TOKEN secret is not configured for the proxy Space."
    )


SPACE_ID = "rajsri2609/medical-report-ai"

_client = None


def get_client():
    global _client

    if _client is None:
        _client = Client(
            SPACE_ID,
            token=HF_TOKEN
        )

    return _client


def proxy_analyze(file_obj):
    if file_obj is None:
        return {"error": "No file uploaded."}

    client = get_client()

    # Convert Gradio uploaded file into a path
    file_path = (
        file_obj.name
        if hasattr(file_obj, "name")
        else str(file_obj)
    )

    # handle_file() converts the path into the FileData format
    # expected by the private Gradio backend
    result = client.predict(
        handle_file(file_path),
        api_name="/analyze_report"
    )

    # Backend returns:
    # [analysis_json, report_context_state]
    if isinstance(result, (list, tuple)) and len(result) > 0:
        return result[0]

    return result


def proxy_chat(message, history, report_context):
    if not message:
        return "Please enter a question."

    client = get_client()

    result = client.predict(
        message,
        history or [],
        report_context or [],
        api_name="/chat"
    )

    if isinstance(result, (list, tuple)) and len(result) > 0:
        return result[0]

    return result


with gr.Blocks(title="Medical Report AI Proxy") as demo:
    gr.Markdown("# Medical Report AI Proxy")
    gr.Markdown(
        "Secure proxy between the public frontend and the private AI backend."
    )

    # -------------------------
    # Analyze report
    # -------------------------

    file_input = gr.File(
        label="Test Medical Report",
        file_types=[".pdf", ".png", ".jpg", ".jpeg"]
    )

    analyze_button = gr.Button("Analyze")

    analyze_output = gr.JSON(
        label="Analysis Result"
    )

    analyze_button.click(
        fn=proxy_analyze,
        inputs=[file_input],
        outputs=[analyze_output],
        api_name="analyze"
    )

    # -------------------------
    # Chat
    # -------------------------

    gr.Markdown("## Chat Test")

    message = gr.Textbox(
        label="Message"
    )

    history = gr.JSON(
        label="History",
        value=[]
    )

    report_context = gr.JSON(
        label="Report Context",
        value=[]
    )

    chat_button = gr.Button("Chat")

    chat_output = gr.Textbox(
        label="Chat Response"
    )

    chat_button.click(
        fn=proxy_chat,
        inputs=[
            message,
            history,
            report_context
        ],
        outputs=[chat_output],
        api_name="chat"
    )


if __name__ == "__main__":
    demo.launch(show_error=True)