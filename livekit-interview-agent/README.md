# AI Mock Interview Agent (LiveKit + Gemini)

A voice-based mock interview agent built with [LiveKit Agents](https://docs.livekit.io/agents/) and Google Gemini. The agent guides a candidate through two interview stages using a clean state machine.

## Interview Flow

| Stage | What happens |
|---|---|
| **SELF_INTRO** | Agent asks the candidate to introduce themselves. Advances after the first answer, or after 60 seconds (fallback). |
| **PAST_EXPERIENCE** | Agent asks about a past project or role. Advances after the first answer. |
| **COMPLETE** | Agent thanks the candidate and the session ends. |

---

## Prerequisites

- Python 3.10 or newer
- A [LiveKit Cloud](https://cloud.livekit.io) account (free tier works)
- A [Google AI Studio API key](https://aistudio.google.com/app/apikey) (free tier works)

---

## Setup on Replit

### 1. Add your secrets

In the Replit sidebar, go to **Secrets** and add the following four keys:

| Secret key | Where to find the value |
|---|---|
| `LIVEKIT_URL` | LiveKit Cloud → your project → Settings → **WebSocket URL** (starts with `wss://`) |
| `LIVEKIT_API_KEY` | LiveKit Cloud → your project → Settings → **API Keys** |
| `LIVEKIT_API_SECRET` | Same page as `LIVEKIT_API_KEY` |
| `GOOGLE_API_KEY` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |

> If you prefer a local `.env` file instead, copy `.env.example` to `.env` and fill in the values. **Do not commit `.env` to version control.**

### 2. Install dependencies

Open the Replit Shell and run:

```bash
cd livekit-interview-agent
pip install -r requirements.txt
```

### 3. Download the Silero VAD model (first run only)

```bash
python agent.py download-files
```

### 4. Start the agent worker

```bash
python agent.py start
```

The agent worker connects to LiveKit and waits for a room to be dispatched. You should see:

```
INFO     livekit-agents  worker started
```

### 5. Join a room to test

Open the [LiveKit Agents Playground](https://agents-playground.livekit.io/) and connect to the same LiveKit project. The agent will join automatically and start the interview.

---

## Project Structure

```
livekit-interview-agent/
├── agent.py          # Main agent — state machine + voice pipeline
├── requirements.txt  # Python dependencies
├── .env.example      # Template for environment variables
└── README.md         # This file
```

---

## How the State Machine Works

The `InterviewStateMachine` class in `agent.py` tracks:

- **Current stage** (`SELF_INTRO` → `PAST_EXPERIENCE` → `COMPLETE`)
- **Time in stage** — used by the 60-second timeout watchdog
- **User turns in stage** — advances after the candidate gives their first answer

Two transition paths:

1. **Natural** — `user_speech_committed` event fires → turn counter increments → threshold met → `_do_advance()` called.
2. **Fallback** — `_timeout_watchdog()` coroutine polls every 5 seconds → if 60 s pass in `SELF_INTRO` without a natural transition, calls `_do_advance()`.

Each transition swaps the LLM's system prompt so it stays in-role for the new stage and speaks the stage's opening question via `agent.say()`.

---

## Customisation

| What to change | Where |
|---|---|
| Interview questions | `STAGE_OPENINGS` dict in `agent.py` |
| LLM behaviour per stage | `STAGE_PROMPTS` dict in `agent.py` |
| Add more stages | Extend `InterviewStage` enum and `InterviewStateMachine.advance()` |
| Change timeout | `INTRO_TIMEOUT_SECONDS` constant |
| Change LLM / voice | `VoicePipelineAgent(...)` constructor arguments |
