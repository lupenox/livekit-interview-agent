import './styles.css';
import type { MockMateCredentials, ProviderTest, ServiceEvent } from './types';

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) {
    throw new Error(`MockMate setup UI is missing ${selector}.`);
  }
  return element;
}

const form = requireElement<HTMLFormElement>('#credential-form');
const testButton = requireElement<HTMLButtonElement>('#test-button');
const clearButton = requireElement<HTMLButtonElement>('#clear-button');
const rememberInput = requireElement<HTMLInputElement>('#remember');
const message = requireElement<HTMLDivElement>('#message');
const testResults = requireElement<HTMLDivElement>('#test-results');
const logOutput = requireElement<HTMLPreElement>('#service-log');

const fields: Array<keyof MockMateCredentials> = [
  'livekitUrl',
  'livekitApiKey',
  'livekitApiSecret',
  'groqApiKey',
  'deepgramApiKey',
  'elevenlabsApiKey',
];

function credentialsFromForm(): MockMateCredentials {
  const credentials = {} as MockMateCredentials;
  for (const field of fields) {
    const input = form.elements.namedItem(field);
    if (!(input instanceof HTMLInputElement)) throw new Error(`Missing ${field} field.`);
    credentials[field] = input.value.trim();
  }
  return credentials;
}

function fillForm(credentials: MockMateCredentials): void {
  for (const field of fields) {
    const input = form.elements.namedItem(field);
    if (input instanceof HTMLInputElement) input.value = credentials[field];
  }
}

function setBusy(busy: boolean): void {
  for (const element of form.elements) {
    if (element instanceof HTMLInputElement || element instanceof HTMLButtonElement) {
      element.disabled = busy;
    }
  }
  testButton.disabled = busy;
  clearButton.disabled = busy;
}

function setMessage(copy: string, kind: 'info' | 'error' | 'success' = 'info'): void {
  message.textContent = copy;
  message.dataset.kind = kind;
}

function renderTests(results: ProviderTest[]): void {
  testResults.replaceChildren(
    ...results.map((result) => {
      const row = document.createElement('div');
      row.className = `provider-result ${result.ok ? 'provider-ok' : 'provider-error'}`;
      const provider = document.createElement('strong');
      provider.textContent = result.provider;
      const detail = document.createElement('span');
      detail.textContent = result.message;
      row.append(provider, detail);
      return row;
    }),
  );
}

function appendServiceEvent(event: ServiceEvent): void {
  const cleaned = event.message.trimEnd();
  if (!cleaned) return;
  logOutput.textContent += `[${event.service}:${event.stream}] ${cleaned}\n`;
  logOutput.scrollTop = logOutput.scrollHeight;
}

async function initialize(): Promise<void> {
  const [status, saved] = await Promise.all([
    window.mockMateDesktop.getCredentialStatus(),
    window.mockMateDesktop.getSavedCredentials(),
  ]);
  rememberInput.disabled = !status.encryptionAvailable;
  if (!status.encryptionAvailable) {
    const copy = document.querySelector<HTMLElement>('#remember-copy');
    if (copy) copy.textContent = 'Secure OS storage is unavailable; credentials will remain in memory only.';
  }
  if (saved) {
    fillForm(saved);
    rememberInput.checked = true;
    setMessage('Saved credentials loaded securely.', 'success');
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  setBusy(true);
  setMessage('Starting the local MockMate services…');
  try {
    await window.mockMateDesktop.startMockMate(credentialsFromForm(), rememberInput.checked);
    setMessage('MockMate is ready.', 'success');
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'MockMate could not start.', 'error');
  } finally {
    setBusy(false);
  }
});

testButton.addEventListener('click', async () => {
  setBusy(true);
  setMessage('Testing provider credentials…');
  try {
    const results = await window.mockMateDesktop.testCredentials(credentialsFromForm());
    renderTests(results);
    const allGood = results.every((result) => result.ok);
    setMessage(allGood ? 'All credentials are valid.' : 'Some credentials need attention.', allGood ? 'success' : 'error');
  } catch (error) {
    setMessage(error instanceof Error ? error.message : 'Credential test failed.', 'error');
  } finally {
    setBusy(false);
  }
});

clearButton.addEventListener('click', async () => {
  await window.mockMateDesktop.clearCredentials();
  form.reset();
  testResults.replaceChildren();
  setMessage('Saved credentials removed.');
});

window.mockMateDesktop.onServiceEvent(appendServiceEvent);
void initialize();
