import { app, BrowserWindow } from 'electron';
import { spawn, type ChildProcessByStdio } from 'node:child_process';
import { access } from 'node:fs/promises';
import path from 'node:path';
import type { Readable } from 'node:stream';
import type { MockMateCredentials, ServiceEvent, StartResult } from './types';

const FRONTEND_URL = 'http://127.0.0.1:3000';
const STARTUP_TIMEOUT_MS = 45_000;

type ManagedProcess = ChildProcessByStdio<null, Readable, Readable>;

let agentProcess: ManagedProcess | null = null;
let frontendProcess: ManagedProcess | null = null;

function emit(event: ServiceEvent): void {
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send('services:event', event);
  }
}

function repoRoot(): string {
  return path.resolve(app.getAppPath(), '..');
}

async function findPython(root: string): Promise<string> {
  const windows = process.platform === 'win32';
  const candidates = [
    path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python'),
    path.join(root, 'livekit-interview-agent', '.venv', windows ? 'Scripts/python.exe' : 'bin/python'),
  ];

  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Try the next known project virtual environment.
    }
  }

  throw new Error('Python environment not found. Create .venv before starting the desktop app.');
}

function childEnvironment(credentials: MockMateCredentials): NodeJS.ProcessEnv {
  return {
    ...process.env,
    LIVEKIT_URL: credentials.livekitUrl,
    LIVEKIT_API_KEY: credentials.livekitApiKey,
    LIVEKIT_API_SECRET: credentials.livekitApiSecret,
    GROQ_API_KEY: credentials.groqApiKey,
    DEEPGRAM_API_KEY: credentials.deepgramApiKey,
    ELEVENLABS_API_KEY: credentials.elevenlabsApiKey,
    PORT: '3000',
  };
}

function wireLogs(service: ServiceEvent['service'], child: ManagedProcess): void {
  child.stdout.on('data', (chunk: Buffer) => {
    emit({ service, stream: 'stdout', message: chunk.toString() });
  });
  child.stderr.on('data', (chunk: Buffer) => {
    emit({ service, stream: 'stderr', message: chunk.toString() });
  });
  child.on('exit', (code, signal) => {
    emit({ service, stream: 'status', message: `${service} exited (${code ?? signal ?? 'unknown'}).` });
  });
}

async function waitForFrontend(): Promise<void> {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (!frontendProcess || frontendProcess.exitCode !== null) {
      throw new Error('Frontend exited during startup.');
    }
    try {
      const response = await fetch(FRONTEND_URL, { signal: AbortSignal.timeout(1_500) });
      if (response.ok) return;
    } catch {
      // Next.js is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('Frontend did not become ready within 45 seconds.');
}

export async function startServices(credentials: MockMateCredentials): Promise<StartResult> {
  if (agentProcess || frontendProcess) return { frontendUrl: FRONTEND_URL };

  if (app.isPackaged) {
    throw new Error('Packaged service resources are not included in this foundation milestone yet.');
  }

  const root = repoRoot();
  const python = await findPython(root);
  const env = childEnvironment(credentials);

  agentProcess = spawn(python, [path.join(root, 'agent.py'), 'dev'], {
    cwd: root,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  wireLogs('agent', agentProcess);

  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  frontendProcess = spawn(npmCommand, ['run', 'dev', '--', '--hostname', '127.0.0.1'], {
    cwd: path.join(root, 'frontend'),
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  wireLogs('frontend', frontendProcess);

  try {
    await waitForFrontend();
    emit({ service: 'frontend', stream: 'status', message: 'MockMate is ready.' });
    return { frontendUrl: FRONTEND_URL };
  } catch (error) {
    await stopServices();
    throw error;
  }
}

async function stopChild(child: ManagedProcess | null): Promise<void> {
  if (!child || child.exitCode !== null) return;
  child.kill();
  await Promise.race([
    new Promise<void>((resolve) => child.once('exit', () => resolve())),
    new Promise<void>((resolve) => setTimeout(resolve, 3_000)),
  ]);
}

export async function stopServices(): Promise<void> {
  const agent = agentProcess;
  const frontend = frontendProcess;
  agentProcess = null;
  frontendProcess = null;
  await Promise.all([stopChild(agent), stopChild(frontend)]);
}
