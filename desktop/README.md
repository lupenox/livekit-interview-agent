# MockMate Desktop

Electron desktop edition of MockMate. This branch keeps the existing web/local MVP on `main` intact while building a downloadable bring-your-own-key application.

## Current milestone

The desktop shell currently:

- collects LiveKit, Groq, Deepgram, and ElevenLabs credentials locally
- validates each provider from Electron's main process
- optionally encrypts remembered credentials with Electron `safeStorage`
- exposes only a narrow preload/IPC API to the renderer
- starts the existing Python LiveKit worker and Next.js frontend in development
- passes credentials through child-process environment variables rather than command-line arguments
- loads the existing MockMate interview interface inside the Electron window
- stops the managed services when the desktop application closes

The packaged Python executable and packaged Next.js server are the next milestone. Until those sidecars are bundled, `npm start` is a development workflow and expects the repository's Python virtual environment and frontend dependencies to exist.

## Development

Prepare the existing Python and frontend projects first. Then, from the repository root:

```bash
cd desktop
npm install
npm start
```

The launcher finds Python in either:

```text
.venv/
livekit-interview-agent/.venv/
```

## Security model

- `nodeIntegration` is disabled.
- `contextIsolation` and renderer sandboxing are enabled.
- Provider calls and process management run in the Electron main process.
- The renderer receives a small allow-listed API through `contextBridge`.
- Remembered credentials are stored only when operating-system encryption is available.
- Credentials are never placed in URLs or child-process arguments.
- External navigation is denied and HTTPS links are opened in the system browser.

## Release roadmap

1. Desktop foundation and encrypted setup wizard
2. Bundle the Python agent with PyInstaller per operating system
3. Bundle the Next.js production server as an Electron resource
4. Add Windows, Linux, and macOS packaging workflows
5. Add signing, notarization, GitHub Releases, and website download links
