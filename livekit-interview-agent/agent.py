"""
LiveKit Agents - AI Mock Interview Demo
========================================
A voice interview agent with a two-stage state machine:
  Stage 1: SELF_INTRO  — candidate introduces themselves
  Stage 2: PAST_EXPERIENCE — candidate describes a past project or role
  Stage 3: COMPLETE    — interview wraps up

Transition logic:
  - Natural: after the user finishes speaking in a stage, the agent advances.
  - Fallback: if SELF_INTRO lasts over 60 seconds with no answer, auto-advance.
"""

import asyncio
import enum
import logging
import time

from dotenv import load_dotenv
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import google, silero

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("interview-agent")


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

class InterviewStage(enum.Enum):
    SELF_INTRO = "self_intro"
    PAST_EXPERIENCE = "past_experience"
    COMPLETE = "complete"


# System prompt injected at position [0] of the chat context for each stage.
# Keeps the LLM focused on its role without bleeding across stages.
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

# Opening line spoken aloud when entering each stage.
# Stored separately so the agent can say them with agent.say() rather than
# waiting for the LLM to re-generate them each time.
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

# How many user speech turns to wait for before advancing from a stage.
# Set to 1 so the agent advances after the candidate gives their first answer.
TURNS_TO_ADVANCE = 1

# Seconds to wait in SELF_INTRO before forcing a transition (fallback).
INTRO_TIMEOUT_SECONDS = 60


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class InterviewStateMachine:
    """
    Lightweight state machine that tracks the current interview stage,
    how long we've been in it, and how many user turns have occurred.
    """

    def __init__(self):
        self.stage: InterviewStage = InterviewStage.SELF_INTRO
        self._stage_start: float = time.monotonic()
        self._user_turns: int = 0

    # --- Queries ---

    def time_in_stage(self) -> float:
        """Seconds elapsed since entering the current stage."""
        return time.monotonic() - self._stage_start

    def can_advance(self) -> bool:
        """True once the user has spoken enough turns in this stage."""
        return self._user_turns >= TURNS_TO_ADVANCE

    # --- Mutations ---

    def record_user_turn(self):
        """Increment the user-turn counter for the current stage."""
        self._user_turns += 1

    def advance(self) -> InterviewStage:
        """
        Move to the next stage, reset per-stage counters, and return the new stage.
        Call only when can_advance() is True or a timeout fires.
        """
        if self.stage == InterviewStage.SELF_INTRO:
            self.stage = InterviewStage.PAST_EXPERIENCE
        elif self.stage == InterviewStage.PAST_EXPERIENCE:
            self.stage = InterviewStage.COMPLETE

        self._stage_start = time.monotonic()
        self._user_turns = 0
        logger.info("Transitioned to stage: %s", self.stage.value)
        return self.stage


# ---------------------------------------------------------------------------
# Stage transition helper
# ---------------------------------------------------------------------------

async def _do_advance(agent: VoicePipelineAgent, state: InterviewStateMachine):
    """
    Advance the state machine and update the agent:
      1. Swap the system prompt so the LLM stays in-role for the new stage.
      2. Speak the stage's opening line.
    This function is safe to call from both the event handler and the watchdog.
    """
    if state.stage == InterviewStage.COMPLETE:
        return  # Nothing left to advance

    new_stage = state.advance()

    # Replace the system message in the chat context (always at index 0).
    agent.chat_ctx.messages[0] = llm.ChatMessage(
        role="system",
        content=STAGE_PROMPTS[new_stage],
    )

    # Speak the opening question / closing statement for the new stage.
    # allow_interruptions=False on the final closing so it plays in full.
    allow_interruptions = new_stage != InterviewStage.COMPLETE
    await agent.say(STAGE_OPENINGS[new_stage], allow_interruptions=allow_interruptions)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def entrypoint(ctx: JobContext):
    """
    Called by the LiveKit worker when a new room job is dispatched.
    Wires up the voice pipeline and drives the interview state machine.
    """
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    state = InterviewStateMachine()

    # Build the initial chat context with the SELF_INTRO system prompt.
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=STAGE_PROMPTS[InterviewStage.SELF_INTRO],
    )

    # Assemble the voice pipeline: VAD → STT (Google) → LLM (Gemini) → TTS (Google).
    agent = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=google.STT(),
        llm=google.LLM(model="gemini-2.0-flash-exp"),
        tts=google.TTS(),
        chat_ctx=initial_ctx,
    )

    agent.start(ctx.room)

    # Speak the first question to kick off the interview.
    await agent.say(STAGE_OPENINGS[InterviewStage.SELF_INTRO], allow_interruptions=True)

    # ------------------------------------------------------------------
    # Natural transition: advance when the user has answered the question
    # ------------------------------------------------------------------
    @agent.on("user_speech_committed")
    def on_user_speech(_msg: llm.ChatMessage):
        """
        Fires each time the user finishes a speech turn.
        We record the turn and, if we've reached the threshold, schedule
        an advance on the event loop (can't await inside a sync callback).
        """
        if state.stage == InterviewStage.COMPLETE:
            return

        state.record_user_turn()
        logger.info(
            "[%s] user turn #%d  (%.1fs in stage)",
            state.stage.value,
            state._user_turns,
            state.time_in_stage(),
        )

        # Only advance once per stage (guard against duplicate calls).
        if state.can_advance():
            asyncio.ensure_future(_do_advance(agent, state))

    # ------------------------------------------------------------------
    # Time-based fallback: auto-advance SELF_INTRO after 60 seconds
    # ------------------------------------------------------------------
    async def _timeout_watchdog():
        """
        Polls every 5 seconds while in SELF_INTRO.
        If 60 seconds pass without a natural transition (e.g. the candidate
        is silent or the VAD misses their speech), force an advance so the
        interview doesn't get stuck.
        """
        while state.stage == InterviewStage.SELF_INTRO:
            await asyncio.sleep(5)
            if (
                state.stage == InterviewStage.SELF_INTRO
                and state.time_in_stage() >= INTRO_TIMEOUT_SECONDS
                and not state.can_advance()   # hasn't already triggered naturally
            ):
                logger.warning(
                    "SELF_INTRO timeout after %.1fs — forcing advance",
                    state.time_in_stage(),
                )
                await _do_advance(agent, state)
                break   # watchdog job is done once the stage advances

    asyncio.ensure_future(_timeout_watchdog())

    # Hold the coroutine open for the lifetime of the room connection.
    await asyncio.sleep(float("inf"))


# ---------------------------------------------------------------------------
# Worker bootstrap
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint)
    )
