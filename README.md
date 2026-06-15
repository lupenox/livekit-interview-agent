# LiveKit AI Mock Interview Agent

A real-time voice mock interview agent built with **LiveKit Agents**, **Deepgram STT**, **Gemini**, and **ElevenLabs TTS**. The agent runs a two-stage interview:

1. Self Introduction
2. Past Experience / Project Discussion

It uses a free-tier-friendly voice pipeline so a candidate can speak in a LiveKit room and hear the agent respond as an audio participant.

## What changed

The previous implementation used Google Cloud Speech-to-Text and Google Cloud Text-to-Speech, which require Google Cloud billing credentials. This version keeps Gemini for interview reasoning but moves speech services to providers with accessible free tiers:

- `ctx.connect()` joins the LiveKit room and subscribes to room media.
- `silero.VAD.load()` detects when the candidate starts and stops speaking.
- `deepgram.STT(model="nova-3")` converts candidate microphone audio to text.
- `google.LLM(model="gemini-2.5-flash")` generates interview responses.
- `elevenlabs.TTS(model="eleven_turbo_v2_5")` turns responses into speech and publishes an agent audio track back to the room.

The audio path is now **Deepgram STT → Gemini LLM → ElevenLabs TTS**.

## Required API keys

Create `.env` or `.env.local` in the repository root with:

```env
LIVEKIT_URL=wss://your-livekit-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
GOOGLE_API_KEY=your_google_ai_studio_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

### Where to get free-tier-friendly keys

- **LiveKit**: Create a free LiveKit Cloud project at <https://cloud.livekit.io>, then copy the WebSocket URL plus API key/secret from the project settings.
- **Google Gemini**: Create a Gemini API key in Google AI Studio at <https://aistudio.google.com/app/apikey>. This is used only for the LLM.
- **Deepgram**: Sign up at <https://console.deepgram.com/signup>, then create/copy an API key from the Deepgram console. This is used for Speech-to-Text.
- **ElevenLabs**: Sign up at <https://elevenlabs.io/sign-up>, then create/copy an API key from your ElevenLabs profile or developer/API key settings. This is used for Text-to-Speech.

> Free tiers and quotas can change. Check each provider dashboard for your current monthly credits/limits before running long sessions.

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies from the repository root:

```bash
pip install -r requirements.txt
```

Download LiveKit plugin model files, including Silero VAD assets:

```bash
python agent.py download-files
```

## Run

For a local terminal test:

```bash
python agent.py console
```

For a LiveKit worker that can be dispatched to rooms:

```bash
python agent.py start
```

When the worker starts successfully, join a room from the LiveKit Agents Playground or your frontend. The agent joins as a participant, listens to the candidate microphone through Deepgram STT, uses Gemini to generate the interviewer response, and speaks through ElevenLabs TTS.

## Interview flow

- The session starts in `SELF_INTRO` and asks the candidate to introduce themself.
- After the first final user transcript, the state machine advances to `PAST_EXPERIENCE` and asks about a project or past role.
- After the next final user transcript, the state machine advances to `COMPLETE` and closes with a short thank-you.
- If no final transcript is received during the self-introduction stage within 60 seconds, a watchdog advances to the past-experience stage automatically.

## Debugging

The agent validates required environment variables at startup and logs missing keys before failing fast. It also logs room connection, session start, final user transcripts, stage transitions, timeout fallback, and LiveKit session errors.

## Project files

```text
agent.py                            # Root runnable LiveKit agent
requirements.txt                    # Python dependencies
.env.example                        # Environment variable template
livekit-interview-agent/agent.py     # Compatibility copy of the agent
livekit-interview-agent/README.md    # Challenge-specific README
livekit-interview-agent/.env.example # Compatibility env template
```
