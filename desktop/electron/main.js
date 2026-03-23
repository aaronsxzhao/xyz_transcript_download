const { app, BrowserWindow, dialog, shell } = require('electron');
const fs = require('fs');
const net = require('net');
const path = require('path');
const { execFile, spawn, spawnSync } = require('child_process');

const APP_NAME = 'XYZ Podcast';
const BACKEND_HEALTH_TIMEOUT_MS = 30000;
const BACKEND_POLL_INTERVAL_MS = 500;

let backendProcess = null;
let backendExitInfo = null;
let backendUrl = null;
let mainWindow = null;
let isQuitting = false;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getRepoRoot() {
  return path.resolve(__dirname, '..', '..');
}

function getPackagedBackendRoot() {
  return path.join(process.resourcesPath, 'backend');
}

function getBackendAppRoot() {
  return app.isPackaged ? path.join(getPackagedBackendRoot(), 'app') : getRepoRoot();
}

function getToolsRoot() {
  return app.isPackaged ? path.join(process.resourcesPath, 'tools') : null;
}

function getBackendEntryScript() {
  return path.join(getBackendAppRoot(), 'desktop', 'backend', 'run_server.py');
}

function getPackagedPythonBinary() {
  const runtimeRoot = path.join(getPackagedBackendRoot(), 'runtime');
  const candidates = process.platform === 'win32'
    ? [path.join(runtimeRoot, 'Scripts', 'python.exe')]
    : [
        path.join(runtimeRoot, 'bin', 'python3'),
        path.join(runtimeRoot, 'bin', 'python'),
      ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return null;
}

function findSystemPythonBinary() {
  const repoRoot = getRepoRoot();
  const repoVenvCandidates = process.platform === 'win32'
    ? [path.join(repoRoot, 'venv', 'Scripts', 'python.exe')]
    : [
        path.join(repoRoot, 'venv', 'bin', 'python3'),
        path.join(repoRoot, 'venv', 'bin', 'python'),
      ];

  for (const candidate of repoVenvCandidates) {
    if (fs.existsSync(candidate)) {
      return { command: candidate, prefixArgs: [] };
    }
  }

  const candidates = process.platform === 'win32'
    ? ['py', 'python', 'python3']
    : ['python3', 'python'];

  for (const candidate of candidates) {
    const args = candidate === 'py' ? ['-3', '--version'] : ['--version'];
    const result = spawnSync(candidate, args, { stdio: 'ignore' });
    if (result.status === 0) {
      return candidate === 'py' ? { command: 'py', prefixArgs: ['-3'] } : { command: candidate, prefixArgs: [] };
    }
  }

  return null;
}

function getPythonLaunchCommand() {
  if (app.isPackaged) {
    const command = getPackagedPythonBinary();
    if (!command) {
      throw new Error('Bundled Python runtime was not found in the packaged app.');
    }
    return { command, prefixArgs: [] };
  }

  const detected = findSystemPythonBinary();
  if (!detected) {
    throw new Error('Python 3 was not found. Install Python 3.9+ to run the desktop app in development.');
  }
  return detected;
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : null;
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolve(port);
      });
    });
  });
}

async function waitForBackendReady(url) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < BACKEND_HEALTH_TIMEOUT_MS) {
    if (backendExitInfo) {
      throw new Error(`Backend exited early with code ${backendExitInfo.code} and signal ${backendExitInfo.signal}.`);
    }

    try {
      const response = await fetch(`${url}/api/health`);
      if (response.ok) {
        return;
      }
    } catch (error) {
      // Backend is still starting.
    }

    await sleep(BACKEND_POLL_INTERVAL_MS);
  }

  throw new Error('Timed out waiting for the local backend to become ready.');
}

function buildBackendEnvironment() {
  const userDataDir = app.getPath('userData');
  const dataDir = path.join(userDataDir, 'data');

  fs.mkdirSync(dataDir, { recursive: true });

  const env = {
    ...process.env,
    XYZ_DATA_DIR: dataDir,
    SUPABASE_URL: '',
    SUPABASE_KEY: '',
    SUPABASE_SERVICE_KEY: '',
    SUPABASE_JWT_SECRET: '',
    XYZ_DESKTOP_MODE: '1',
    PYTHONUNBUFFERED: '1',
  };

  const toolsRoot = getToolsRoot();
  if (toolsRoot && fs.existsSync(toolsRoot)) {
    env.PATH = `${toolsRoot}${path.delimiter}${env.PATH || ''}`;
  }

  return env;
}

async function startBackend() {
  const port = await getFreePort();
  const url = `http://127.0.0.1:${port}`;
  const entryScript = getBackendEntryScript();

  if (!fs.existsSync(entryScript)) {
    throw new Error(`Backend entry script not found: ${entryScript}`);
  }

  const python = getPythonLaunchCommand();
  const args = [
    ...python.prefixArgs,
    entryScript,
    '--host',
    '127.0.0.1',
    '--port',
    String(port),
  ];

  backendExitInfo = null;
  backendProcess = spawn(python.command, args, {
    cwd: getBackendAppRoot(),
    env: buildBackendEnvironment(),
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProcess.stdout.on('data', (chunk) => {
    process.stdout.write(`[backend] ${chunk}`);
  });

  backendProcess.stderr.on('data', (chunk) => {
    process.stderr.write(`[backend] ${chunk}`);
  });

  backendProcess.on('exit', (code, signal) => {
    backendExitInfo = { code, signal };
    console.log(`[backend] exited code=${code} signal=${signal}`);
    backendProcess = null;
  });

  await waitForBackendReady(url);
  backendUrl = url;
}

function killProcessTree(pid) {
  return new Promise((resolve) => {
    if (!pid) {
      resolve();
      return;
    }

    if (process.platform === 'win32') {
      execFile('taskkill', ['/pid', String(pid), '/t', '/f'], (error) => {
        if (error && error.code !== 128) {
          console.warn('Failed to terminate backend process tree:', error);
        }
        resolve();
      });
      return;
    }

    try {
      process.kill(pid, 'SIGTERM');
    } catch (error) {
      if (error.code === 'ESRCH') {
        resolve();
        return;
      }
      console.warn('Failed to send SIGTERM to backend:', error);
    }

    setTimeout(() => {
      try {
        process.kill(pid, 'SIGKILL');
      } catch (error) {
        if (error.code !== 'ESRCH') {
          console.warn('Failed to force kill backend:', error);
        }
      }
      resolve();
    }, 3000);
  });
}

async function stopBackend() {
  if (!backendProcess) {
    return;
  }

  const pid = backendProcess.pid;
  backendProcess.removeAllListeners('exit');
  backendProcess.stdout?.removeAllListeners('data');
  backendProcess.stderr?.removeAllListeners('data');
  backendProcess = null;
  backendExitInfo = null;
  backendUrl = null;
  await killProcessTree(pid);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 760,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#111827',
    title: APP_NAME,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.loadURL(backendUrl);
}

async function bootstrap() {
  try {
    await startBackend();
    createWindow();
  } catch (error) {
    console.error(error);
    await dialog.showMessageBox({
      type: 'error',
      title: APP_NAME,
      message: 'The desktop app could not start its local backend.',
      detail: error instanceof Error ? error.message : String(error),
    });
    await stopBackend();
    app.quit();
  }
}

app.on('before-quit', async (event) => {
  if (isQuitting) {
    return;
  }

  isQuitting = true;
  event.preventDefault();
  await stopBackend();
  app.quit();
});

app.on('window-all-closed', () => {
  app.quit();
});

app.whenReady().then(bootstrap);
