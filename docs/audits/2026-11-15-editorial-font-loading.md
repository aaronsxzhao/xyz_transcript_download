# Editorial font delivery — 2026-11-15

Baseline main / deployed revision: `1f33f3e8cd97c036680aa30c0a9afe454c607190` (#272). Follow-up branch: `codex/nov15-editorial-font-loading`, created from that main in the existing isolated worktree. #271 is preserved. See the [startup diagnosis](2026-11-15-startup-transport.md).

## Production counterexample

#272 full PR CI 43622847598 passed; formal Oracle deployment 43626099659 succeeded. Independent Mac health returned HTTP200 with the exact revision (one earlier 30s no-response probe is retained, then a 2.14s successful probe). This did not close Editorial acceptance.

Fresh secure Chrome 157 contexts, service workers blocked and HTTP cache disabled by read-only request routing: six anonymous Editorial cases at 390/820/1440px × light/dark. Three passed; both 820px cases rendered Classic instead of Editorial, and 1440px dark reload remained on the startup shell at the original test timeout. Failure screenshots were actually viewed. In 820px light a public recovery response completed with HTTP200, Brotli, cache MISS, 2.242s; the form appeared while document.readyState was still loading. This is evidence of the deployed recovery resource and early form availability, not complete themed acceptance.

The remaining critical stylesheet was 142,686 raw / 42,720 gzip bytes. It combined 46,699 raw / 6,579 gzip bytes of theme rules with the large Unicode font-face manifest. The eight-second skin timeout could discard the whole selected appearance when that font metadata transfer stalled. Early preload alone did not remove this dependency.

## Change

Separate the same Noto Serif SC font-face declarations into a dedicated Vite CSS entry. Keep it outside the workspace group so it cannot inflate the embedded program. Keep the original glyph files, Unicode ranges, variable weights, font-display:swap policy and fallback stacks.

The early appearance bootstrap preloads the selected theme normally, and starts font metadata independently at low priority. Once that public preload completes it becomes a stylesheet. The theme promise does not await it. Runtime switches to Editorial use the same idempotent loader; development still imports the font CSS. A failed font manifest leaves readable fallback fonts and the selected Editorial colors/layout. The original eight-second theme timeout remains unchanged. No new retry loop, account write, payment or processing behavior is added.

The critical Editorial CSS is now 6,579 gzip bytes rather than 42,720 (85% less). Font metadata is a separate 35,282 gzip bytes. The complete document is 202,235 gzip bytes (197.5 KiB), below the unchanged 202,496-byte ceiling. No size assertion or timing budget was raised.

## Regression evidence

Local macOS 26.5.2, sandboxed Chrome 157 and Playwright WebKit 27.2, production build and controlled data only:

- New `check_editorial_font_loading.py` holds the response containing font-face declarations. Both baseline engines fail to open the form within the original 2.5s startup ceiling; candidate opens in 69ms Chromium / 115ms WebKit while font metadata is still unavailable. Email entry and checkbox interaction work then survive actual font application. The manifest HTTP503 case is explicitly observed with cache disabled; Editorial light remains selected and usable.
- Existing `check_editorial_fonts.py`: 390/1440px × light/dark, both engines pass actual custom Chinese glyph checks, same-origin loading, 13 used Unicode subsets and Classic exclusion. The existing real-glyph assertions are retained.
- All 556 frontend tests pass. `check_document_startup.py`, `check_page_boundaries.py` and the 12 persisted-theme `check_series_theme_browser.py` cases pass. Inline startup, recovery, single mount, asset failure and CSS order remain covered.
- The new font loading lane is added beside the existing font checks in full CI; its three-minute step cap is retained.
- Actually viewed local images: `local/after-chromium-fonts.png`, `local/after-webkit-fonts.png`, `fonts-chromium/390-light-reader.png`, `fonts-webkit/390-dark-reader.png`. Other captured glyph images are assertion evidence, not a claim of manual visual review.

Private evidence: original checkout `appearance-checks/cloud-browser/nov15-font-loading/`. The first post-#272 live attempt remains under `appearance-checks/cloud-browser/nov15-startup/live-anonymous/`; it is intentionally recorded as PARTIAL and must not be relabelled passed.

## Release follow-up

Full CI, merge, formal deployment, exact live SHA and the replacement online matrix remain to be recorded after this patch. Preserve the failed first matrix. Anonymous login checks and controlled local readers do not establish authenticated production series/reader coverage. The dedicated credential is still absent from the private input file and both BROWSER_TEST bindings; the existing Chrome profile also showed an empty login form. No token was fabricated or exported. No closed paid generation/import validation was repeated.
