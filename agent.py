#!/usr/bin/env python3
"""
LiveKit Multi-Agent Voice Mock Interview Worker

Architecture:
- Cascaded voice pipeline: Silero VAD -> Deepgram Nova-3 STT -> Groq Llama 3.3 70B -> ElevenLabs Turbo v2.5 TTS
- Two-stage agent handoff: SelfIntroductionAgent -> PastExperienceAgent
- Dual transition control: LLM function tools (`move_to_past_experience`, `conclude_interview`)
  backed by guarded stage timeout watchers so interviews never stall or double-transition
- Patient turn handling tuned for interview answers with natural thinking pauses
"""

import asyncio
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    EndpointingOptions,
    InterruptionOptions,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, elevenlabs, openai, silero

load_dotenv()
logger = logging.getLogger("mock-interview")
logging.basicConfig(level=logging.INFO)

STAGE_SELF_INTRO = "self_introduction"
STAGE_PAST_EXPERIENCE = "past_experience"
STAGE_COMPLETED = "completed"

INTRO_TIMEOUT = 60
PAST_TIMEOUT = 90
DEEPGRAM_MODEL = "nova-3"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
ELEVENLABS_MODEL = "eleven_turbo_v2_5"
ENDPOINTING_MIN_DELAY = 2.0
ENDPOINTING_MAX_DELAY = 6.0
MIN_INTERRUPTION_DURATION = 1.0


