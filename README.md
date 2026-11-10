# LiveKit AI Mock Interview Agent

A real-time voice mock interview agent built with **LiveKit Agents**, **Silero VAD**, **Deepgram Nova-3 STT**, **Groq-hosted Llama 3.3 70B**, **ElevenLabs Turbo v2.5 TTS**, and a **Next.js web frontend**.

The agent conducts a structured two-stage behavioral/technical interview:

1. **Self Introduction** (`SelfIntroductionAgent`)
2. **Past Experience / Project Discussion** (`PastExperienceAgent`)

A candidate joins a LiveKit WebRTC room (via the browser UI or local terminal console), speaks naturally, and converses with the AI interviewer in real time.

---

## Voice Pipeline

```text
Candidate Microphone
        ↓
Next.js Frontend (WebRTC) or Local Console
        ↓
LiveKit Room (Audio + Participant Metadata)
        ↓
Silero VAD (Speech Boundary Detection)
        ↓
Deepgram Nova-3 STT (Streaming Speech-to-Text)
        ↓
Groq Llama 3.3 70B (Stage-Scoped Agent + Function Tools)
        ↓
ElevenLabs Turbo v2.5 TTS (Low-Latency Voice Synthesis)
        ↓
LiveKit Agent Audio Track
```

---

## Key Features

- **Two-Stage Multi-Agent Architecture**: `SelfIntroductionAgent` and `PastExperienceAgent` inherit from `BaseInterviewStageAgent`, keeping stage instructions, tools, and timers strictly scoped.
- **Role-Aware Prompting**: The Next.js token endpoint embeds the candidate's `targetRole` in LiveKit participant metadata, which the Python worker reads on room entry to tailor interview prompts.
- **Dual Transition Control (Function Tools + Guarded Timeouts)**:
  - Primary transition: The LLM invokes `@function_tool` handoffs (`move_to_past_experience`, `conclude_interview`) when the candidate finishes answering.
  - Fallback transition: Guarded stage timers (`60s` for self-intro, `90s` for past experience) advance or wrap up the session if a stage stalls, while automatically cancelling and invalidating prior timers on handoff so stale timers never fire mid-stage.
- **Patient Turn Handling**: Configured with a `2.0s–6.0s` fixed endpointing window, disabled interruptions, and disabled preemptive generation so candidates can pause and think without being cut off.
- **Server-Side API Budget Monitor**: `/api/credits` aggregates live quota health from ElevenLabs, Deepgram, and Groq without exposing provider keys to the browser.

---

## Project Structure

```text
livekit-interview-agent/
├── agent.py                              # Python LiveKit worker & stage agents
├── requirements.txt                      # Python dependencies
├── tests/
│   └── test_agent.py                     # Mock-isolated unit & async test suite
├── frontend/                             # Next.js 16 + React 19 browser application
│   ├── app/
│   │   ├── page.tsx                      # Setup screen (candidate name + target role)
│   │   └── api/
│   │       ├── token/route.ts            # Mints short-lived LiveKit JWT with targetRole metadata
│   │       └── credits/route.ts          # Server-side provider quota/rate-limit health check
│   ├── components/
│   │   ├── interview-room.tsx            # LiveKit WebRTC voice room + audio visualizer
│   │   └── credits-health.tsx            # In-interview API budget status popover
│   └── lib/
│       └── types.ts                      # Shared TypeScript interfaces
└── .github/workflows/
    ├── tests.yml                         # Python dependency, import, compile, and unit test CI
    └── frontend.yml                      # Next.js ESLint and production build CI
```

---

## Quick Start

### 1. Required API Keys (`.env`)

Create a `.env` file in the repository root:

```env
LIVEKIT_URL=wss://your-livekit-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

### 2. Run the Python Voice Agent

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m livekit.agents download-files

# Terminal-only console mode:
python agent.py console

# Development worker mode (for use with the Next.js frontend):
python agent.py dev
```

### 3. Run the Next.js Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env.local   # Populate with the same LiveKit & provider keys
npm install
npm run dev
```

Open `http://localhost:3000`, enter your name and target role, and click **Begin interview**.

---

## Testing

Run the Python unit tests (uses in-process LiveKit/provider stubs—no network calls or API keys needed):

```bash
python -m unittest -v tests.test_agent
```

