# The Sunday Decision Lab performance audit

Date: 2026-10-08

## Executive result

The optimized visitor path typically becomes usable in about 2.0–2.6 seconds in local Streamlit application tests, versus a target of 3 seconds. Warm full-app reruns measure about 315–340 milliseconds. The comparison workflow remains under the 2-second target after data is available. Projection, floor, and ceiling values are unchanged for all 487 players in the validated production snapshot.

Render Starter remains appropriate for the present traffic level of fewer than 10 users, but it has little memory headroom on the currently deployed release. The live service used roughly 68–90% of its 512 MB limit during the observed 12-hour window. Ten truly simultaneous cold sessions are not a realistic guaranteed target on 0.5 CPU: a synthetic local test completed in about 6.9 seconds wall time. The optimized release should be deployed and observed before considering any hosting change.

## Measurement scope

All local application measurements used the published snapshot path rather than provider refresh jobs. Results are workstation measurements and do not represent Render network or cold-container latency. The live HTTP time-to-first-byte checks and Render dashboard readings are production measurements. The ten-session test uses Streamlit AppTest threads in one process and is a conservative approximation, not a production load generator.

## Before and after

| Workflow or resource | Before | After | Status |
|---|---:|---:|---|
| Injury scenario calculation, 487 players | 950 ms | 60–87 ms; about 70 ms average | Verified |
| Snapshot network requests | About 0.89 s sequential | Board and weekly snapshots requested concurrently with pooled connections | Verified implementation; actual gain depends on network |
| Local Parquet snapshot read | 82 ms | Cached resource retrieval avoids repeat reads and per-session DataFrame copies | Verified |
| Typical initial local app run | No reliable like-for-like full-app baseline because the old browser-storage component blocks headless AppTest | 2.0–2.6 s typical; one cold outlier 3.76 s | Verified after |
| Warm full-app rerun | Not measured reliably before | 315–340 ms | Verified after |
| Scoring-format change | Not measured reliably before | 413–476 ms | Verified after |
| Position navigation | Not measured reliably before | 315–513 ms | Verified after |
| Optimized local process working set | Not applicable | About 167–201 MB; about 202 MB peak in the representative run | Verified after |
| Current live Render memory | Roughly 68–90% of 512 MB | Requires optimized deployment to remeasure | Verified current release |
| Current live HTTP TTFB | 0.31–0.44 s | Optimized release not deployed | Verified current release |
| Synthetic 10 cold sessions | Not measured before | About 6.9 s wall time; about 6.8 s median session | Estimated capacity test |
| Logo payload | 576,541 bytes | 135,576 bytes | Verified |
| Icon payload | 47,757 bytes | 26,012 bytes | Verified |

## Ten largest bottlenecks

1. Injury-impact calculations ran on every Streamlit rerun and used row-wise Pandas operations. Fixed with vectorized/grouped calculations and snapshot-level caching.
2. Streamlit reran the monolithic page for small inputs, including every search keystroke. Search now submits through a form; panels are lazily rendered.
3. The live service is near its 512 MB memory ceiling. Unused Plotly code and the dashboard dependency were removed, and shared snapshots now use a resource cache.
4. Immutable snapshot DataFrames were copied through `cache_data` for sessions and reruns. They are now shared through a bounded `cache_resource` and treated as read-only by consumers.
5. Board and weekly snapshot files were downloaded sequentially. They now download concurrently through a small pooled HTTP session.
6. Closed Streamlit expanders still executed share-image and Analysis Hub content. Both now use explicit lazy toggles.
7. Desktop and mobile selection cards were both rendered on the server and one copy was only hidden by CSS. One responsive card tree now serves both layouts.
8. Large logos were base64-encoded into page HTML on every run. Streamlit now serves compressed image assets through its cacheable media endpoint.
9. The browser-local-storage component mounted on ordinary reruns. It now mounts only while restoring or persisting onboarding state.
10. Render Starter supplies only 0.5 CPU. Ten simultaneous cold sessions remain CPU-constrained even after application optimizations.

## Implementation details

### `dashboard/app.py`

- Added a bounded reusable HTTP session with connection pooling and safe connect/read timeouts.
- Reduced metadata cache expiration to preserve freshness while preventing repeated requests.
- Fetches the board and weekly snapshot concurrently.
- Uses a bounded resource cache for immutable shared DataFrames.
- Precomputes the injury scenario once per published snapshot and scoring format.
- Makes the Analysis Hub and share-image builder lazy.
- Caches generated share images with a bounded entry count.
- Uses a search form to avoid reruns for every typed character.
- Removes duplicate mobile selection-card rendering.
- Serves optimized logo files through `st.image` instead of embedding base64 repeatedly.
- Mounts persistent onboarding storage only when needed.
- Removes unused Plotly import and chart helper.

### `dashboard/injury_impact.py`

- Replaced row-wise `DataFrame.apply`, nested frame filtering, and scalar writes with array-backed grouped calculations.
- Preserved the original factors, caps, ordering, text rules, and projection outputs.

### `dashboard/requirements.txt`

- Removed unused Plotly from the deployed dashboard image to reduce build size, import overhead, and memory pressure.

### Assets

- Resized the full logo to 450 x 343 and the icon to 176 x 168 at the dimensions used by the interface.

### Test configuration

- Restricted default Pytest discovery to `tests`, preventing local runtime and generated directories from being scanned accidentally.

## Accuracy and safety validation

- 101 automated tests pass.
- 17 focused dashboard and injury tests pass.
- Python compilation and whitespace validation pass.
- `median_ppr`, `floor_ppr`, `ceiling_ppr`, and `projected_ppr` are identical before and after injury enrichment for all 487 snapshot rows.
- Cache keys include the snapshot URLs and scoring format. Public immutable datasets may be shared; user selections and interface state remain in Streamlit session state and are not cached globally.
- Provider and refresh workflows were not removed or made less frequent.

## Remaining issues and recommended rollout

1. Deploy the tested optimized release, then observe Render memory, CPU, restart events, and response behavior for at least one normal usage window.
2. Run a real HTTP load test against a staging or production deployment during a controlled window. AppTest concurrency is not a substitute for browser/server load testing.
3. The 300 ms interaction target is nearly met but a full Streamlit rerun can still measure 315–500 ms. Further gains would require progressively moving independent controls into fragments, which should be done page-by-page with visual regression testing.
4. External fonts and player headshots remain browser-network dependencies. Browser caching mitigates repeat visits, but first visits depend on third-party response time.
5. A Render cold start can exceed the under-3-second target even when application execution does not. Always-on behavior beyond the current plan would require approval.

## Hosting conclusion

Keep Render Starter for now. The optimized local working set leaves materially more headroom than the current production graph suggests, and the application has fewer than 10 users. Do not upgrade solely on the basis of the synthetic test. Reconsider only if the optimized deployment still sustains above roughly 85% memory, records out-of-memory restarts, or regularly receives several simultaneous cold sessions.
