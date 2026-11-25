# Dashboard versions

## dashboard-v1.2.2 — Retain strict continuity after interrupted field comparison

- Keep the experimental 200 ms bed-candidate view and its adjustable grouping controls.
- Restore strict tracker clearing on every original continuity gap. The bounded display policy remains an offline-tested variant; the interrupted overnight comparison did not provide enough eligible data to select it on the retained hardware profile.
- Hardware restarts during field testing do not establish a software or radar-profile cause. No fall-detector thresholds or physical mounting values change.
- Validation: existing bed, stream and fall tests, TypeScript, production build and live local preview.
- Rollback: `dashboard-v1.2.0` has the same strict-continuity bed view; `dashboard-v1.1.0` restores the previous bed layout without the new bed-candidate method.

## dashboard-v1.2.1 — Bounded display continuity

- Keep display tracks through at most three missing frames within 200 ms of source time and 500 ms of receive time when fresh evidence supports them.
- Stale data, longer gaps and resets still clear display state. Every original gap remains visible in the continuity counter.
- Fall-state invalidation remains strict for every original continuity gap; its detector and thresholds are unchanged.
- Validation includes protocol/clock bounds, supported-box expiry and exact recorded-frame comparisons. Numerical overnight results remain unverified person-count proxies.
- Rollback: `dashboard-v1.2.0` (experimental bed boxes before this display-only fix).

## dashboard-v1.2.0 — Experimental bed candidates

- Bed-aligned candidate boxes use separate across-bed and along-bed distances, a short source-frame evidence window, and distinct-position support. They never force two people.
- Candidate settings and the original whole-room box view are available without reflashing; preferences persist in the browser.
- Fresh candidates are distinguished from weak historical evidence. Gaps, stale frames and geometry changes clear accumulated evidence.
- Box tops and observed spans remain approximate radar measurements, not full body height or verified human identity. The single-person fall prototype is unchanged.
- Default method was frozen from development recordings before prospective overnight validation: 0.15 m across, 1 m along, 200 ms, three distinct positions. Detailed overnight results are separate from functional validation.
- Validation: TypeScript, 35 protocol/mount/bed/people/fall checks, exact runtime replay and live GCP browser preview with persistence and original-view fallback. Production build is recorded with the published source.
- Rollback: `dashboard-v1.1.0` (bed reference with original room boxes).

## dashboard-v1.1.0 — Bed room reference

- Bed beside the right wall, head at the far-right corner and foot toward the near-right corner.
- Adjustable width, length, mattress height and wall gap; show/hide and browser-local persistence.
- Bed fits inside room bounds and is visual only. Radar points and fall thresholds remain unchanged.
- Validation: TypeScript, radar/mount/people/bed checks, production build and live browser preview.
- Rollback: `dashboard-v1.0.0` (working dashboard before the bed).

## dashboard-v1.0.0 — Stable baseline

- Live GCP radar, field tuning controls, corrected 3D mounting, person candidate boxes and estimated height.
- Backed up before the bed change. Sites source: `8ac03e6708d291796e01b20ef4c20b02dedee4b6`.
- GitHub baseline commit: `2e87d82`.

## Recovering a version

Use branch `codex/radar-dashboard-room` in `Sameer856/citraverse-v2`.
Each feature is a separate commit. Use GitHub's revert workflow or `git revert <feature-commit>` to create a new undo commit; preserve the existing history. Validate and redeploy the reverted dashboard through the Sites publishing workflow. Do not force-push or reset the shared branch. Tags identify source snapshots; checking out a tag alone does not redeploy the website.

Local room/mount/bed preferences are stored in each browser. Credentials are excluded and must be supplied separately when running the project.
