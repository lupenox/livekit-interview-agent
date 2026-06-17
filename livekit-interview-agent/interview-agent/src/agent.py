"""LiveKit + Gemini two-stage voice mock interview agent.

Run locally with:
    python agent.py console

Run as a LiveKit worker with:
    python agent.py start
"""

from __future__ import annotations

from __future__ import annotations

import asyncio
import enum
import logging
import os
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions
from livekit.plugins import deepgram, elevenlabs, openai, silero

load_dotenv()
load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("interview-agent")

INTRO_TIMEOUT_SECONDS = 60
TURNS_TO_ADVANCE = 1
GEMINI_MODEL = "gemini-2.5-flash"
DEEPGRAM_MODEL = "nova-3"
ELEVENLABS_MODEL = "eleven_turbo_v2_5"


class InterviewStage(enum.Enum):
    SELF_INTRO = "self_intro"
    PAST_EXPERIENCE = "past_experience"
    COMPLETE = "complete"


STAGE_PROMPTS = {
    InterviewStage.SELF_INTRO: (
        "You are a professional, friendly AI interviewer running a mock interview. "
        "You are in the SELF INTRODUCTION stage. The opening question has already "
        "been asked, so do not repeat it. Listen to the candidate's introduction "
        "and respond with a brief warm acknowledgement in one or two sentences. "
        "Do not ask follow-up questions yet."
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "You are a professional, friendly AI interviewer running a mock interview. "
        "You are in the PAST EXPERIENCE / PROJECT DISCUSSION stage. "
        "Your goal is to have a short but meaningful conversation about the candidate's project or experience. "
        "Ask only ONE short follow-up question at a time. "
        "Do not ask multiple questions in the same response. "
        "If the candidate says they are done, finished, or wants to stop, politely end the interview immediately. "
        "Keep responses brief, natural, and interview-like."
    ),
    InterviewStage.COMPLETE: (
        "The mock interview is complete. Thank the candidate warmly and briefly. "
        "Wish them well in their job search. Do not ask another interview question."
    ),
}

STAGE_OPENINGS = {
    InterviewStage.SELF_INTRO: (
        "Hello, welcome to your mock interview. Could you start by introducing "
        "yourself and telling me a bit about your background?"
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "Thank you for that introduction. Now, could you tell me about a past "
        "experience or project you're proud of, and what your role was?"
    ),
    InterviewStage.COMPLETE: (
        "That wraps up our mock interview. Thank you so much for your time. "
        "You did a great job, and I wish you the best with your job search."
    ),
}


@dataclass
class InterviewStateMachine:
    """Small state machine for the two required interview stages."""

    stage: InterviewStage = InterviewStage.SELF_INTRO
    user_turns: int = 0
    stage_started_at: float = field(default_factory=time.monotonic)
    advancing: bool = False

    def time_in_stage(self) -> float:
        return time.monotonic() - self.stage_started_at

    def record_user_turn(self) -> None:
        self.user_turns += 1

    def should_advance(self) -> bool:
        # Only move from intro to project discussion.
        # Do NOT auto-end the interview; let the interviewer keep asking follow-ups.
        if self.stage == InterviewStage.SELF_INTRO:
            return self.user_turns >= 1 and self.time_in_stage() >= 8
        return False

    def advance(self) -> InterviewStage:
        if self.stage == InterviewStage.SELF_INTRO:
            self.stage = InterviewStage.PAST_EXPERIENCE
        elif self.stage == InterviewStage.PAST_EXPERIENCE:
            self.stage = InterviewStage.COMPLETE
        self.user_turns = 0
        self.stage_started_at = time.monotonic()
        logger.info("Interview stage advanced to %s", self.stage.value)
        return self.stage


class InterviewAgent(Agent):
    def __init__(self, state: InterviewStateMachine) -> None:
        self.state = state
        super().__init__(instructions=STAGE_PROMPTS[state.stage])


