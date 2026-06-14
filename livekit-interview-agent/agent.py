"""
LiveKit Agents - AI Mock Interview Demo
========================================
A mock interview agent with a two-stage state machine:
  Stage 1: SELF_INTRO  — candidate introduces themselves
  Stage 2: PAST_EXPERIENCE — candidate describes a past project or role
  Stage 3: COMPLETE    — interview wraps up

Transition logic:
  - Natural: after the user answers in a stage, the agent advances.
  - Fallback: if SELF_INTRO lasts over 60 seconds with no answer, auto-advance.

This demo supports two modes:
  1. voice mode with Google STT/TTS when Google Cloud ADC credentials exist
  2. text-mode fallback when only GOOGLE_API_KEY / Gemini API access exists
"""

import asyncio
import enum
import logging
import os
import time

from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.plugins import google

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("interview-agent")

try:
    from livekit.agents.pipeline import VoicePipelineAgent
    from livekit.plugins import silero
except Exception as exc:  # pragma: no cover - optional voice stack
    VoicePipelineAgent = None
    silero = None
    logger.warning("Voice pipeline imports unavailable; text-mode fallback only: %s", exc)


class InterviewStage(enum.Enum):
    SELF_INTRO = "self_intro"
    PAST_EXPERIENCE = "past_experience"
    COMPLETE = "complete"


STAGE_PROMPTS = {
    InterviewStage.SELF_INTRO: (
        "You are a professional, friendly AI interviewer running a mock interview. "
        "You are in the SELF INTRODUCTION stage. "
        "The opening question has already been asked — do NOT repeat it. "
        "Your only job right now is to listen to the candidate's introduction and respond "
        "with a brief, warm acknowledgement (1-2 sentences). "
        "Do not ask follow-up questions or move to any other topic."
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "You are a professional, friendly AI interviewer running a mock interview. "
        "You are in the PAST EXPERIENCE stage. "
        "The past-experience question has already been asked — do NOT repeat it. "
        "Listen to the candidate's answer and respond with a brief, encouraging reaction "
        "(1-2 sentences). You may ask one short clarifying question if it adds value. "
        "Do not introduce new topics."
    ),
    InterviewStage.COMPLETE: (
        "You are a professional, friendly AI interviewer. "
        "The mock interview is complete. "
        "Thank the candidate warmly and briefly (2-3 sentences). "
        "Wish them well in their job search."
    ),
}

STAGE_OPENINGS = {
    InterviewStage.SELF_INTRO: (
        "Hello! Welcome to your mock interview. "
        "Could you start by introducing yourself — "
        "tell me a bit about who you are and your background?"
    ),
    InterviewStage.PAST_EXPERIENCE: (
        "Thank you for that introduction! "
        "Now, could you tell me about a past experience or project you're proud of, "
        "and what your role was?"
    ),
    InterviewStage.COMPLETE: (
        "That wraps up our mock interview — thank you so much for your time! "
        "You did a great job. Best of luck with your job search!"
    ),
}

TURNS_TO_ADVANCE = 1
INTRO_TIMEOUT_SECONDS = 60


class InterviewStateMachine:
    """Tracks the current interview stage, elapsed stage time, and user turns."""

    def __init__(self):
        self.stage: InterviewStage = InterviewStage.SELF_INTRO
        self._stage_start: float = time.monotonic()
        self._user_turns: int = 0

    def time_in_stage(self) -> float:
        return time.monotonic() - self._stage_start

    def can_advance(self) -> bool:
        return self._user_turns >= TURNS_TO_ADVANCE

    def record_user_turn(self):
        self._user_turns += 1

    def advance(self) -> InterviewStage:
        if self.stage == InterviewStage.SELF_INTRO:
            self.stage = InterviewStage.PAST_EXPERIENCE
        elif self.stage == InterviewStage.PAST_EXPERIENCE:
            self.stage = InterviewStage.COMPLETE

        self._stage_start = time.monotonic()
        self._user_turns = 0
        logger.info("Transitioned to stage: %s", self.stage.value)
        return self.stage


def _google_cloud_adc_available() -> bool:
    """
    Google's Gemini API key is enough for the LLM, but Google STT/TTS require
    Google Cloud Application Default Credentials. Only enable voice mode when
    those credentials are present.
    """
    return bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))


