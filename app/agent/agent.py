"""LiveKit Agents voice entrypoint: Silero VAD -> Sarvam STT -> language
detection (app.agent.language) -> OpenRouter LLM (via tools in
app.agent.tools) -> Sarvam TTS -> LiveKit room audio.

The only module that touches the LiveKit Agents SDK directly. LiveKit
dispatches a room job like any other once a SIP call lands, so no
SIP-specific code is needed here -- `ctx.room` already has the caller as a
participant once `ctx.connect()` resolves.

VENDOR NOTE: uses Sarvam AI rather than the originally-specified Deepgram --
Deepgram has no STT model for Marathi/Kannada and its TTS voices are
English-only, both hard blockers for this project's multilingual
requirement (see README "Tech Stack"). Isolated to this module, so swapping
providers again later doesn't touch anything else.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions, cli
from livekit.agents import llm as agent_llm
from livekit.plugins import sarvam, silero

from app.agent.language import SUPPORTED_LANGUAGES
from app.agent.llm import build_openrouter_llm
from app.agent.prompts import BASE_SYSTEM_PROMPT, greeting_for, language_instruction
from app.agent.state import AgentUserdata
from app.agent.tools import ALL_TOOLS
from app.config import get_settings
from app.sessions.manager import SessionManager
from app.sessions.models import CallSession

load_dotenv(".env")

logger = logging.getLogger("insurance-voice-agent")

# BCP-47 codes Sarvam expects, keyed by our internal ISO 639-1 codes.
LANGUAGE_TO_BCP47: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "mr": "mr-IN",
    "ta": "ta-IN",
    "kn": "kn-IN",
}

# Must be a speaker compatible with the default TTS model (bulbul:v3) --
# see the sarvam.TTS `speaker` docs for the current per-model roster.
TTS_SPEAKER = "priya"


def _build_tts_by_language() -> dict[str, sarvam.TTS]:
    return {
        lang: sarvam.TTS(
            target_language_code=bcp47,
            speaker=TTS_SPEAKER,
            # linear16 (raw PCM) instead of the mp3 default avoids a
            # real-time decode step that caused audible choppiness.
            output_audio_codec="linear16",
        )
        for lang, bcp47 in LANGUAGE_TO_BCP47.items()
    }


class InsuranceAgent(Agent):
    """The health-insurance assistant persona ("Maya"). See app.agent.prompts."""

    def __init__(self, tts_by_language: dict[str, sarvam.TTS]) -> None:
        super().__init__(instructions=BASE_SYSTEM_PROMPT, tools=ALL_TOOLS)
        self._tts_by_language = tts_by_language

    async def on_enter(self) -> None:
        userdata: AgentUserdata = self.session.userdata
        language = userdata.language_tracker.current_language
        greeting = greeting_for(language)
        userdata.session_manager.record_message("assistant", greeting, language)
        await self.session.say(greeting)

    async def on_user_turn_completed(
        self, turn_ctx: agent_llm.ChatContext, new_message: agent_llm.ChatMessage
    ) -> None:
        userdata: AgentUserdata = self.session.userdata
        text = new_message.text_content or ""
        if not text.strip():
            return

        language = userdata.language_tracker.update(text)
        userdata.session_manager.record_message("user", text, language)

        self.update_instructions(f"{BASE_SYSTEM_PROMPT}\n\n{language_instruction(language)}")
        self.update_options(tts=self._tts_by_language.get(language, self._tts_by_language["en"]))

        # Belt-and-braces: a system-prompt update alone isn't reliable once a
        # conversation has built up momentum in one language, so also edit
        # the outgoing message directly -- a much harder-to-ignore signal.
        new_message.content.append(f"[{language_instruction(language)}]")


def _extract_sip_call_id(ctx: JobContext) -> str | None:
    """Best-effort SIP call identifier from the inbound participant's attributes.

    Returns None for non-SIP (e.g. local testing) rooms rather than raising —
    this is metadata, not something a call should fail over.
    """

    for participant in ctx.room.remote_participants.values():
        call_id = participant.attributes.get("sip.callID")
        if call_id:
            return call_id
    return None


async def entrypoint(ctx: JobContext) -> None:
    """LiveKit job entrypoint: one call per invocation of this function."""

    settings = get_settings()
    if not settings.sarvam_api_key:
        raise RuntimeError("SARVAM_API_KEY is not set. Configure it in .env before starting the voice agent.")

    await ctx.connect()

    call_id = _extract_sip_call_id(ctx)
    call_session = CallSession(livekit_session_id=ctx.room.name, call_id=call_id)
    session_manager = SessionManager(session=call_session)
    userdata = AgentUserdata(session_manager=session_manager)

    tts_by_language = _build_tts_by_language()

    session: AgentSession[AgentUserdata] = AgentSession(
        vad=silero.VAD.load(),
        stt=sarvam.STT(model="saarika:v2.5", language="unknown"),
        llm=build_openrouter_llm(),
        tts=tts_by_language["en"],
        userdata=userdata,
    )

    def _on_conversation_item_added(event: agents.ConversationItemAddedEvent) -> None:
        item = event.item
        if getattr(item, "role", None) == "assistant":
            text = item.text_content or ""
            if text.strip():
                language = userdata.language_tracker.current_language
                userdata.session_manager.record_message("assistant", text, language)

    session.on("conversation_item_added", _on_conversation_item_added)

    async def _finalize() -> None:
        try:
            session_manager.complete()
        except Exception:  # noqa: BLE001 - never block shutdown on persistence
            logger.exception("Failed to finalize session %s", call_session.id)

    ctx.add_shutdown_callback(_finalize)

    try:
        await session.start(
            agent=InsuranceAgent(tts_by_language=tts_by_language),
            room=ctx.room,
            room_input_options=RoomInputOptions(),
        )
    except Exception:
        logger.exception("Voice session %s failed", call_session.id)
        session_manager.fail()
        raise


def main() -> None:
    assert set(LANGUAGE_TO_BCP47) == set(SUPPORTED_LANGUAGES)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="insurance-voice-agent"))


if __name__ == "__main__":
    main()
