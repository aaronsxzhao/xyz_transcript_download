# Local Mac test-account access — 2026-11-15

The user requested persistent access to the dedicated test account without entering
it for each audit. 1Password was not installed. No connected 1Password plugin was
found, and the user explicitly allowed a different solution.

## Installed and verified

Use macOS Keychain through a dedicated native Security-framework helper. Local
installation: `~/Library/Application Support/XYZ Browser Tests/`; command:
`~/.local/bin/xyz-browser-test`. Swift/Python sources and usage notes are installed
alongside the helper, independent of temporary directories and Git checkouts.

The helper addresses only generic-password service
`online.aipodcastsummary.browser-tests`, account label `dedicated-test-account`.
The actual email and password are encrypted together in that one Keychain item;
the email is not used as searchable item metadata. No other Keychain items are
listed. No access policies are broadened, and the helper does not grant every
application access.

The user completed `xyz-browser-test setup` in Terminal with both fields hidden.
`status` subsequently returned `CONFIGURED`. Multiple later reads used the same
stored item without another account prompt. No account values, password, browser
storage state or token are stored in this report, Git, command arguments or a
plaintext credential file.

- Native self-test: isolated random item store/read/delete passed; deletion was
  verified. It never read or replaced the real account.
- Synthetic provider checks: parsing, origin restriction, denied access and
  redacted errors passed.
- Synthetic child-process check: credentials exist only in the trusted child's
  environment, never command arguments or the parent environment. DEBUG/PWDEBUG
  are removed from that child to prevent raw browser input logging. Proxy/CA
  settings remain inherited.
- Actual account validation: one original-site HTTPS/HTTP1.1 sign-in request
  returned HTTP200 and a server-issued session in 2.095s. The returned token was
  not persisted, exported or injected into a browser.
- Normal browser UI authentication also passed in a separately labelled
  Chromium `--disable-http2` comparison: sign-in HTTP200 headers in 2.782s, followed by a real
  protected stats response. Five real saved-video states matched their
  Library/progress status comparison. These are actual account observations.

## Browser coverage boundary

Normal browser runs first encountered connection timeouts; waiting for the
complete document did not establish a successful default-transport login.
A later health preflight also failed before any sign-in request. The account
was not repeatedly re-entered or replaced, and incorrect credentials were not
inferred from these failures.

The labelled HTTP2-disabled browser comparison completed normal sign-in and protected
stats, but its first owned podcast-summary read showed the existing read-timeout
UI. It did not complete the six-case dashboard return matrix or subsequent
controlled series cases. A bounded saved-video-note observation completed normal sign-in again (HTTP200
headers in 2.536s) and protected stats, then stopped on an actual dashboard startup
shell after a safe startup retry. It completed no dashboard return cases. Neither
failed page run is counted as passed. Account availability must not be confused with
complete online reader acceptance.

Public TLS connection comparisons to the domain's actual DNS addresses also
varied: one health connection hit an eight-second TLS-connect ceiling while
other fresh health/config requests returned 200 in about 2–8s. The browser comparison used only `--disable-http2`; QUIC was not separately
disabled and per-request negotiated protocol was not recorded, so it is not a
proof that every browser request used HTTP1.1. These are connection
observations, not proof that Cloudflare, HTTP2 or the application caused the fault.
No Cloudflare setting, global browser option, application deadline, size budget,
assertion, auth policy or RLS rule was changed.

## Future operation

Before requesting the test account again, use `xyz-browser-test status`. If
configured, use `xyz-browser-test check` or import the installed
`runner.credentials()` from a trusted test runner. Custom runners must keep the
secret in memory, use the configured HTTPS origin, suppress debug/traces and
perform normal UI sign-in. The internal native `read` action is a private pipe
interface; never run it directly in a logged tool call.

Only a genuine credential rejection/password change calls for updating the same
item with `setup`. Connection timeouts do not call for re-entering the account.
A locked Keychain or OS access denial requires the user to unlock/authorize the
dedicated helper. Other hosts do not gain this Mac's account automatically.

No payment, content generation, import, deletion, subscription or reprocessing
was triggered. No paid verification was repeated. Private screenshots remain in
`appearance-checks/nov15-dashboard-return/keychain-live-authenticated*/` in the
original checkout; none is published or committed here.

Apple references: [Keychain access prompts](https://support.apple.com/en-ge/guide/keychain-access/kyca1243/mac),
[macOS Keychain API implementations](https://developer.apple.com/documentation/technotes/tn3137-on-mac-keychains).
