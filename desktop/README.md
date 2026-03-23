# Desktop Packaging

This folder wraps the existing local FastAPI + React app in Electron so the app can open in a native window, start its local backend automatically, and stop it when the window closes.

## Behavior

- The desktop app stores data locally under the OS user-data directory.
- The packaged backend forces local mode by clearing Supabase auth environment variables unless you explicitly override them.
- The Electron shell launches the backend on a free localhost port and waits for `/api/health` before showing the window.

## Build Flow

1. Install desktop dependencies:

```bash
cd desktop
npm install
```

2. Build the frontend and stage the backend runtime:

```bash
npm run build:web
npm run prepare:backend
```

3. Build installers on the target OS:

```bash
npm run dist
```

## Outputs

- macOS: `desktop/dist/*.dmg` and `desktop/dist/*.zip`
- Windows: `desktop/dist/*.exe` and `desktop/dist/*.zip`

## Notes

- The backend runtime is staged into `desktop/.stage/backend`.
- The staging script creates a Python virtualenv and installs `requirements.txt`, so the build machine needs Python 3.9+.
- If `ffmpeg` and `ffprobe` are available on the build machine, they are copied into the packaged app resources.
- Unsigned builds may trigger macOS Gatekeeper or Windows SmartScreen warnings until signing is added.
