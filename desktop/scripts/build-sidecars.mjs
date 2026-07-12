import { access, chmod, copyFile, cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(scriptDirectory, '..');
const repositoryRoot = path.resolve(desktopRoot, '..');
const frontendRoot = path.join(repositoryRoot, 'frontend');
const resourcesRoot = path.join(desktopRoot, 'resources');
const buildRoot = path.join(desktopRoot, '.build');
const agentResources = path.join(resourcesRoot, 'agent');
const frontendResources = path.join(resourcesRoot, 'frontend');
const nodeResources = path.join(resourcesRoot, 'node');

const windows = process.platform === 'win32';
const npmCommand = windows ? 'npm.cmd' : 'npm';
const virtualEnvironmentPython = process.env.VIRTUAL_ENV
  ? path.join(process.env.VIRTUAL_ENV, windows ? 'Scripts/python.exe' : 'bin/python')
  : null;
const pythonCommand = process.env.PYTHON ?? virtualEnvironmentPython ?? (windows ? 'python' : 'python3');

function run(command, args, cwd = repositoryRoot) {
  console.log(`\n> ${command} ${args.join(' ')}`);
  const result = spawnSync(command, args, {
    cwd,
    env: process.env,
    stdio: 'inherit',
    shell: false,
  });

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} exited with status ${result.status ?? 'unknown'}.`);
  }
}

async function exists(target) {
  try {
    await access(target);
    return true;
  } catch {
    return false;
  }
}

async function buildPythonAgent() {
  const spec = path.join(desktopRoot, 'pyinstaller', 'mockmate-agent.spec');
  const workPath = path.join(buildRoot, 'pyinstaller');

  run(pythonCommand, ['-c', 'import PyInstaller']);
  run(pythonCommand, ['-m', 'livekit.agents', 'download-files']);
  run(pythonCommand, [
    '-m',
    'PyInstaller',
    '--noconfirm',
    '--clean',
    '--distpath',
    agentResources,
    '--workpath',
    workPath,
    spec,
  ]);

  const executable = path.join(agentResources, windows ? 'mockmate-agent.exe' : 'mockmate-agent');
  if (!(await exists(executable))) throw new Error(`PyInstaller did not create ${executable}.`);
  if (!windows) await chmod(executable, 0o755);
}

async function buildFrontend() {
  if (!(await exists(path.join(frontendRoot, 'node_modules')))) {
    run(npmCommand, ['install', '--no-audit', '--no-fund'], frontendRoot);
  }

  run(npmCommand, ['run', 'build'], frontendRoot);

  const standalone = path.join(frontendRoot, '.next', 'standalone');
  const staticAssets = path.join(frontendRoot, '.next', 'static');
  if (!(await exists(path.join(standalone, 'server.js')))) {
    throw new Error('Next.js standalone output is missing server.js.');
  }

  await cp(standalone, frontendResources, { recursive: true });
  await mkdir(path.join(frontendResources, '.next'), { recursive: true });
  await cp(staticAssets, path.join(frontendResources, '.next', 'static'), { recursive: true });

  const publicDirectory = path.join(frontendRoot, 'public');
  if (await exists(publicDirectory)) {
    await cp(publicDirectory, path.join(frontendResources, 'public'), { recursive: true });
  }
}

async function bundleNodeRuntime() {
  await mkdir(nodeResources, { recursive: true });
  const destination = path.join(nodeResources, windows ? 'node.exe' : 'node');
  await copyFile(process.execPath, destination);
  if (!windows) await chmod(destination, 0o755);
}

async function main() {
  console.log(`Building MockMate sidecars for ${process.platform}-${process.arch}`);
  await rm(resourcesRoot, { recursive: true, force: true });
  await rm(buildRoot, { recursive: true, force: true });
  await Promise.all([
    mkdir(agentResources, { recursive: true }),
    mkdir(frontendResources, { recursive: true }),
    mkdir(nodeResources, { recursive: true }),
  ]);

  await buildPythonAgent();
  await buildFrontend();
  await bundleNodeRuntime();
  await writeFile(
    path.join(resourcesRoot, 'manifest.json'),
    `${JSON.stringify({ platform: process.platform, arch: process.arch, builtAt: new Date().toISOString() }, null, 2)}\n`,
  );

  console.log('\nMockMate sidecars are ready in desktop/resources.');
}

main().catch((error) => {
  console.error('\nDesktop sidecar build failed.');
  console.error(error instanceof Error ? error.message : error);
  console.error('Install Python build dependencies with: pip install -r desktop/requirements-build.txt');
  process.exitCode = 1;
});
