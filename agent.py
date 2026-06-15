"""LiveKit + Gemini two-stage voice mock interview agent.

Run locally with:
    python agent.py console

Run as a LiveKit worker with:
    python agent.py start
"""

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
from livekit.plugins import deepgram, elevenlabs, google, silero

load_dotenv()
load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("interview-agent")

INTRO_NUDGE_SECONDS = 45
INTRO_FORCE_ADVANCE_SECONDS = 90
PAST_EXPERIENCE_NUDGE_SECONDS = 75
PAST_EXPERIENCE_WRAP_SECONDS = 210
MIN_INTRO_WORDS_TO_ADVANCE = 12
MIN_PAST_EXPERIENCE_TURNS = 3
MIN_PAST_EXPERIENCE_WORDS = 35
GEMINI_MODEL = "gemini-2.5-flash"
DEEPGRAM_MODEL = "nova-3"
ELEVENLABS_MODEL = "eleven_turbo_v2_5"


class InterviewStage(enum.Enum):
    SELF_INTRO = "self_intro"
    PAST_EXPERIENCE = "past_experience"
    COMPLETE = "complete"


STAGE_PROMPTS = {
    InterviewStage.SELF_INTRO: (
        "You are a friendly but professional mock interviewer. You are in the "
        "SELF INTRODUCTION stage. The candidate should introduce themselves, their "
        "background, and what they are looking for. If their answer is only a few "
        "words, do not move on yet; warmly ask one specific, low-pressure question "
        "to help them expand, such as their current focus, relevant background, or "
        "what kind of role they are targeting. If they give a real introduction, "
        "acknowledge it naturally and be ready to transition to project experience. "
        "Avoid repeating the exact opening prompt."
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "You are a friendly but professional mock interviewer in the PAST "
        "EXPERIENCE / PROJECT DISCUSSION stage. Make this feel like a real "
        "conversation, not a checklist. Ask one thoughtful follow-up at a time. "
        "Prefer deeper questions about context, ownership, technical or product "
        "decisions, tradeoffs, obstacles, collaboration, measurable impact, and "
        "what the candidate learned. Build on details the candidate already shared. "
        "Do not end the interview after the first short project answer; keep the "
        "discussion going for several turns unless the candidate clearly wants to stop."
    ),
    InterviewStage.COMPLETE: (
        "The mock interview is complete. Give a warm, concise wrap-up that thanks "
        "the candidate, briefly reflects that they discussed their background and "
        "project experience, and wishes them well. Do not ask another interview question."
    ),
}

STAGE_OPENINGS = {
    InterviewStage.SELF_INTRO: (
        "Hello, welcome to your mock interview. Could you start by introducing "
        "yourself and telling me a bit about your background?"
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "Thanks, that gives me a helpful starting point. Let's shift into your "
        "past experience. Could you walk me through one project or role you're "
        "proud of — what the goal was, what you owned, and why it mattered?"
    ),
    InterviewStage.COMPLETE: (
        "That's a good place for us to wrap up. Thank you for sharing both your "
        "background and your project experience today. I hope this was useful, "
        "and I wish you the best with your next interviews."
    ),
}


@dataclass
class InterviewStateMachine:
    """Small state machine for the two required interview stages."""

    stage: InterviewStage = InterviewStage.SELF_INTRO
    user_turns: int = 0
    total_words: int = 0
    last_user_turn_at: float = field(default_factory=time.monotonic)
    stage_started_at: float = field(default_factory=time.monotonic)
    advancing: bool = False
    intro_nudge_sent: bool = False
    past_experience_nudge_sent: bool = False

    def time_in_stage(self) -> float:
        return time.monotonic() - self.stage_started_at

    def time_since_user_turn(self) -> float:
        return time.monotonic() - self.last_user_turn_at

    def record_user_turn(self, transcript: str) -> None:
        self.user_turns += 1
        self.total_words += len(transcript.split())
        self.last_user_turn_at = time.monotonic()

    def should_advance(self) -> bool:
        if self.stage == InterviewStage.SELF_INTRO:
            return self.user_turns >= 1 and self.total_words >= MIN_INTRO_WORDS_TO_ADVANCE
        if self.stage == InterviewStage.PAST_EXPERIENCE:
            return (
                self.user_turns >= MIN_PAST_EXPERIENCE_TURNS
                and self.total_words >= MIN_PAST_EXPERIENCE_WORDS
            )
        return False

    def advance(self) -> InterviewStage:
        if self.stage == InterviewStage.SELF_INTRO:
            self.stage = InterviewStage.PAST_EXPERIENCE
        elif self.stage == InterviewStage.PAST_EXPERIENCE:
            self.stage = InterviewStage.COMPLETE
        self.user_turns = 0
        self.total_words = 0
        now = time.monotonic()
        self.stage_started_at = now
        self.last_user_turn_at = now
        self.intro_nudge_sent = False
        self.past_experience_nudge_sent = False
        logger.info("Interview stage advanced to %s", self.stage.value)
        return self.stage