def _require_env(name: str) -> str:
    """Return a required API key or raise a clear startup error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to .env before starting the agent.")
    return value


async def _update_agent(session: AgentSession, next_agent: Agent) -> None:
    """Switch agents across LiveKit versions with sync or async handoff APIs."""
    handoff_result = session.update_agent(next_agent)
    if inspect.isawaitable(handoff_result):
        await handoff_result


def _extract_target_role(room: object) -> Optional[str]:
    """
    Extract optional `targetRole` from LiveKit room or remote participant metadata
    (populated by the Next.js `/api/token` route).
    """
    metadata_candidates: list[str] = []

    room_meta = getattr(room, "metadata", None)
    if isinstance(room_meta, str) and room_meta.strip():
        metadata_candidates.append(room_meta)

    remote_participants = getattr(room, "remote_participants", None)
    if isinstance(remote_participants, dict):
        for participant in remote_participants.values():
            p_meta = getattr(participant, "metadata", None)
            if isinstance(p_meta, str) and p_meta.strip():
                metadata_candidates.append(p_meta)

    for raw in metadata_candidates:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                role = (parsed.get("targetRole") or "").strip()
                if role:
                    return role
        except (ValueError, TypeError):
            continue

    return None


@dataclass
class InterviewContext:
    stage_start_time: float = field(default_factory=time.time)
    current_stage: Optional[str] = None
    target_role: Optional[str] = None
    timeout_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def cancel_timeout(self) -> None:
        """Cancel any active stage timeout task so stale timers never fire after handoff."""
        task = self.timeout_task
        self.timeout_task = None
        if task is not None and hasattr(task, "done") and not task.done():
            task.cancel()


class BaseInterviewStageAgent(Agent):
    """Base class for stage-scoped interviewer agents with guarded timeout watchers."""

    STAGE_NAME: str = ""
    BASE_INSTRUCTIONS: str = ""

    def __init__(self, ctx: InterviewContext):
        instructions = self.BASE_INSTRUCTIONS
        if ctx.target_role:
            instructions = f"{instructions} The candidate is interviewing for a {ctx.target_role} role."
        super().__init__(instructions=instructions)
        self.ctx = ctx

    def _start_stage_timer(self, timeout: int) -> None:
        self.ctx.cancel_timeout()
        self.ctx.current_stage = self.STAGE_NAME
        self.ctx.stage_start_time = time.time()
        self.ctx.timeout_task = asyncio.create_task(self._timeout_watcher(timeout))

    def _is_timer_still_valid(self, expected_start_time: float, timeout: int) -> bool:
        """
        Verify that:
        1. The stage has not transitioned since this timer was scheduled, and
        2. The full timeout duration has elapsed.
        """
        if self.ctx.current_stage not in (None, self.STAGE_NAME):
            return False
        if self.ctx.stage_start_time != expected_start_time:
            return False
        return self.ctx.stage_start_time + timeout <= time.time()

    async def _timeout_watcher(self, timeout: int) -> None:
        raise NotImplementedError


class SelfIntroductionAgent(BaseInterviewStageAgent):
    STAGE_NAME = STAGE_SELF_INTRO
    BASE_INSTRUCTIONS = (
        "You are a professional and friendly AI mock interviewer. "
        "CURRENT STAGE: SELF-INTRODUCTION. "
        "Greet the candidate warmly and ask them to introduce themselves and give a quick overview of their background. "
        "Keep responses encouraging but concise. Do not dive deep into specific experiences yet. "
        "If the candidate gives only a short introduction, ask one brief follow-up before transitioning. "
        "Only call the move_to_past_experience tool after the candidate has clearly finished their self-introduction. "
        "Never interrupt while the candidate is still speaking or collecting their thoughts."
    )

    async def on_enter(self):
        logger.info("=== SELF-INTRODUCTION stage ===")
        self._start_stage_timer(INTRO_TIMEOUT)
        await self.session.say(
            "Hello! Thank you for joining this mock interview. "
            "Could you start by introducing yourself and telling me a bit about your background?"
        )

    async def _timeout_watcher(self, timeout: int):
        expected_start = self.ctx.stage_start_time
        await asyncio.sleep(timeout)
        if self._is_timer_still_valid(expected_start, timeout):
            logger.warning("Time-based fallback triggered")
            await self.session.say("To keep us on time, let's move into your past experience.")
            await _update_agent(self.session, PastExperienceAgent(self.ctx))

    @function_tool
    async def move_to_past_experience(self, context: RunContext[InterviewContext]):
        self.ctx.cancel_timeout()
        self.ctx.current_stage = STAGE_PAST_EXPERIENCE
        next_agent = PastExperienceAgent(self.ctx)
        return next_agent, "Thank you. Now let's talk about a past project or role you're proud of."


class PastExperienceAgent(BaseInterviewStageAgent):
    STAGE_NAME = STAGE_PAST_EXPERIENCE
    BASE_INSTRUCTIONS = (
        "You are in the PAST EXPERIENCE stage. "
        "Have a natural conversation about one of the candidate's past projects or roles. "
        "Ask about their role, challenges they faced, what they learned, and the impact. "
        "Wait for complete answers before responding, especially if the candidate pauses mid-thought. "
        "Keep it conversational."
    )

    async def on_enter(self):
        logger.info("=== PAST EXPERIENCE stage ===")
        self._start_stage_timer(PAST_TIMEOUT)

    async def _timeout_watcher(self, timeout: int):
        expected_start = self.ctx.stage_start_time
        await asyncio.sleep(timeout)
        if self._is_timer_still_valid(expected_start, timeout):
            self.ctx.current_stage = STAGE_COMPLETED
            await self.session.say(
                "We've had a good discussion. Thank you for sharing your experience. "
                "That wraps up our mock interview. You did well."
            )

    @function_tool
    async def conclude_interview(self, context: RunContext[InterviewContext]):
        self.ctx.cancel_timeout()
        self.ctx.current_stage = STAGE_COMPLETED
        await self.session.say(
            "Thank you for your time. You shared some great examples. Good luck with your interviews!"
        )


async def entrypoint(ctx: JobContext):
    groq_api_key = _require_env("GROQ_API_KEY")
    deepgram_api_key = _require_env("DEEPGRAM_API_KEY")
    elevenlabs_api_key = _require_env("ELEVENLABS_API_KEY")

    target_role = _extract_target_role(ctx.room)
    interview_ctx = InterviewContext(target_role=target_role)

    session = AgentSession(
        userdata=interview_ctx,
        vad=silero.VAD.load(),
        stt=deepgram.STT(
            model=DEEPGRAM_MODEL,
            language="en-US",
            api_key=deepgram_api_key,
        ),
        llm=openai.LLM(
            model=GROQ_MODEL,
            base_url=GROQ_BASE_URL,
            api_key=groq_api_key,
        ),
        tts=elevenlabs.TTS(
            model=ELEVENLABS_MODEL,
            api_key=elevenlabs_api_key,
        ),
        turn_handling=TurnHandlingOptions(
            endpointing=EndpointingOptions(
                mode="fixed",
                min_delay=ENDPOINTING_MIN_DELAY,
                max_delay=ENDPOINTING_MAX_DELAY,
            ),
            interruption=InterruptionOptions(
                enabled=False,
                min_duration=MIN_INTERRUPTION_DURATION,
            ),
            preemptive_generation={"enabled": False},
        ),
    )

    await session.start(agent=SelfIntroductionAgent(interview_ctx), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
