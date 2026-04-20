# Third-Party Notices

DocForge Local (`docforge-local`) depends on third-party open-source packages.

For first release review, package/license metadata was collected locally using:

```bash
uv run python scripts/license_inventory.py
```

See `docs/open_source_audit.md` for the auditable inventory and compatibility notes.

## Naming note for v0.1.0

- User-facing name: **DocForge Local** / `docforge-local`
- Internal Python package name retained for compatibility: `repo_autodocs`

## Attribution scope for this repository

- This repository does **not** currently vendor/copy third-party source code into `src/`.
- This repository does **not** currently bundle third-party binary/font/media assets requiring separate attribution files.
- Runtime behavior depends on installed third-party Python packages, each with their own licenses.

If future releases vendor third-party code or bundle assets, this file should be expanded with explicit component-level attributions.