class InterviewAgent(Agent):
    def __init__(self, state: InterviewStateMachine) -> None:
        self.state = state
        super().__init__(instructions=STAGE_PROMPTS[state.stage])


async def _advance_stage(
    session: AgentSession,
    agent: InterviewAgent,
    *,
    reason: str,
) -> None:
    """Advance once, update the system instructions, and speak the next prompt."""
    state = agent.state
    if state.advancing or state.stage == InterviewStage.COMPLETE:
        return

    state.advancing = True
    try:
        logger.info("Advancing from %s because %s", state.stage.value, reason)
        next_stage = state.advance()
        await agent.update_instructions(STAGE_PROMPTS[next_stage])
        await session.generate_reply(
            instructions=(
                "Transition smoothly and conversationally into the next part. Use this "
                "message as the substance, but sound natural instead of scripted: "
                f"{STAGE_OPENINGS[next_stage]}"
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
    _require_env("GOOGLE_API_KEY")

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
        llm=google.LLM(model=GEMINI_MODEL),
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
        state.record_user_turn(transcript)
        logger.info(
            "Candidate final transcript in %s (turn %s, %s words, %.1fs): %s",
            state.stage.value,
            state.user_turns,
            state.total_words,
            state.time_in_stage(),
            transcript,
        )
        if state.should_advance():
            asyncio.create_task(
                _advance_stage(
                    session,
                    interview_agent,
                    reason="candidate gave enough detail for this stage",
                )
            )

    try:
        await session.start(room=ctx.room, agent=interview_agent)
        logger.info("Voice session started with Deepgram STT → Gemini → ElevenLabs TTS")
    except Exception:
        logger.exception("Failed to start the LiveKit voice session")
        raise

    await session.generate_reply(
        instructions=(
            "Greet the candidate by saying exactly this opening prompt, naturally: "
            f"{STAGE_OPENINGS[InterviewStage.SELF_INTRO]}"
        ),
        allow_interruptions=True,
    )

    async def timeout_watchdog() -> None:
        while state.stage != InterviewStage.COMPLETE:
            await asyncio.sleep(5)

            if state.advancing:
                continue

            if (
                state.stage == InterviewStage.SELF_INTRO
                and not state.intro_nudge_sent
                and state.time_since_user_turn() >= INTRO_NUDGE_SECONDS
                and not state.should_advance()
            ):
                state.intro_nudge_sent = True
                logger.info("Sending self-introduction nudge after quiet/short response")
                await session.generate_reply(
                    instructions=(
                        "The candidate has been quiet or gave a very short intro. "
                        "Gently invite them to add a little more about their background, "
                        "current focus, or target role. Keep it under two sentences."
                    ),
                    allow_interruptions=True,
                )
                continue

            if (
                state.stage == InterviewStage.SELF_INTRO
                and state.time_in_stage() >= INTRO_FORCE_ADVANCE_SECONDS
            ):
                logger.warning("Self-introduction fallback advancing after timeout")
                await _advance_stage(
                    session,
                    interview_agent,
                    reason="self-introduction timeout fallback",
                )
                continue

            if (
                state.stage == InterviewStage.PAST_EXPERIENCE
                and not state.past_experience_nudge_sent
                and state.time_since_user_turn() >= PAST_EXPERIENCE_NUDGE_SECONDS
                and not state.should_advance()
            ):
                state.past_experience_nudge_sent = True
                logger.info("Sending past-experience nudge after inactivity")
                await session.generate_reply(
                    instructions=(
                        "The project discussion has stalled. Ask one specific, "
                        "helpful follow-up about the candidate's ownership, a challenge "
                        "they faced, or the impact of the work. Do not wrap up yet."
                    ),
                    allow_interruptions=True,
                )
                continue

            if (
                state.stage == InterviewStage.PAST_EXPERIENCE
                and state.time_in_stage() >= PAST_EXPERIENCE_WRAP_SECONDS
            ):
                logger.warning("Past-experience fallback wrapping after timeout")
                await _advance_stage(
                    session,
                    interview_agent,
                    reason="past-experience timeout fallback",
                )
                return

    asyncio.create_task(timeout_watchdog())


if __name__ == "__main__":
    agents.cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
