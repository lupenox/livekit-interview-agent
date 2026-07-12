# MockMate Desktop

Electron desktop edition of MockMate. This branch keeps the existing web/local MVP on `main` intact while building a downloadable bring-your-own-key application.

## What is working

The desktop application:

- collects LiveKit, Groq, Deepgram, and ElevenLabs credentials locally
- validates each provider from Electron's main process
- optionally encrypts remembered credentials with Electron `safeStorage`
- exposes only a narrow preload/IPC API to the renderer
- starts and stops the LiveKit worker and Next.js frontend automatically
- passes credentials through child-process environment variables rather than command-line arguments
- loads the existing MockMate interview interface inside the Electron window
- supports both repository development and fully packaged sidecars

## Development

Prepare the existing Python and frontend projects first. Then, from the repository root:

```bash
cd desktop
npm install
npm start
```

Development mode finds Python in either:

```text
.venv/
livekit-interview-agent/.venv/
```

It runs `agent.py dev` and the frontend's Next.js development server from the source repository.

## Build a self-contained application

The packaged app contains:

```text
MockMate
├── Electron desktop shell
├── PyInstaller LiveKit worker
├── standalone Next.js production server
└── platform-matched Node.js runtime
```

Users do not need Python, Node.js, npm, or the source repository after installation.

Install the Python build dependencies once:

```bash
python -m pip install -r desktop/requirements-build.txt
```

Make sure the frontend and desktop JavaScript dependencies are installed:

```bash
cd frontend
npm install
cd ../desktop
npm install
```

Create an unpacked application for the current operating system:

```bash
npm run package
```

Create the platform installer or archive:

```bash
npm run make
```

Both commands first run `npm run build:sidecars`, which:

1. downloads the LiveKit plugin model assets
2. packages `agent.py` as `mockmate-agent` with PyInstaller
3. builds the frontend using Next.js standalone output
4. copies the current platform's Node.js executable
5. places all runtime resources in `desktop/resources/`

Generated resources, PyInstaller work files, and Electron output are ignored by Git.

## Automated packages

The **Desktop Packages** GitHub Actions workflow builds native artifacts on Linux, Windows, and macOS. It can be started manually from the Actions tab or by pushing a tag matching:

```text
desktop-v*
```

The workflow uploads unsigned build artifacts for 14 days. Public releases still need code signing and notarization to avoid operating-system trust warnings.

## Security model

- `nodeIntegration` is disabled.
- `contextIsolation` and renderer sandboxing are enabled.
- Provider calls and process management run in the Electron main process.
- The renderer receives a small allow-listed API through `contextBridge`.
- Remembered credentials are stored only when operating-system encryption is available.
- Credentials are never placed in URLs or child-process arguments.
- External navigation is denied and HTTPS links are opened in the system browser.
- Electron's `RunAsNode` fuse remains disabled; the standalone frontend uses a separate bundled Node runtime.

## Release roadmap

1. Desktop foundation and encrypted setup wizard — complete
2. Package the Python and Next.js sidecars — implemented, native validation in progress
3. Produce unsigned Windows, Linux, and macOS artifacts — workflow added
4. Add application icons and release metadata
5. Add signing, notarization, GitHub Releases, and website download links
