#!/usr/bin/env python3
"""
Clean LiveKit Multi-Agent Mock Interview - Ready for Submission

This version includes:
- Self-Introduction and Past-Experience stages
- Smooth multi-agent transitions using function tools
- Time-based fallback mechanism
- Proper turn handling to reduce cutting off
"""

import asyncio
import enum
import logging
import os
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from livekit.agents import (
    Agent, AgentSession, JobContext, RunContext, function_tool,
    TurnHandlingOptions, EndpointingOptions, InterruptionOptions, cli, WorkerOptions
)
from livekit.plugins import deepgram, elevenlabs, openai, silero

load_dotenv()
logger = logging.getLogger("mock-interview")
logging.basicConfig(level=logging.INFO)


INTRO_TIMEOUT = 60
PAST_TIMEOUT = 90


@dataclass
class InterviewContext:
    stage_start_time: float = field(default_factory=time.time)


class SelfIntroductionAgent(Agent):
    def __init__(self, ctx: InterviewContext):
        super().__init__(
            instructions=(
                "You are a professional and friendly AI mock interviewer. "
                "CURRENT STAGE: SELF-INTRODUCTION. "
                "Greet the candidate warmly and ask them to introduce themselves and give a quick overview of their background. "
                "Keep responses encouraging but concise. Do not dive deep into specific experiences yet. "
                "When you have enough basic information, call the move_to_past_experience tool to transition."
            )
        )
        self.ctx = ctx

    async def on_enter(self):
        logger.info("=== SELF-INTRODUCTION stage ===")
        self.ctx.stage_start_time = time.time()
        asyncio.create_task(self._timeout_watcher(INTRO_TIMEOUT))
        await self.session.say(
            "Hello! Thank you for joining this mock interview. "
            "Could you start by introducing yourself and telling me a bit about your background?"
        )

    async def _timeout_watcher(self, timeout: int):
        await asyncio.sleep(timeout)
        if self.ctx.stage_start_time + timeout <= time.time():
            logger.warning("Time-based fallback triggered")
            await self.session.say("To keep us on time, let's move into your past experience.")
            next_agent = PastExperienceAgent(self.ctx)
            await self.session.update_agent(next_agent)

    @function_tool
    async def move_to_past_experience(self, context: RunContext[InterviewContext]):
        next_agent = PastExperienceAgent(context.userdata)
        return next_agent, "Thank you. Now let's talk about a past project or role you're proud of."


class PastExperienceAgent(Agent):
    def __init__(self, ctx: InterviewContext):
        super().__init__(
            instructions=(
                "You are in the PAST EXPERIENCE stage. "
                "Have a natural conversation about one of the candidate's past projects or roles. "
                "Ask about their role, challenges they faced, what they learned, and the impact. "
                "Keep it conversational."
            )
        )
        self.ctx = ctx

    async def on_enter(self):
        logger.info("=== PAST EXPERIENCE stage ===")
        self.ctx.stage_start_time = time.time()
        asyncio.create_task(self._timeout_watcher(PAST_TIMEOUT))

    async def _timeout_watcher(self, timeout: int):
        await asyncio.sleep(timeout)
        if self.ctx.stage_start_time + timeout <= time.time():
            await self.session.say(
                "We've had a good discussion. Thank you for sharing your experience. "
                "That wraps up our mock interview. You did well."
            )

    @function_tool
    async def conclude_interview(self, context: RunContext[InterviewContext]):
        await self.session.say(
            "Thank you for your time. You shared some great examples. Good luck with your interviews!"
        )


async def entrypoint(ctx: JobContext):
    interview_ctx = InterviewContext()

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=openai.LLM(
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        ),
        tts=elevenlabs.TTS(model="eleven_turbo_v2_5"),
        turn_handling=TurnHandlingOptions(
            endpointing=EndpointingOptions(mode="fixed", min_delay=1.0, max_delay=4.0),
            interruption=InterruptionOptions(mode="adaptive", min_duration=0.6),
        ),
    )

    await session.start(agent=SelfIntroductionAgent(interview_ctx), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
