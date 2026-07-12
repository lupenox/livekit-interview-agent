# MockMate frontend

Next.js frontend for the LiveKit AI mock interview agent.

## What Next.js does here

Next.js renders the React interface and provides the small server-side `/api/token` route that creates short-lived LiveKit participant tokens. It does not replace the Python interview agent and it is not an ORM.

## Setup

From the repository root:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Fill `.env.local` with the same LiveKit and provider credentials used by the Python agent:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
ELEVENLABS_API_KEY=your_elevenlabs_api_key
DEEPGRAM_API_KEY=your_deepgram_api_key
GROQ_API_KEY=your_groq_api_key
```

All provider credentials are used only by Next.js server routes. Never prefix these secret variables with `NEXT_PUBLIC_`.

Keep the Python worker running in a separate terminal from the repository root:

```bash
source livekit-interview-agent/.venv/bin/activate
python agent.py dev
```

Then open `http://localhost:3000` and begin an interview.

## API budget monitor

The interview header includes an API budget menu that refreshes once per minute through the server-side `/api/credits` endpoint. It displays:

- ElevenLabs characters remaining in the current subscription period
- Deepgram project balance
- Groq daily-request and per-minute token headroom when Groq returns rate-limit headers

The indicator turns amber when percentage-based capacity drops below 25% and red below 10%. Deepgram uses configurable amount thresholds:

```env
DEEPGRAM_LOW_BALANCE=5
DEEPGRAM_CRITICAL_BALANCE=1
```

Set `DEEPGRAM_PROJECT_ID` when the API key has access to multiple projects and the first returned project is not the one used by the agent.

## Validation

```bash
npm run lint
npm run build
```

## Architecture

```text
Browser / Next.js UI
        ↓
Next.js token + credits endpoints
        ↓
Temporary LiveKit room
        ↓
Python LiveKit interview agent
        ↓
Deepgram → Groq → ElevenLabs
```

## Production note

The token route is suitable for local development and portfolio demos. Add authentication and rate limiting before exposing it as a public service. The credits route does not expose secret keys, but it does expose account usage information and should also be protected for a public deployment.