Run the frontend linter and production build:

```bash
cd frontend
npm run lint
npm run build
```

---

## Architecture & Interview Defense Guide

### 1. Why a Cascaded Pipeline (VAD → STT → LLM → TTS) Instead of End-to-End Speech-to-Speech?
- **Modularity & Cost Control**: Separating Silero VAD, Deepgram Nova-3 STT, Groq Llama 3.3 70B, and ElevenLabs Turbo v2.5 lets us pick the best-in-class provider for each step at a fraction of the per-minute cost of monolithic speech-to-speech APIs (like OpenAI Realtime API).
- **Deterministic Tool & State Control**: In a mock interview, we need strict stage transitions (`SelfIntroductionAgent` → `PastExperienceAgent`) and predictable turn-taking. Using Groq via LiveKit's `openai.LLM` plugin gives us fast token generation (~300+ tok/s) and reliable `@function_tool` execution, while `GROQ_MODEL` can be swapped via environment variable without code edits.

### 2. Why Two Distinct `Agent` Classes Instead of One Giant System Prompt?
- **Smaller Context & Sharper Adherence**: A single mega-prompt that tells an LLM how to conduct an introduction, when to transition, how to probe past projects, and when to conclude often causes the model to jump ahead (asking deep project questions during the intro).
- **Stage Isolation**: By splitting `SelfIntroductionAgent` and `PastExperienceAgent` (both subclassing `BaseInterviewStageAgent`), `SelfIntroductionAgent` only has access to the `move_to_past_experience` tool, and `PastExperienceAgent` only has access to `conclude_interview`. Handing off via `return next_agent, transition_message` swaps both the system instructions and the available toolset atomically.

### 3. How Do You Prevent Race Conditions Between LLM Function Tools and Stage Timeouts?
- **The Problem**: Each stage spawns an `asyncio.create_task(self._timeout_watcher(timeout))` on entry (`60s` for intro, `90s` for past experience) so the interview never gets stuck if the LLM fails to call the transition tool. However, if the candidate finishes their intro in 15 seconds via `move_to_past_experience`, an uncancelled 60-second intro timer could wake up 45 seconds later—right in the middle of the `PastExperienceAgent` discussion—and trigger a duplicate transition.
- **Two-Layer Defense in `BaseInterviewStageAgent`**:
  1. **Explicit Task Cancellation**: `InterviewContext.cancel_timeout()` cancels the active `asyncio.Task` whenever a new stage starts (`_start_stage_timer`) or a tool transition occurs (`move_to_past_experience`, `conclude_interview`).
  2. **State & Timestamp Verification (`_is_timer_still_valid`)**: Before sleeping, `_timeout_watcher` snapshots `expected_start = self.ctx.stage_start_time`. Upon waking, it verifies that `self.ctx.current_stage` still matches `self.STAGE_NAME`, `self.ctx.stage_start_time == expected_start`, and the full duration has elapsed.

### 4. Why Are Interruptions and Preemptive Generation Disabled?
- In casual voice chatbots, aggressive endpointing (~0.5s) feels snappy. In a **mock interview**, candidates frequently pause for 2–4 seconds to structure a STAR-method answer.
- Setting `EndpointingOptions(mode="fixed", min_delay=2.0, max_delay=6.0)`, `InterruptionOptions(enabled=False)`, and `preemptive_generation={"enabled": False}` prevents the interviewer from talking over a thinking candidate or generating speculative replies on half-finished thoughts.

### 5. How Does the Frontend Communicate `targetRole` and Monitor API Credits Securely?
- **Role Context via JWT Metadata**: When the user submits the setup form, `POST /api/token` mints a short-lived (20-minute) LiveKit `AccessToken` with `metadata: JSON.stringify({ targetRole })`. When the Python worker joins the room, `_extract_target_role(ctx.room)` reads the participant metadata and injects the target role into `BaseInterviewStageAgent` instructions.
- **Fault-Isolated Credit Checks**: `GET /api/credits` queries ElevenLabs, Deepgram, and Groq in parallel on the server (`Promise.all` wrapped in `safeProvider`). Provider API keys never leave the server, and a `403 Forbidden` (e.g., a Deepgram key scoped only for transcription, not billing) degrades gracefully to `"unavailable"` without blocking the interview or the other providers.
