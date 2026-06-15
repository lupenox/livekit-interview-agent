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
from livekit.agents import Agent, AgentSession, JobContext, TurnHandlingOptions, WorkerOptions
from livekit.plugins import deepgram, elevenlabs, google, silero

load_dotenv()
load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("interview-agent")

INTRO_GENTLE_NUDGE_SECONDS = 45
INTRO_STRONG_NUDGE_SECONDS = 90
INTRO_FORCE_ADVANCE_SECONDS = 150
PAST_EXPERIENCE_GENTLE_NUDGE_SECONDS = 90
PAST_EXPERIENCE_STRONG_NUDGE_SECONDS = 180
PAST_EXPERIENCE_FORCE_WRAP_SECONDS = 360
MIN_INTRO_TURNS_TO_ADVANCE = 2
MIN_INTRO_WORDS_TO_ADVANCE = 28
MIN_PAST_EXPERIENCE_TURNS = 4
MIN_PAST_EXPERIENCE_WORDS = 80
GEMINI_MODEL = "gemini-2.5-flash"
DEEPGRAM_MODEL = "nova-3"
ELEVENLABS_MODEL = "eleven_turbo_v2_5"


class InterviewStage(enum.Enum):
    SELF_INTRO = "self_intro"
    PAST_EXPERIENCE = "past_experience"
    COMPLETE = "complete"


STAGE_PROMPTS = {
    InterviewStage.SELF_INTRO: (
        "You are a friendly but professional mock interviewer. Start from zero "
        "knowledge every session: do not imply you know the candidate's name, role, "
        "background, projects, company, or goals until they tell you. You are in "
        "the SELF INTRODUCTION stage. Listen for a real introduction that includes "
        "some combination of current role/focus, background, skills, interests, and "
        "what they are looking for. If the answer is brief or incomplete, stay in "
        "this stage and ask one specific, low-pressure follow-up to help them expand. "
        "Do not summarize details they did not say. Do not repeat the opening prompt."
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "You are a friendly but professional mock interviewer in the PAST "
        "EXPERIENCE / PROJECT DISCUSSION stage. Start only from details the "
        "candidate has actually shared. Make this feel like a real conversation, "
        "not a checklist. Ask one thoughtful follow-up at a time and wait for the "
        "candidate's answer. Dig into ownership, constraints, tradeoffs, technical "
        "or product decisions, collaboration, obstacles, measurable impact, and "
        "lessons learned. If an answer is short, ask for a concrete example or more "
        "detail instead of wrapping up. Do not end the interview until there has "
        "been a meaningful back-and-forth."
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
        "Thanks, that's helpful context. I'd like to shift into your past "
        "experience now. Could you walk me through one project or role you're "
        "proud of — the goal, what you personally owned, and why it mattered?"
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
    intro_gentle_nudge_sent: bool = False
    intro_strong_nudge_sent: bool = False
    past_experience_gentle_nudge_sent: bool = False
    past_experience_strong_nudge_sent: bool = False

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
            return (
                self.user_turns >= MIN_INTRO_TURNS_TO_ADVANCE
                and self.total_words >= MIN_INTRO_WORDS_TO_ADVANCE
            )
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
        self.intro_gentle_nudge_sent = False
        self.intro_strong_nudge_sent = False
        self.past_experience_gentle_nudge_sent = False
        self.past_experience_strong_nudge_sent = False
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
                "Make a brief, natural bridge into the next part. Do not claim any "
                "facts the candidate did not share. Use this message as the substance, "
                "but sound conversational instead of scripted: "
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
            no_delay=False,
            endpointing_ms=800,
        ),
        # LLM: transcribed text + current stage instructions -> interviewer text. Gemini
        # only needs GOOGLE_API_KEY, so it stays budget-friendly for this demo.
        llm=google.LLM(model=GEMINI_MODEL),
        # TTS: interviewer text -> speech published back into LiveKit using ElevenLabs.
        tts=elevenlabs.TTS(model=ELEVENLABS_MODEL, api_key=elevenlabs_api_key),
        # Give candidates time to finish a thought before the agent responds.
        # These endpointing settings reduce false turn endings and interruptions.
        turn_handling=TurnHandlingOptions(
            endpointing={"mode": "fixed", "min_delay": 1.2, "max_delay": 6.0},
            interruption={"min_duration": 0.8, "min_words": 2},
        ),
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
                and not state.intro_gentle_nudge_sent
                and state.time_since_user_turn() >= INTRO_GENTLE_NUDGE_SECONDS
                and not state.should_advance()
            ):
                state.intro_gentle_nudge_sent = True
                logger.info("Sending gentle self-introduction nudge")
                await session.generate_reply(
                    instructions=(
                        "The candidate has been quiet or gave a very short intro. "
                        "Gently ask them to share a bit more about their background "
                        "or current focus. Keep it warm and under two sentences."
                    ),
                    allow_interruptions=False,
                )
                continue

            if (
                state.stage == InterviewStage.SELF_INTRO
                and not state.intro_strong_nudge_sent
                and state.time_since_user_turn() >= INTRO_STRONG_NUDGE_SECONDS
                and not state.should_advance()
            ):
                state.intro_strong_nudge_sent = True
                logger.info("Sending stronger self-introduction nudge")
                await session.generate_reply(
                    instructions=(
                        "The introduction is still incomplete. Ask one clearer but "
                        "friendly prompt: invite them to mention their role or focus, "
                        "one relevant skill or experience, and what they hope to do next."
                    ),
                    allow_interruptions=False,
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
                and not state.past_experience_gentle_nudge_sent
                and state.time_since_user_turn() >= PAST_EXPERIENCE_GENTLE_NUDGE_SECONDS
                and not state.should_advance()
            ):
                state.past_experience_gentle_nudge_sent = True
                logger.info("Sending gentle past-experience nudge")
                await session.generate_reply(
                    instructions=(
                        "The project discussion has stalled or stayed surface-level. "
                        "Ask one specific follow-up about what the candidate personally "
                        "owned or what decision they had to make. Do not wrap up yet."
                    ),
                    allow_interruptions=False,
                )
                continue

            if (
                state.stage == InterviewStage.PAST_EXPERIENCE
                and not state.past_experience_strong_nudge_sent
                and state.time_since_user_turn() >= PAST_EXPERIENCE_STRONG_NUDGE_SECONDS
                and not state.should_advance()
            ):
                state.past_experience_strong_nudge_sent = True
                logger.info("Sending stronger past-experience nudge")
                await session.generate_reply(
                    instructions=(
                        "The project discussion still needs depth. Ask a direct but "
                        "supportive follow-up about a challenge, tradeoff, collaboration "
                        "moment, measurable impact, or lesson learned. Do not wrap up yet."
                    ),
                    allow_interruptions=False,
                )
                continue

            if (
                state.stage == InterviewStage.PAST_EXPERIENCE
                and state.time_in_stage() >= PAST_EXPERIENCE_FORCE_WRAP_SECONDS
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
