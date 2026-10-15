# Releasing

HACS installs this integration from `anker_prime_charger.zip`, a release asset holding the
contents of `custom_components/anker_prime_charger` (`hacs.json`: `"zip_release": true`,
`"filename": "anker_prime_charger.zip"`). HACS's **Downloads** figure is that asset's download
count on the current release, so it restarts at zero with every release.

## Steps

1. Run the tests and `ruff check` / `ruff format --check` (CI runs them too, with hassfest and the
   HACS check).
2. Bump `version` in `custom_components/anker_prime_charger/manifest.json`
   ([semantic versioning](https://semver.org/): a new feature bumps the minor version, a fix the
   patch).
3. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and start a new empty
   `## [Unreleased]` above it. If `hacs.json`'s minimum Home Assistant version changed, say so.
4. Check the zip before tagging: `python scripts/release-zip.py --tag vX.Y.Z --output <temp>.zip`
   (builds it from `HEAD`, checks it, and checks the manifest version against the tag). Delete
   the zip afterwards.
5. Commit, then create an annotated tag and push both:
   `git tag -a vX.Y.Z -m "vX.Y.Z"`, `git push origin main`, `git push origin vX.Y.Z`.
6. Publish a GitHub release from the tag, with the CHANGELOG section as notes:
   `gh release create vX.Y.Z --title vX.Y.Z --notes-file <file> --verify-tag --latest`.
7. The **Release** workflow (`.github/workflows/release.yaml`) then builds the zip with the same
   script and attaches it to the release, usually within a minute. Until it is attached, HACS
   can't install that release.

## Rules

- **Never rename the zip** without changing `hacs.json` `filename` in the same release: HACS looks
  for an asset with exactly that name. `scripts/release-zip.py` fails if they differ.
- The workflow must exist in the **tagged commit**: GitHub runs the workflow file as it is at the
  release's tag.
- The zip is built with `git archive` from tracked files only, so anything the integration needs
  at runtime must be committed. Local files (`__pycache__`, the library's `authcache` login
  cache) never get in.

## Check a release

- `gh release view vX.Y.Z --json assets` lists `anker_prime_charger.zip` and its download count.
- The workflow run's summary shows the attached size.
- If the run failed, fix the cause and re-run it from the Actions tab: the upload uses
  `--clobber`, so it replaces a partial asset.