async def _call_gemini(prompt: str) -> str:
    """Minimal Gemini call for text-mode fallback."""
    model = google.LLM(model="gemini-2.0-flash-exp")
    chat_ctx = llm.ChatContext().append(role="user", text=prompt)
    chunks = []

    async for chunk in model.chat(chat_ctx=chat_ctx):
        delta = getattr(chunk, "delta", None)
        if delta and getattr(delta, "content", None):
            chunks.append(delta.content)

    return "".join(chunks).strip()


async def _run_text_mode(ctx: JobContext):
    """
    Text-mode fallback for demos that have a Gemini API key but do not have
    Google Cloud STT/TTS credentials. This still demonstrates the required
    LiveKit job dispatch plus the staged interview state machine.
    """
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_NONE)
    state = InterviewStateMachine()

    logger.info("Running in text-mode fallback. Room: %s", ctx.room.name)
    print("\n=== TEXT MODE MOCK INTERVIEW ===")
    print(STAGE_OPENINGS[InterviewStage.SELF_INTRO])

    async def timeout_watchdog():
        await asyncio.sleep(INTRO_TIMEOUT_SECONDS)
        if state.stage == InterviewStage.SELF_INTRO and not state.can_advance():
            logger.warning("SELF_INTRO timeout fired; moving to PAST_EXPERIENCE")
            state.advance()
            print("\n" + STAGE_OPENINGS[state.stage])

    watchdog_task = asyncio.create_task(timeout_watchdog())

    while state.stage != InterviewStage.COMPLETE:
        user_text = await asyncio.to_thread(input, "\nCandidate: ")
        if not user_text.strip():
            continue

        prompt = (
            f"{STAGE_PROMPTS[state.stage]}\n\n"
            f"Candidate said: {user_text}\n\n"
            "Respond briefly as the interviewer."
        )
        response = await _call_gemini(prompt)
        print(f"\nInterviewer: {response}")

        state.record_user_turn()
        if state.can_advance():
            state.advance()
            print("\n" + STAGE_OPENINGS[state.stage])

    watchdog_task.cancel()


async def _do_voice_advance(agent: VoicePipelineAgent, state: InterviewStateMachine):
    if state.stage == InterviewStage.COMPLETE:
        return

    new_stage = state.advance()
    agent.chat_ctx.messages[0] = llm.ChatMessage(
        role="system",
        content=STAGE_PROMPTS[new_stage],
    )
    await agent.say(
        STAGE_OPENINGS[new_stage],
        allow_interruptions=new_stage != InterviewStage.COMPLETE,
    )


async def _run_voice_mode(ctx: JobContext):
    """Full voice mode. Requires Google Cloud ADC for google.STT/google.TTS."""
    if VoicePipelineAgent is None or silero is None:
        raise RuntimeError("Voice dependencies are unavailable")

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    state = InterviewStateMachine()

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=STAGE_PROMPTS[InterviewStage.SELF_INTRO],
    )

    agent = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=google.STT(),
        llm=google.LLM(model="gemini-2.0-flash-exp"),
        tts=google.TTS(),
        chat_ctx=initial_ctx,
    )

    agent.start(ctx.room)
    await agent.say(STAGE_OPENINGS[InterviewStage.SELF_INTRO], allow_interruptions=True)

    @agent.on("user_speech_committed")
    def on_user_speech(_msg: llm.ChatMessage):
        if state.stage == InterviewStage.COMPLETE:
            return

        state.record_user_turn()
        logger.info(
            "[%s] user turn #%d  (%.1fs in stage)",
            state.stage.value,
            state._user_turns,
            state.time_in_stage(),
        )

        if state.can_advance():
            asyncio.ensure_future(_do_voice_advance(agent, state))

    async def timeout_watchdog():
        while state.stage == InterviewStage.SELF_INTRO:
            await asyncio.sleep(5)
            if (
                state.stage == InterviewStage.SELF_INTRO
                and state.time_in_stage() >= INTRO_TIMEOUT_SECONDS
                and not state.can_advance()
            ):
                logger.warning(
                    "SELF_INTRO timeout after %.1fs — forcing advance",
                    state.time_in_stage(),
                )
                await _do_voice_advance(agent, state)
                break

    asyncio.ensure_future(timeout_watchdog())
    await asyncio.sleep(float("inf"))


async def entrypoint(ctx: JobContext):
    if _google_cloud_adc_available():
        logger.info("Google Cloud ADC found; starting full voice pipeline")
        await _run_voice_mode(ctx)
    else:
        logger.info("No Google Cloud ADC found; starting text-mode fallback")
        await _run_text_mode(ctx)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
