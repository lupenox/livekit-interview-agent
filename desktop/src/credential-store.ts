import { app, safeStorage } from 'electron';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { CredentialStatus, MockMateCredentials } from './types';

let sessionCredentials: MockMateCredentials | null = null;

function credentialPath(): string {
  return path.join(app.getPath('userData'), 'credentials.enc');
}

export function credentialStatus(): CredentialStatus {
  return {
    saved: sessionCredentials !== null,
    encryptionAvailable: safeStorage.isEncryptionAvailable(),
  };
}

export async function loadCredentials(): Promise<MockMateCredentials | null> {
  if (sessionCredentials) return { ...sessionCredentials };

  try {
    const encoded = await fs.readFile(credentialPath(), 'utf8');
    if (!safeStorage.isEncryptionAvailable()) return null;

    const decrypted = safeStorage.decryptString(Buffer.from(encoded, 'base64'));
    const parsed = JSON.parse(decrypted) as MockMateCredentials;
    sessionCredentials = parsed;
    return { ...parsed };
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== 'ENOENT') console.error('[credentials] unable to load encrypted credentials');
    return null;
  }
}

export async function saveCredentials(
  credentials: MockMateCredentials,
  remember: boolean,
): Promise<CredentialStatus> {
  sessionCredentials = { ...credentials };

  if (!remember) {
    await fs.rm(credentialPath(), { force: true });
    return credentialStatus();
  }

  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('Secure operating-system credential storage is unavailable. Continue without Remember credentials.');
  }

  const encrypted = safeStorage.encryptString(JSON.stringify(credentials));
  await fs.mkdir(path.dirname(credentialPath()), { recursive: true });
  await fs.writeFile(credentialPath(), encrypted.toString('base64'), { mode: 0o600 });
  return credentialStatus();
}

export async function clearCredentials(): Promise<void> {
  sessionCredentials = null;
  await fs.rm(credentialPath(), { force: true });
}
