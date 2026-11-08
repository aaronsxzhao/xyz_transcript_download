# UI design contract

This records the accepted product direction, not a new redesign. The authored CSS is the source of exact token values. Change this contract alongside an explicitly authorized design change; do not use it to silently restyle existing pages.

## Two designs, two color modes

| Design | Intent | Typography | Surfaces and accent |
| --- | --- | --- | --- |
| Classic | Familiar tool interface; retain the established layout | System sans-serif | Existing slate/indigo palette, distinct panels, current spacing and hierarchy |
| Editorial | Calm publication and reading experience | `--publication-serif`; shipped Chinese serif fallback | Warm neutral surfaces, terracotta accent, restrained separators instead of unrelated filled cards |

Both support light and dark. Theme switching changes presentation, not content, navigation, drafts or task state. Light is not simply a white background on dark components. Disabled, selected, hover, focus, loading, error and empty states belong to all four appearances.

Token sources:
- `web/src/index.css`: Classic base and shared structural rules.
- `web/src/classic-light.css`: Classic light colors.
- `web/src/editorial.css`: Editorial tokens, typography and scoped overrides.
- `web/src/appearance.css`: shared appearance controls and corrections.

Use `--ui-bg`, `--ui-surface`, `--ui-hover`, `--ui-border`, `--ui-text`, `--ui-secondary`, `--ui-muted`, `--ui-accent`, `--ui-accent-fill`, `--ui-on-accent`, `--ui-tint`, `--ui-radius` and `--ui-card-radius` where defined by the component/theme; retain existing fallbacks for Classic. Do not copy a dark slate background or indigo selected fill into a theme-independent component. Current shared radius defaults are 8px controls/12px cards for Classic and 4px for Editorial; specialized tabs, pills and image controls retain their existing geometry.

## Layout invariants

- Preserve Classic's established base layout. A fix for Editorial must not unintentionally alter it.
- Keep the mobile brand on two lines with compact vertical spacing; protect the theme selector, color toggle and menu touch targets. Do not shrink the title to make a toolbar fit.
- Keep the import entry in its current position. Keep statistics visible and reader collection details expanded by default.
- Responsive fixes may wrap metadata/actions without moving functionality to a different journey. Use `min-width:0`, controlled wrapping and scoped overflow handling; do not hide overflow on the whole page to conceal a broken child.
- Long CJK titles, long English titles and unbroken text must not collide with source, date or actions. Respect the existing line clamp for the surface; do not impose one global clamp on all headings.
- Keep existing per-surface spacing. New components should reuse adjacent card/body/footer classes rather than invent a parallel spacing scale.

## Content and series

A multipart source is one series with ordered episodes, not unrelated copies of the same video. Group using source identity, not title similarity. Each episode retains its own summary and processing state.

- Dashboard series follow adjacent recent-note typography, artwork direction and separators.
- Library series and ordinary notes share artwork dimensions, metadata, title, source and footer alignment in both grid and list modes.
- Channel series follow the established channel-card structure. Reader directories remain inside the reading column and retain the current episode indicator.
- Put episode count/status in the metadata/footer and the existing View/Hide episodes disclosure in the corresponding action position. Avoid an oversized bespoke series button or a text-only “Series” image placeholder.
- Use actual source artwork when available and the existing media icon fallback otherwise. Preserve image proportions; avoid cropping instructional screenshots. Match the surface's established cover/contain choice.
- Across surfaces, a saved episode must not become “not processed” just because another listing lacks its metadata. Tests must distinguish loaded-page counts, total series parts and ready episodes.

## Controls and feedback

Use shared Button, reader-action, ui-button and ItemActions conventions where applicable. Primary actions use the theme accent; destructive actions remain distinguishable. Labels and status must not rely solely on color or a numeric badge.

Touch controls should retain existing 44px targets; dense desktop controls may use the established smaller height. Keep visible keyboard focus, accessible names for icon-only controls, accurate disabled/loading states, `aria-expanded` for disclosures and `aria-pressed` for toggles. Verify normal text contrast of at least 4.5:1 and essential non-text/focus cues at least 3:1 in actual composited backgrounds; disabled controls are a separate state.

Progress presentation must reflect the current task/run, remain consistent between cards and task drawers, and not jump backward due to stale updates. Do not fabricate completion or silently modify processing logic under a visual-only fix. Check reduced motion when changing animations.

## CSS loading is part of appearance

Optional components must not reapply base CSS after the selected skin. The production build inlines base styles and retains disabled stylesheet markers for Vite dependency detection. Test persisted Editorial and Classic light on direct navigation, reload, lazy component load and theme round trips. A screenshot taken only after manually switching themes is insufficient.

## Currency and math in saved-note readers

Single-dollar inline formulas use tight delimiters (`$x^2$`, `$2 + 2$`): no
whitespace immediately inside the delimiters, and no digit immediately after
the closing dollar. This prevents prices such as `$100 … $5` from consuming
prose and emphasis as a formula. Use `$$ … $$` for padded inline math or a
separate `$$` block for display math. Escaped dollars and code remain literal.
This is a display-only policy; saved Markdown is not rewritten. The user
explicitly authorized the currency/math parsing fix on 2026-11-08.
