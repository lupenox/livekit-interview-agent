# LiveKit AI Mock Interview Agent

A real-time voice mock interview agent built with **LiveKit Agents**, **Silero VAD**, **Deepgram STT**, a **Groq-hosted Llama model**, **ElevenLabs TTS**, and an optional **Next.js web frontend**.

The agent conducts a focused two-stage interview:

1. **Self Introduction**
2. **Past Experience / Project Discussion**

A candidate joins a LiveKit room, speaks naturally, and hears the AI interviewer respond as another audio participant.

## Voice pipeline

```text
Candidate microphone
        ↓
Next.js frontend or console
        ↓
LiveKit room
        ↓
Silero VAD
        ↓
Deepgram Nova-3 STT
        ↓
Groq-hosted Llama 3.3 70B
(OpenAI-compatible API)
        ↓
ElevenLabs Turbo v2.5 TTS
        ↓
LiveKit agent audio track
```

The LLM is configured through LiveKit's `openai.LLM` adapter using Groq's OpenAI-compatible endpoint. Groq replaced Gemini in the current implementation because Gemini's free-request limits made repeated development and testing less practical.

## Features

- Real-time speech-to-speech interview experience
- Two stage-specific interviewer agents
- Function-tool transition from self-introduction to past experience
- Silero voice activity detection for speech boundaries
- Deepgram `nova-3` speech recognition
- Groq-hosted `llama-3.3-70b-versatile` interview reasoning
- ElevenLabs `eleven_turbo_v2_5` speech synthesis
- Time-based fallbacks to keep the interview moving
- Patient fixed endpointing to reduce mid-answer cutoffs
- Interruption handling disabled for calmer mock-interview flow
- Local console mode and LiveKit worker mode
- Next.js interview setup and browser voice-room experience
- Short-lived LiveKit token generation through a server-side route
- In-interview API budget monitor with low-credit warnings
- Clear startup validation for required provider keys
- Automated Python and frontend CI checks

## Required API keys

Create a `.env` file in the repository root:

```env
LIVEKIT_URL=wss://your-livekit-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

You can obtain credentials from:

- **LiveKit Cloud:** <https://cloud.livekit.io>
- **GroqCloud:** <https://console.groq.com/keys>
- **Deepgram:** <https://console.deepgram.com/signup>
- **ElevenLabs:** <https://elevenlabs.io/sign-up>

> Free tiers, model availability, and usage limits can change. Check each provider dashboard before running long sessions.

## Python agent setup

Clone the repository and enter the project directory:

```bash
git clone https://github.com/lupenox/livekit-interview-agent.git
cd livekit-interview-agent
```

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Download LiveKit plugin model files, including the Silero VAD assets:

```bash
python -m livekit.agents download-files
```

## Run the agent

For a local terminal-based test:

```bash
python agent.py console
```

To run a development worker that the browser frontend can dispatch into rooms:

```bash
python agent.py dev
```

To run the worker in production mode:

```bash
python agent.py start
```

## Run the Next.js frontend

The `frontend/` directory contains a separate Next.js application. Next.js renders the React interface and provides small server-side endpoints for LiveKit room tokens and provider usage data; the Python process remains the interview agent.

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Add the LiveKit and provider credentials to `frontend/.env.local`:

```env
LIVEKIT_URL=wss://your-livekit-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

ELEVENLABS_API_KEY=your_elevenlabs_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
GROQ_API_KEY=your_groq_api_key
```

Optional Deepgram billing settings:

```env
DEEPGRAM_PROJECT_ID=
DEEPGRAM_LOW_BALANCE=5
DEEPGRAM_CRITICAL_BALANCE=1
```

Open `http://localhost:3000`, enter a name and target role, and begin the interview. Keep `python agent.py dev` running in the other terminal.

## API budget monitor

During an interview, the frontend displays an **API budget** menu beside the timer. The browser requests sanitized usage information from the server-side `/api/credits` route every 60 seconds. Provider API keys stay on the server and are never returned to the browser.