async def _advance_stage(session: AgentSession, agent: InterviewAgent) -> None:
    """Advance once, update the system instructions, and speak the next prompt."""
    state = agent.state
    if state.advancing or state.stage == InterviewStage.COMPLETE:
        return

    state.advancing = True
    try:
        next_stage = state.advance()
        await agent.update_instructions(STAGE_PROMPTS[next_stage])
        await session.generate_reply(
            instructions=(
                "Say exactly this stage transition prompt, naturally and without "
                f"adding extra questions: {STAGE_OPENINGS[next_stage]}"
            ),
            allow_interruptions=next_stage != InterviewStage.COMPLETE,
        )
    finally:
        state.advancing = False


def _require_env(name: str) -> str:
    """Return a required environment value or raise a helpful startup error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Add it to .env/.env.local before starting the voice agent."
        )
    return value


def _log_required_configuration() -> None:
    missing = [
        name
        for name in (
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "DEEPGRAM_API_KEY",
            "ELEVENLABS_API_KEY",
            "GOOGLE_API_KEY",
        )
        if not os.getenv(name)
    ]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
    else:
        logger.info(
            "Required LiveKit, Deepgram, ElevenLabs, and Gemini keys are configured"
        )


async def entrypoint(ctx: JobContext) -> None:
    """LiveKit worker entrypoint.

    Audio pipeline: the room audio is subscribed by `ctx.connect()`. Silero VAD
    detects candidate speech boundaries, Deepgram converts candidate speech to
    text, Gemini produces the interviewer response, and ElevenLabs publishes the
    response back to the room as an agent audio track. In short:
    Deepgram STT → Gemini LLM → ElevenLabs TTS.
    """

    _log_required_configuration()
    deepgram_api_key = _require_env("DEEPGRAM_API_KEY")
    elevenlabs_api_key = _require_env("ELEVENLABS_API_KEY")

    try:
        await ctx.connect()
        logger.info("Connected to LiveKit room: %s", ctx.room.name)
    except Exception:
        logger.exception("Failed to connect to LiveKit room")
        raise
    state = InterviewStateMachine()
    interview_agent = InterviewAgent(state)

    session = AgentSession(
        # Voice Activity Detection: lets the agent know when the user starts and
        # stops speaking so complete turns are sent through the pipeline.
        vad=silero.VAD.load(),
        # STT: candidate microphone audio -> text using Deepgram's free-tier-friendly API.
        stt=deepgram.STT(
            model=DEEPGRAM_MODEL,
            language="en-US",
            api_key=deepgram_api_key,
        ),
        # LLM: transcribed text + current stage instructions -> interviewer text. Gemini
        # only needs GOOGLE_API_KEY, so it stays budget-friendly for this demo.
        llm=openai.LLM(
    model="llama-3.3-70b-versatile",
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
),
        # TTS: interviewer text -> speech published back into LiveKit using ElevenLabs.
        tts=elevenlabs.TTS(model=ELEVENLABS_MODEL, api_key=elevenlabs_api_key),
    )

    @session.on("error")
    def _on_error(event) -> None:
        logger.error("LiveKit agent session error: %s", event)

    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(event) -> None:
        if not getattr(event, "is_final", False) or state.stage == InterviewStage.COMPLETE:
            return
        transcript = (getattr(event, "transcript", "") or "").strip()
        if not transcript:
            return
        state.record_user_turn()
        logger.info(
            "Candidate final transcript in %s (turn %s, %.1fs): %s",
            state.stage.value,
            state.user_turns,
            state.time_in_stage(),
            transcript,
        )
        if state.should_advance():
            asyncio.create_task(_advance_stage(session, interview_agent))

    try:
        await session.start(room=ctx.room, agent=interview_agent)
        logger.info("Voice session started with Deepgram STT → Gemini → ElevenLabs TTS")
    except Exception:
        logger.exception("Failed to start the LiveKit voice session")
        raise

    await session.say(
        "Hi, welcome to your mock interview. Could you start by introducing yourself and telling me a bit about your background?",
        allow_interruptions=True,
    )



if __name__ == "__main__":
    agents.cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="interview-agent",
    ))
