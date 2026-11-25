# Dashboard version control

The user requests a recoverable GitHub checkpoint for each logical dashboard change.

- Before editing, confirm the previous working dashboard is backed up in `Sameer856/citraverse-v2`, branch `codex/radar-dashboard-room`, under `sites/citraverse-radar-room-3d`.
- Keep feature changes in separate commits. Update CHANGELOG.md with validation and the previous rollback version. Tag tested milestones `dashboard-vX.Y.Z` without moving an existing tag.
- Push the exact published source snapshot to that GitHub branch. Preserve the separate Sites source repository and its publishing workflow; do not change its remote to GitHub.
- Never include `.dev.vars`, environment credentials, local pairing files, generated archives, node_modules or build output. Copy tracked source only when mirroring to GitHub.
- Revert using a new commit and redeploy it. Do not reset or force-push shared history. A Git revert alone does not change the hosted dashboard.
