# LiveKit AI Mock Interview Agent

This directory contains the deployable LiveKit starter-project version of the two-stage voice mock interview agent.

The agent combines:

- **LiveKit Agents** for real-time room orchestration
- **Silero VAD** for speech-boundary detection
- **Deepgram Nova-3** for speech-to-text
- **Groq-hosted Llama 3.3 70B** for interview reasoning
- **ElevenLabs Turbo v2.5** for text-to-speech

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
(OpenAI-compatible endpoint)
        ↓
ElevenLabs Turbo v2.5 TTS
        ↓
LiveKit agent audio track
```

The Groq model is connected through LiveKit's `openai.LLM` adapter because Groq exposes an OpenAI-compatible API.

## Interview flow

The state machine begins in `SELF_INTRO`, where the agent asks the candidate to introduce themself.

After the first completed candidate turn and at least eight seconds in the stage, the agent advances to `PAST_EXPERIENCE`. It then asks one concise follow-up question at a time about the candidate's role, challenges, lessons learned, and project impact.

```text
SELF_INTRO → PAST_EXPERIENCE
```

The past-experience stage intentionally does not auto-complete after a fixed number of turns, allowing a more natural project discussion.

## Required environment variables

Copy `.env.example` to `.env.local` and provide:

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

> Free tiers, quotas, and model availability can change. Check each provider dashboard before running long sessions.

## Development setup

This subproject uses `uv` and Python 3.10–3.14.

```bash
uv sync
```

Download the required LiveKit plugin assets:

```bash
uv run python src/agent.py download-files
```

## Run

Terminal voice session:

```bash
uv run python src/agent.py console
```

Development worker:

```bash
uv run python src/agent.py dev
```

Production worker:

```bash
uv run python src/agent.py start
```

## Tests and linting

Run the test suite:

```bash
uv run pytest
```

Run Ruff checks:

```bash
uv run ruff check .
```

## Project structure

```text
src/agent.py       # Interview state machine and LiveKit worker
pyproject.toml     # Runtime and development dependencies
.env.example       # Required environment-variable template
Dockerfile         # Container deployment configuration
tests/             # Test and evaluation files
```

## Architecture notes

Speech recognition, reasoning, and speech synthesis use separate providers. This makes each stage independently replaceable and keeps the voice pipeline modular.

Groq is accessed through an OpenAI-compatible adapter, so the LLM provider can be changed without redesigning the Deepgram, ElevenLabs, or LiveKit integrations.

## Security

Keep real API credentials in `.env.local` or another local secret store. Never commit active credentials to the repository.
