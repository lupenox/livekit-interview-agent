# LiveKit AI Mock Interview Agent

A real-time AI mock interview demo built with LiveKit Agents and Gemini. The agent guides a candidate through two interview stages:

1. Self Introduction
2. Past Experience / Project Discussion

The project demonstrates a simple staged interview workflow with clean transition logic and a timeout fallback so the conversation can continue even if the normal stage-completion logic is not triggered.

## Features

- LiveKit voice agent worker
- Gemini-powered interview responses
- Two-stage interview flow:
  - `SELF_INTRO`
  - `PAST_EXPERIENCE`
  - `COMPLETE`
- Smooth transition between interview stages
- Time-based fallback for stage progression
- Environment-based API key configuration

## Tech Stack

- Python 3.12
- LiveKit Agents
- LiveKit Google plugin
- LiveKit Silero plugin
- Gemini API
- python-dotenv
- PyAV

## Setup

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```env
LIVEKIT_URL=wss://your-livekit-project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
GOOGLE_API_KEY=your_google_api_key
```

Download required model files:

```bash
python agent.py download-files
```

Start the LiveKit worker:

```bash
python agent.py start
```

A successful startup should show:

```txt
registered worker
```

## Interview Flow

The agent begins in the self-introduction stage and asks the candidate to introduce themselves.

After the candidate responds, the agent transitions into the past-experience stage and asks about a project, internship, work experience, or relevant background.

If the normal transition logic does not trigger within the configured time window, the agent uses a timeout fallback to move the interview forward.

## Submission Notes

This project was built for the AI Engineer take-home challenge. It focuses on implementing the self-introduction and past-experience stages of an AI mock interview using LiveKit Agents, with clear stage switching and fallback behavior.
