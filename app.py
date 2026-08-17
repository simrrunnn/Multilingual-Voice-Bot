"""HuggingFace Spaces entrypoint (Gradio SDK).

Serves the FastAPI read API (`app.main.app`) plus a small Gradio status/
lookup UI mounted at `/`, and launches the LiveKit voice agent worker as a
background OS subprocess rather than running it in-process: the LiveKit
Agents CLI owns its own process (signal handling, job-executor processes,
event loop startup) and isn't meant to be embedded in another app's asyncio
loop. A subprocess keeps both halves working exactly as they do standalone.

Configuration is via environment variables (Space secrets), same as local
`.env` -- see `.env.example`. Set real credentials in the Space's
Settings > Repository secrets, never in code.
"""

from __future__ import annotations

import atexit
import os
import subprocess
import sys

import gradio as gr
import uvicorn
from dotenv import load_dotenv

# HF Spaces injects secrets as real OS environment variables (no .env file
# present there), so this is a no-op in that environment. Locally, it makes
# `python app.py` see the same credentials `uvicorn app.main:app` does.
load_dotenv(".env")

from app.database.client import is_configured  # noqa: E402
from app.database.repository import get_session  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402

_REQUIRED_AGENT_ENV_VARS = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SARVAM_API_KEY",
    "OPENROUTER_API_KEY",
]

_worker_process: subprocess.Popen | None = None
_worker_skip_reason: str | None = None


def _start_agent_worker() -> None:
    """Launch the LiveKit voice agent worker as a background subprocess.

    Silently skips starting it (rather than crashing the whole Space) if
    required credentials aren't configured yet, so the read API and status
    UI stay usable while voice credentials are still being set up.
    """

    global _worker_process, _worker_skip_reason

    missing = [v for v in _REQUIRED_AGENT_ENV_VARS if not os.environ.get(v)]
    if missing:
        _worker_skip_reason = f"missing env vars: {', '.join(missing)}"
        print(f"Voice agent worker not started ({_worker_skip_reason}). See .env.example.")
        return

    _worker_process = subprocess.Popen(
        [sys.executable, "-m", "app.agent.agent", "start"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    atexit.register(lambda: _worker_process and _worker_process.terminate())
    print(f"Voice agent worker started (pid={_worker_process.pid}).")


def _worker_status() -> str:
    if _worker_process is None:
        return f"not started ({_worker_skip_reason})" if _worker_skip_reason else "not started"
    if _worker_process.poll() is None:
        return f"running (pid={_worker_process.pid})"
    return f"exited (code={_worker_process.returncode}) -- check Space logs"


def _status_markdown() -> str:
    return (
        "# Multilingual Health Insurance Voice Bot\n\n"
        f"- Voice agent worker: **{_worker_status()}**\n"
        f"- Supabase configured: **{'yes' if is_configured() else 'no'}**\n\n"
        "This Space hosts the read API (`/health`, `/sessions`, `/sessions/{id}`) and the "
        "LiveKit voice agent worker that answers calls dispatched to it via LiveKit SIP + "
        "Twilio. It does not take calls directly from this page -- dial the configured "
        "Twilio number. See the project README for architecture and setup details.\n\n"
        "*Demo project with fictional insurance policies -- not real insurance or "
        "financial advice.*"
    )


def _lookup_session(session_id: str) -> dict:
    session_id = (session_id or "").strip()
    if not session_id:
        return {"error": "Enter a session ID."}
    if not is_configured():
        return {"error": "Supabase is not configured on this Space."}
    try:
        session = get_session(session_id)
    except Exception as exc:  # noqa: BLE001 - surface any DB error to the UI rather than crash it
        return {"error": f"Lookup failed: {exc}"}
    if session is None:
        return {"error": f"No session found with id {session_id!r}."}
    return session.model_dump(mode="json")


with gr.Blocks(title="Multilingual Health Insurance Voice Bot") as _demo:
    status_md = gr.Markdown(_status_markdown())
    refresh_btn = gr.Button("Refresh status")
    refresh_btn.click(fn=_status_markdown, outputs=status_md)

    gr.Markdown("## Look up a completed call session")
    with gr.Row():
        session_id_input = gr.Textbox(label="Session ID", placeholder="e.g. 3f40dc16-669f-...")
        lookup_btn = gr.Button("Look up")
    session_output = gr.JSON(label="Session")
    lookup_btn.click(fn=_lookup_session, inputs=session_id_input, outputs=session_output)


# Gradio's own routes are mounted under "/"; FastAPI routes registered on
# `fastapi_app` before this call (in app.main) take precedence for their
# exact paths, per Gradio's documented FastAPI-mounting pattern.
app = gr.mount_gradio_app(fastapi_app, _demo, path="/")


if __name__ == "__main__":
    _start_agent_worker()
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
