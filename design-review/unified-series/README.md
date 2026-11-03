# Unified series presentation

Series use the existing content-card artwork, metadata, title, source and footer classes. Library grid/list mode now applies to series too. The episode disclosure occupies the same footer position as the ordinary read action; missing artwork uses the existing video icon rather than a separate “Series” placeholder.

Dashboard series stay in the recent-content list so Editorial artwork direction and typography match adjacent ordinary notes. Channels use the same cover/title/source/footer order and View/Hide episodes wording. The reader uses Series / Episodes labels and retains its expanded directory and existing selection, status and processing behavior.

Validation: 524 frontend tests; production build 197.6 KiB / 197.75 KiB budget; persisted-theme browser checks across Classic/Editorial, light/dark and 390/820/1440 widths, including equal artwork widths, title font sizes and body alignment between list cards. Series expansion/order/retry and multipart reader/selection regressions also exercised. CI repeats theme and multipart checks in WebKit.

Screenshots are from a local production build with controlled synthetic data, not production account acceptance.
