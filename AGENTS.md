# Repository working agreements

For frontend, visual or interaction work, read [the UI design contract](docs/ui-design-contract.md) and [the regression contract](docs/ui-regression-contract.md) before editing. User instructions for the current task take precedence.

- Start from current main in an isolated branch/worktree. Inspect relevant open PRs and the latest review evidence; do not overwrite another agent's work.
- Preserve the confirmed Classic layout, two-line mobile brand, existing import entry position, visible statistics and expanded reader collection directory unless the user explicitly requests a change.
- Use the existing Classic/Editorial themes and semantic tokens. Match adjacent ordinary content when adding series/episode UI.
- Reproduce visual issues in a browser before fixing them. Test a production build, including persisted-theme cold starts and reloads, not only switching themes after startup.
- For minor-only audits, fix only confirmed low-risk presentation issues. Changes to navigation, entry points, defaults, processing, retry, cancel, deletion or dismissal semantics are flow changes: report them unless already authorized by the user. Do not manufacture changes when checks pass.
- Use synthetic or explicitly controlled data for write interactions. Do not trigger real payment, deletion, subscription or content reprocessing during an audit.
- Record the tested commit, surfaces, viewport/theme/browser coverage, evidence and limitations. Local fixtures, CI WebKit, live-site checks and physical-device checks are distinct claims.
- Run the relevant regression lanes documented below. Do not weaken assertions or raise budgets just to make a change pass. Deploy only within the user's authorization and verify the deployed revision and health, not merely a merged PR.
