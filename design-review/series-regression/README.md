# Series cold-start regression

The lazy series chunk requested shared workspace CSS after the persisted Editorial skin. The document already inlined that CSS, but Vite only recognized stylesheet links, causing a second base stylesheet to override equal-specificity skin rules. Disabled stylesheet markers now identify inlined CSS without another request or another applied stylesheet.

The previous series browser fixture switched skins after initial page load and did not include ordinary cards beside a series. Added cold-start and reload checks with mixed content for Classic/Editorial, light/dark, 390/820/1440 widths, plus skin round trips, hover, and no duplicate base-CSS request assertions. These are local controlled-data screenshots, not production-account verification. CI also runs the new checks in WebKit.

Recent content and Library now fetch bounded continuation pages when series grouping underfills the page. Reads stop at the original title target, exhaustion, a repeated cursor, or five pages, preserving the continuation button. Ordinary ungrouped pagination is unchanged. Series presentation follows Editorial list separators.

Validation: 524 frontend tests; 12 cold-start/reload/theme combinations; 12 series directory/order/retry combinations; document startup regression; production build 197.5 KiB under unchanged 197.75 KiB budget. Updated existing channel deletion test to await the already-lazy list before interacting, with no deletion behavior change.
