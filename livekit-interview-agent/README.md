# LiveKit AI Mock Interview Agent — Compatibility Copy

This directory contains the challenge-specific compatibility implementation of the real-time voice mock interview agent.

The agent uses **LiveKit Agents**, **Silero VAD**, **Deepgram STT**, a **Groq-hosted Llama model**, and **ElevenLabs TTS** to conduct a two-stage spoken interview:

1. **Self Introduction**
2. **Past Experience / Project Discussion**

The repository-root implementation is the primary version. This copy preserves the original challenge-oriented structure while using the same current provider stack.

## Voice pipeline

```text
Candidate microphone
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

Groq is connected through LiveKit's `openai.LLM` adapter using its OpenAI-compatible endpoint. It replaced Gemini because Gemini's free-request limits made repeated development and testing less practical.

## Features

- Real-time voice interview inside a LiveKit room
- Stage-aware interviewer prompts
- Explicit interview state machine
- Silero voice activity detection
- Deepgram `nova-3` speech recognition
- Groq-hosted `llama-3.3-70b-versatile` reasoning
- ElevenLabs `eleven_turbo_v2_5` speech synthesis
- Automatic stage transitions based on turns and elapsed time
- A 60-second no-response fallback during self-introduction
- Startup validation for required environment variables
- Logging for transcripts, transitions, room connection, and session errors

## Required API keys

Create `.env` or `.env.local` in this directory:

```env
LIVEKIT_URL=wss://your-livekit-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
GROQ_API_KEY=your_groq_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

Credential dashboards:

- **LiveKit Cloud:** <https://cloud.livekit.io>
- **GroqCloud:** <https://console.groq.com/keys>
- **Deepgram:** <https://console.deepgram.com/signup>
- **ElevenLabs:** <https://elevenlabs.io/sign-up>

> Free tiers, model availability, and quotas can change. Check each provider dashboard before running long sessions.

## Setup

From this directory, create and activate a virtual environment:

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

Download the LiveKit plugin assets, including Silero VAD files:

```bash
python agent.py download-files
```

## Run

Local terminal test:

```bash
python agent.py console
```

LiveKit worker mode:

```bash
python agent.py start
```

After the worker starts, join a room through the LiveKit Agents Playground or a compatible frontend.

## Interview flow

The agent begins in `SELF_INTRO`, welcomes the candidate, and asks for a brief introduction.

Final candidate transcripts are counted as interview turns. After at least three turns and 25 seconds in a stage, the state machine can advance:

```text
SELF_INTRO → PAST_EXPERIENCE → COMPLETE
```

If the candidate provides no final transcript within 60 seconds during self-introduction, the watchdog advances the interview to the past-experience stage.

The past-experience stage asks about the candidate's role, challenges, lessons learned, and project impact before closing the interview.

## Architecture notes

Speech recognition, reasoning, and speech synthesis use separate providers so each component can be replaced, tested, or tuned independently.

Groq's OpenAI-compatible endpoint also makes it possible to change the hosted model or provider without redesigning the rest of the LiveKit voice pipeline.

## Security

Keep real API credentials in `.env`, `.env.local`, or another local secret store. Never commit active keys to the repository.