The monitor uses these states:

- **OK:** usage is healthy
- **Low:** 25% or less remains
- **Critical:** 10% or less remains
- **Unavailable:** the provider does not expose the requested data or the key lacks billing permission

Provider behavior:

- **ElevenLabs** reports exact voice characters used and remaining in the current billing period.
- **Deepgram** reports the selected project's balance when the API key has project-billing permission. A transcription-capable key can still receive `403 Forbidden` from the billing endpoint; the interview remains functional and the widget explains the missing permission.
- **Groq** does not expose a traditional account-credit balance through the API. The widget uses rate-limit response headers when available. Some authenticated endpoints omit those headers, in which case the widget directs the user to the Groq console for exact limits.

Failures are isolated by provider. An unavailable balance never blocks the interview or prevents the other providers from reporting usage.

## Interview flow

### 1. Self introduction

`SelfIntroductionAgent` welcomes the candidate and asks for a brief introduction. Its instructions keep this stage concise, avoid diving too deeply into project details, and ask one short follow-up if the candidate gives only a very brief introduction.

The agent can call `move_to_past_experience` to switch to the next interviewer. A 60-second timeout also advances the session if the stage stalls.

### 2. Past experience

`PastExperienceAgent` asks about a project or role, including the candidate's responsibilities, challenges, lessons learned, and impact.

A 90-second fallback closes the discussion with a short, encouraging conclusion if the stage remains active.

## Turn handling

The session uses:

- Fixed endpointing with a 2–6 second delay window
- Disabled preemptive generation, so the agent waits for turn completion before responding
- Disabled interruption handling during the agent's speech, which makes console testing less likely to feel like the interviewer is cutting off the candidate

These settings trade a little responsiveness for a calmer mock-interview experience and better tolerance for natural pauses.

## Testing

Run the Python unit suite with:

```bash
python -m unittest -v tests.test_agent
```

Run the frontend checks with:

```bash
cd frontend
npm install
npm run lint
npm run build
```

The Python tests use in-process provider and LiveKit fakes, so they do not make network requests or consume API credits. They verify:

- Required API-key validation
- Stage-specific agent instructions
- Function-tool transitions
- Self-introduction and past-experience timeout behavior
- Groq, Deepgram, ElevenLabs, Silero, and turn-handling configuration
- Session startup with the expected room and initial agent

GitHub Actions installs the real Python and JavaScript dependencies, imports and compiles the agent, lints the frontend, and produces a production Next.js build.

## Architecture notes

The project intentionally uses separate providers for speech recognition, reasoning, and speech synthesis instead of a single end-to-end voice model. This makes each component easier to replace, test, and tune independently.

Groq is accessed through an OpenAI-compatible interface, so the LLM provider can be changed without redesigning the rest of the voice pipeline.

Next.js is not an ORM. It is the full-stack React web framework used for the browser interface, LiveKit token endpoint, and API-budget endpoint. A database and ORM such as Prisma or Drizzle can be added later for accounts, saved sessions, transcripts, and scoring history.

## Project structure

```text
agent.py                              # Main LiveKit worker and interview agents
requirements.txt                      # Python dependencies
tests/test_agent.py                   # Mock-isolated functional unit tests
frontend/                             # Next.js browser experience
frontend/app/api/token/route.ts       # Short-lived LiveKit participant tokens
frontend/app/api/credits/route.ts     # Sanitized provider usage aggregation
frontend/components/credits-health.tsx # In-interview API budget widget
.github/workflows/tests.yml           # Python dependency, import, compile, and test CI
.github/workflows/frontend.yml        # Frontend lint and production-build CI
.env.example                          # Python agent environment template
livekit-interview-agent/              # Challenge-specific compatibility copy
```

## Security

Keep API keys in `.env`, `frontend/.env.local`, or another local secret store. Do not commit real credentials. The browser receives only sanitized usage totals, never provider keys or raw account data. The frontend token and credit endpoints should gain authentication and rate limiting before a public production deployment.
