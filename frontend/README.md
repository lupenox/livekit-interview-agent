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

Fill `.env.local` with the same LiveKit project credentials used by the Python agent:

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
```

Keep the Python worker running in a separate terminal from the repository root:

```bash
source livekit-interview-agent/.venv/bin/activate
python agent.py dev
```

Then open `http://localhost:3000` and begin an interview.

## Validation

```bash
npm run lint
npm run build
```

## Architecture

```text
Browser / Next.js UI
        ↓
Next.js token endpoint
        ↓
Temporary LiveKit room
        ↓
Python LiveKit interview agent
        ↓
Deepgram → Groq → ElevenLabs
```

## Production note

The token route is suitable for local development and portfolio demos. Add authentication and rate limiting before exposing it as a public service.
