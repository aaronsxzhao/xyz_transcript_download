# Cloud browser inspection

The managed cloud image was validated with system Chromium 154.0.8037.57,
Python 3.12.14, Playwright 1.62.0 and Node 24.19.0. No installation was needed.
This is a shell-driven headless browser; it does not require the built-in Browser
plugin and does not provide a shared desktop for manual sign-in.

## Preflight and permissions

Read the environment status and `/etc/codex/network-policy.json`. Inspect existing
versions and missing linked libraries before installing anything:

```sh
chromium --version
python --version
node --version
python -c "import importlib.metadata; print(importlib.metadata.version('playwright'))"
ldd /usr/lib/chromium/chromium
```

The restricted shell denied Chromium crashpad `setsockopt` with
`Operation not permitted` (SIGTRAP). The same browser worked through the approved
`exec_command` execution with `sandbox_permissions="require_escalated"`.
Permission is granted by the execution host, not by this script or repository.
Future tasks must use the supported permission request when necessary; a prior
successful run does not grant permanent permissions. Record denials separately.

Keep the inherited proxy and CA trust. The script explicitly enables Chromium's
sandbox and TLS certificate verification. Do not add `--no-sandbox`, ignore TLS
errors, disable web security or bypass the platform proxy. If the host cannot
support secure Chromium, report the exact launch blocker. Do not weaken assertions.

## Anonymous recurring inspection

From the repository root, use a new evidence directory per run:

```sh
python scripts/check_cloud_browser.py \
  --output appearance-checks/cloud-browser/RUN-ID/anonymous
```

This exercises actual DOM, a reversible checkbox click, navigation to a protected
route, reload, horizontal bounds and screenshots at 1440x900, 768x1024 and 390x844.
It is an anonymous login-page smoke test, not full product or theme acceptance.
Use the existing UI regression contract lanes for broader local synthetic tests.
No scheduler or automatic production job is installed by this change.

## Explicit authenticated inspection

Only use an authorized test account. Supply `BROWSER_TEST_EMAIL` and
`BROWSER_TEST_PASSWORD` through a secure execution environment or a private
interactive prompt; never put values in commands, source, reports or commits.
Environment variables are optional. With an interactive terminal, the script
prompts without echo for missing values. Previously authorized credentials can
be entered this way; missing environment bindings alone are not a blocker.
Unattended runs require an available confidential credential channel; never copy
credentials into the scheduled instruction text or saved evidence.
The browser process must have access to actual runtime values: an HTTP proxy
placeholder is not necessarily usable as a UI password.

```sh
python scripts/check_cloud_browser.py --authenticated \
  --output appearance-checks/cloud-browser/RUN-ID/authenticated
```

This performs the ordinary sign-in UI, checks the server-issued session and a
successful protected `/api/stats` response, then checks Library link navigation
and reload at the three sizes. No token is fabricated, exported or injected.
The only allowed POST is the explicit same-origin sign-in request; other write
requests are blocked and counted. Performance telemetry is locally suppressed.
Session refresh writes are also blocked: expiry is a coverage blocker, not an
excuse to bypass authentication. No storage state, HAR, raw DOM or trace is saved.
Authenticated screenshots may show test-account content: keep artifacts private,
inspect them before sharing, and never commit them without checking their contents.
The authenticated path must be exercised before claiming its coverage; adding it
to the script alone does not validate it.

## Evidence and actual visual review

Each run writes `results.json` with mode, session verification, browser version,
viewport assertions, screenshot names and failure category. Use a fresh RUN-ID
so prior images cannot be mistaken for current evidence. Files created by this
script use a private umask; the generated evidence directory is gitignored.
Record the git SHA and exact command alongside the report.

After capture, open every accepted PNG using `view_image` or another available
image-capable tool and inspect the actual contents. Create a separate
`visual-review.json` with reviewed filenames, reviewer, timestamp, observations
and defects. The script always leaves `visual_inspection: NOT_REVIEWED`; do not
change it based solely on screenshot existence or automated assertions.

For a defect record the mode, SHA, viewport/theme, navigation and interaction
steps, assertion, screenshot and reproducibility. Reproduce in a fresh run before
changing application code. Raw Playwright exceptions are deliberately omitted
because they can contain credentials; the report supplies stage/category/type.
For launch errors use a separate credential-free preflight to obtain the exact
stderr. Classify socket/sandbox permissions, proxy denials and certificate trust
as environment issues. Do not label them application bugs.

Preserve the existing boundaries: production content read-only; synthetic or
controlled data for write tests; confirmed presentation fixes only within the
current authorization. No deployment follows automatically from a passing smoke
test. Physical-device, authenticated, local-fixture and remote-desktop coverage
remain separate claims.
