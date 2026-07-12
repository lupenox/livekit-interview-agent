from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent.py"


class _Options(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)


class _RunContext:
    def __init__(self, userdata=None):
        self.userdata = userdata

    @classmethod
    def __class_getitem__(cls, _item):
        return cls


class _Agent:
    def __init__(self, *, instructions):
        self.instructions = instructions
        self.session = None


class _AgentSession:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.userdata = kwargs.get("userdata")
        self.started_with = None
        self.updated_agent = None
        self.__class__.instances.append(self)

    async def start(self, *, agent, room):
        self.started_with = {"agent": agent, "room": room}

    def update_agent(self, agent):
        self.updated_agent = agent


class _Factory:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def __call__(self, **kwargs):
        value = types.SimpleNamespace(factory=self.name, **kwargs)
        self.calls.append(kwargs)
        return value


class _VAD:
    calls = 0

    @classmethod
    def load(cls):
        cls.calls += 1
        return types.SimpleNamespace(factory="silero.VAD")


def _function_tool(func):
    return func


def _install_stubs():
    _AgentSession.instances = []
    _VAD.calls = 0

    deepgram_stt = _Factory("deepgram.STT")
    groq_llm = _Factory("openai.LLM")
    elevenlabs_tts = _Factory("elevenlabs.TTS")

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    agents = types.ModuleType("livekit.agents")
    agents.Agent = _Agent
    agents.AgentSession = _AgentSession
    agents.EndpointingOptions = _Options
    agents.InterruptionOptions = _Options
    agents.JobContext = object
    agents.RunContext = _RunContext
    agents.TurnHandlingOptions = _Options
    agents.WorkerOptions = _Options
    agents.function_tool = _function_tool
    agents.cli = types.SimpleNamespace(run_app=lambda _options: None)

    deepgram = types.ModuleType("livekit.plugins.deepgram")
    deepgram.STT = deepgram_stt
    elevenlabs = types.ModuleType("livekit.plugins.elevenlabs")
    elevenlabs.TTS = elevenlabs_tts
    openai = types.ModuleType("livekit.plugins.openai")
    openai.LLM = groq_llm
    silero = types.ModuleType("livekit.plugins.silero")
    silero.VAD = _VAD

    plugins = types.ModuleType("livekit.plugins")
    plugins.deepgram = deepgram
    plugins.elevenlabs = elevenlabs
    plugins.openai = openai
    plugins.silero = silero

    livekit = types.ModuleType("livekit")
    livekit.agents = agents
    livekit.plugins = plugins

    sys.modules.update(
        {
            "dotenv": dotenv,
            "livekit": livekit,
            "livekit.agents": agents,
            "livekit.plugins": plugins,
            "livekit.plugins.deepgram": deepgram,
            "livekit.plugins.elevenlabs": elevenlabs,
            "livekit.plugins.openai": openai,
            "livekit.plugins.silero": silero,
        }
    )

    return types.SimpleNamespace(
        deepgram_stt=deepgram_stt,
        groq_llm=groq_llm,
        elevenlabs_tts=elevenlabs_tts,
        session_class=_AgentSession,
        vad_class=_VAD,
    )


def _load_agent_module():
    stubs = _install_stubs()
    module_name = "agent_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, AGENT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load agent.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module, stubs


class AgentConfigurationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.agent, self.stubs = _load_agent_module()

    def test_require_env_returns_value_and_rejects_missing_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq"}, clear=True):
            self.assertEqual(self.agent._require_env("GROQ_API_KEY"), "test-groq")
            with self.assertRaisesRegex(RuntimeError, "Missing DEEPGRAM_API_KEY"):
                self.agent._require_env("DEEPGRAM_API_KEY")

    def test_stage_agents_use_distinct_instructions(self):
        context = self.agent.InterviewContext(stage_start_time=1.0)
        intro = self.agent.SelfIntroductionAgent(context)
        past = self.agent.PastExperienceAgent(context)

        self.assertIn("SELF-INTRODUCTION", intro.instructions)
        self.assertIn("PAST EXPERIENCE", past.instructions)
        self.assertIn("short introduction", intro.instructions)
        self.assertIn("Wait for complete answers", past.instructions)
        self.assertIs(intro.ctx, context)
        self.assertIs(past.ctx, context)

    async def test_tool_transition_returns_past_experience_agent_without_userdata(self):
        context = self.agent.InterviewContext(stage_start_time=1.0)
        intro = self.agent.SelfIntroductionAgent(context)

        next_agent, message = await intro.move_to_past_experience(_RunContext())

        self.assertIsInstance(next_agent, self.agent.PastExperienceAgent)
        self.assertIs(next_agent.ctx, context)
        self.assertIn("past project or role", message)

    async def test_self_intro_on_enter_resets_timer_and_greets(self):
        context = self.agent.InterviewContext(stage_start_time=1.0)
        intro = self.agent.SelfIntroductionAgent(context)
        intro.session = types.SimpleNamespace(say=AsyncMock())
        scheduled = []

        def capture_task(coro):
            scheduled.append(coro)
            coro.close()
            return object()

        with (
            patch.object(self.agent.time, "time", return_value=50.0),
            patch.object(self.agent.asyncio, "create_task", side_effect=capture_task),
        ):
            await intro.on_enter()

        self.assertEqual(context.stage_start_time, 50.0)
        self.assertEqual(len(scheduled), 1)
        intro.session.say.assert_awaited_once()
        self.assertIn("introducing yourself", intro.session.say.await_args.args[0])

    async def test_self_intro_timeout_advances_agent(self):
        context = self.agent.InterviewContext(stage_start_time=10.0)
        intro = self.agent.SelfIntroductionAgent(context)
        intro.session = types.SimpleNamespace(
            say=AsyncMock(),
            update_agent=AsyncMock(),
        )

        with (
            patch.object(self.agent.asyncio, "sleep", new=AsyncMock()),
            patch.object(self.agent.time, "time", return_value=71.0),
        ):
            await intro._timeout_watcher(60)

        intro.session.say.assert_awaited_once()
        intro.session.update_agent.assert_awaited_once()
        updated_agent = intro.session.update_agent.await_args.args[0]
        self.assertIsInstance(updated_agent, self.agent.PastExperienceAgent)

    async def test_self_intro_timeout_does_not_advance_early(self):
        context = self.agent.InterviewContext(stage_start_time=10.0)
        intro = self.agent.SelfIntroductionAgent(context)
        intro.session = types.SimpleNamespace(
            say=AsyncMock(),
            update_agent=AsyncMock(),
        )

        with (
            patch.object(self.agent.asyncio, "sleep", new=AsyncMock()),
            patch.object(self.agent.time, "time", return_value=69.0),
        ):
            await intro._timeout_watcher(60)

        intro.session.say.assert_not_awaited()
        intro.session.update_agent.assert_not_awaited()

    async def test_past_experience_timeout_closes_with_feedback(self):
        context = self.agent.InterviewContext(stage_start_time=5.0)
        past = self.agent.PastExperienceAgent(context)
        past.session = types.SimpleNamespace(say=AsyncMock())

        with (
            patch.object(self.agent.asyncio, "sleep", new=AsyncMock()),
            patch.object(self.agent.time, "time", return_value=96.0),
        ):
            await past._timeout_watcher(90)

        past.session.say.assert_awaited_once()
        spoken = past.session.say.await_args.args[0]
        self.assertIn("wraps up our mock interview", spoken)

    async def test_entrypoint_builds_expected_voice_pipeline(self):
        room = object()
        ctx = types.SimpleNamespace(room=room)
        env = {
            "GROQ_API_KEY": "groq-test-key",
            "DEEPGRAM_API_KEY": "deepgram-test-key",
            "ELEVENLABS_API_KEY": "elevenlabs-test-key",
        }

        with patch.dict(os.environ, env, clear=True):
            await self.agent.entrypoint(ctx)

        self.assertEqual(self.stubs.vad_class.calls, 1)
        self.assertEqual(
            self.stubs.deepgram_stt.calls,
            [
                {
                    "model": "nova-3",
                    "language": "en-US",
                    "api_key": "deepgram-test-key",
                }
            ],
        )
        self.assertEqual(
            self.stubs.groq_llm.calls,
            [
                {
                    "model": "llama-3.3-70b-versatile",
                    "base_url": "https://api.groq.com/openai/v1",
                    "api_key": "groq-test-key",
                }
            ],
        )
        self.assertEqual(
            self.stubs.elevenlabs_tts.calls,
            [
                {
                    "model": "eleven_turbo_v2_5",
                    "api_key": "elevenlabs-test-key",
                }
            ],
        )

        session = self.stubs.session_class.instances[-1]
        self.assertIs(session.started_with["room"], room)
        self.assertIsInstance(
            session.started_with["agent"], self.agent.SelfIntroductionAgent
        )
        self.assertIs(session.kwargs["userdata"], session.started_with["agent"].ctx)
        self.assertEqual(session.kwargs["turn_handling"]["endpointing"]["mode"], "fixed")
        self.assertEqual(session.kwargs["turn_handling"]["endpointing"]["min_delay"], 2.0)
        self.assertEqual(session.kwargs["turn_handling"]["endpointing"]["max_delay"], 6.0)
        self.assertFalse(session.kwargs["turn_handling"]["interruption"]["enabled"])
        self.assertEqual(
            session.kwargs["turn_handling"]["interruption"]["min_duration"], 1.0
        )
        self.assertFalse(
            session.kwargs["turn_handling"]["preemptive_generation"]["enabled"]
        )

    async def test_entrypoint_fails_before_provider_setup_when_key_is_missing(self):
        ctx = types.SimpleNamespace(room=object())
        env = {
            "GROQ_API_KEY": "groq-test-key",
            "DEEPGRAM_API_KEY": "deepgram-test-key",
        }

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Missing ELEVENLABS_API_KEY"):
                await self.agent.entrypoint(ctx)

        self.assertEqual(self.stubs.session_class.instances, [])


if __name__ == "__main__":
    unittest.main()
