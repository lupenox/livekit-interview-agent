# LiveKit AI Mock Interview Agent

A real-time voice mock interview agent built with **LiveKit Agents**, **Silero VAD**, **Deepgram STT**, a **Groq-hosted Llama model**, and **ElevenLabs TTS**.

The agent conducts a focused two-stage interview:

1. **Self Introduction**
2. **Past Experience / Project Discussion**

A candidate joins a LiveKit room, speaks naturally, and hears the AI interviewer respond as another audio participant.

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
- Adaptive interruption handling and fixed endpointing controls
- Local console mode and LiveKit worker mode
- Clear startup validation for required provider keys
- Automated unit tests and GitHub Actions CI

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

## Setup

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
python agent.py download-files
```

## Run

For a local terminal-based test:

```bash
python agent.py console
```

To run a LiveKit worker that can be dispatched to rooms:

```bash
python agent.py start
```

After the worker starts, join a room through the LiveKit Agents Playground or a compatible frontend. The agent listens to the candidate, generates an interview response, and publishes synthesized speech back to the room.

## Interview flow

### 1. Self introduction

`SelfIntroductionAgent` welcomes the candidate and asks for a brief introduction. Its instructions keep this stage concise and prevent it from diving too deeply into project details.

The agent can call `move_to_past_experience` to switch to the next interviewer. A 60-second timeout also advances the session if the stage stalls.

### 2. Past experience

`PastExperienceAgent` asks about a project or role, including the candidate's responsibilities, challenges, lessons learned, and impact.

A 90-second fallback closes the discussion with a short, encouraging conclusion if the stage remains active.

## Turn handling

The session uses:

- Fixed endpointing with a 1–4 second delay window
- Adaptive interruption handling
- A minimum interruption duration of 0.6 seconds

These settings help the interviewer avoid cutting off the candidate while keeping the conversation responsive.

## Testing

Run the unit suite with:

```bash
python -m unittest -v tests.test_agent
```

Running the test module directly avoids platform-specific `unittest discover` path issues while still executing the complete suite.

The tests use in-process provider and LiveKit fakes, so they do not make network requests or consume API credits. They verify:

- Required API-key validation
- Stage-specific agent instructions
- Function-tool transitions
- Self-introduction and past-experience timeout behavior
- Groq, Deepgram, ElevenLabs, Silero, and turn-handling configuration
- Session startup with the expected room and initial agent

GitHub Actions also installs the real dependencies and imports `agent.py` before running the isolated tests. This catches dependency or LiveKit API incompatibilities without calling external services.

## Architecture notes

The project intentionally uses separate providers for speech recognition, reasoning, and speech synthesis instead of a single end-to-end voice model. This makes each component easier to replace, test, and tune independently.

Groq is accessed through an OpenAI-compatible interface, so the LLM provider can be changed without redesigning the rest of the voice pipeline.

## Project structure

```text
agent.py                         # Main LiveKit worker and interview agents
requirements.txt                 # Python dependencies
tests/test_agent.py              # Mock-isolated functional unit tests
.github/workflows/tests.yml      # Dependency, import, compile, and test CI
.env.example                     # Example environment configuration
livekit-interview-agent/         # Challenge-specific compatibility copy
```

## Security

Keep API keys in `.env` or another local secret store. Do not commit real credentials to the repository.
