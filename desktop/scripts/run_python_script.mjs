import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';

function detectPython() {
  const candidates = process.platform === 'win32'
    ? [
        { command: 'py', prefixArgs: ['-3'] },
        { command: 'python', prefixArgs: [] },
        { command: 'python3', prefixArgs: [] },
      ]
    : [
        { command: 'python3', prefixArgs: [] },
        { command: 'python', prefixArgs: [] },
      ];

  for (const candidate of candidates) {
    const result = spawnSync(candidate.command, [...candidate.prefixArgs, '--version'], {
      stdio: 'ignore',
    });
    if (result.status === 0) {
      return candidate;
    }
  }

  throw new Error('Python 3.9+ is required to build the desktop backend runtime.');
}

const [, , scriptPath, ...scriptArgs] = process.argv;

if (!scriptPath) {
  throw new Error('Usage: node run_python_script.mjs <script> [...args]');
}

const python = detectPython();
const resolvedScript = path.resolve(process.cwd(), scriptPath);
const result = spawnSync(
  python.command,
  [...python.prefixArgs, resolvedScript, ...scriptArgs],
  {
    stdio: 'inherit',
    cwd: process.cwd(),
  },
);

if (typeof result.status === 'number') {
  process.exit(result.status);
}

throw result.error ?? new Error('Python build script failed.');
