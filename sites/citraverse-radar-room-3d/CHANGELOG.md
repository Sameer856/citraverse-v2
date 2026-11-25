# Dashboard versions

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
