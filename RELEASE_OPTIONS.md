Release-Optionen
=================

Diese Datei beschreibt die Eingabeoptionen des CI-Workflows `.github/workflows/release-docker.yml`.

Inputs (workflow_dispatch)
- `bump` (choice)
  - `patch` (Standard): Erhöht nur die Patch-Version (vX.Y.Z -> vX.Y.Z+1).
  - `minor`: Erhöht die Minor-Version und setzt Patch auf 0 (vX.Y.Z -> vX.Y+1.0).
  - `major`: Erhöht die Major-Version und setzt Minor/Patch auf 0 (vX.Y.Z -> vX+1.0.0).
  - `development`: Erzeugt einen Development-Release mit Suffix `-dev` (z. B. `v3.1.4-dev`).

- `push_dev` (choice, optional)
  - `false` (Standard): Bei `bump=development` wird das `:dev`-Image NICHT automatisch an GHCR gepusht.
  - `true`: Bei `bump=development` wird zusätzlich das Image `ghcr.io/aiirondev/legendary-octo-garbanzo:dev` gepusht.

Verhalten/Anmerkungen
- Development releases werden als GitHub Release erzeugt und als `prerelease` markiert, damit sie nicht automatisch von normalen Update‑Flows genutzt werden.
- Es gibt pro Release genau einen Release‑Eintrag (für Dev‑Releases mit `-dev` Suffix). Es wird kein separates `inventarsystem-image-dev.tar.gz` mehr erzeugt; das Update/Deployment erfolgt über den Release‑Tag / Image‑Tag.
- `update.sh` unterstützt weiterhin `dev`/`development`-Modus und akzeptiert nun auch explizite Release‑Tags wie `v3.1.4-dev`.

Beispiele
- Patch-Release (manuell):
  - GitHub UI: Run workflow → `bump=patch`
  - CLI mit `gh`:
    gh workflow run release-docker.yml --repo AIIrondev/legendary-octo-garbanzo --field bump=patch

- Development prerelease (ohne Push des :dev Images):
  - GitHub UI: Run workflow → `bump=development` (leave `push_dev=false`)
  - Ergebnis: Release `vX.Y.Z-dev` als prerelease, Image wird nicht automatisch als `:dev` gepusht.

- Development prerelease + push des :dev Images:
  - GitHub UI: Run workflow → `bump=development`, `push_dev=true`
  - CLI Beispiel:
    gh workflow run release-docker.yml --repo AIIrondev/legendary-octo-garbanzo --field bump=development --field push_dev=true

Empfehlung
- Verwende `bump=development` für experimentelle/early releases; Nutzer müssen explizit `./update.sh vX.Y.Z-dev` ausführen, um auf diese Version zu upgraden.
