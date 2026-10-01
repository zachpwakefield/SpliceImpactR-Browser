# macOS / Dock launcher

The launcher opens SpliceImpactR Browser without a Terminal window. Human v45
is the default; any other installed dataset, including mouse M34, is available
in **Genome annotation**.

## Requirements

Complete the [main installation](../README.md#install) first. The launcher needs
macOS 12+ and Apple's Xcode Command Line Tools. If needed, run
`xcode-select --install` and finish that installation before continuing.

## Install locally

From the repository root:

```bash
./scripts/setup_local.sh --no-start
./desktop_app/install_macos_app.sh human-gencode-v45
open "$HOME/Applications/SpliceImpactR Browser.app"
```

If setup is already complete, skip its command. Drag the app from your home
**Applications** folder into the Dock, or choose **Options → Keep in Dock**
while it is running. The installer also adds a Desktop link; it does not change
Dock settings.

Use **Open Browser** to reopen the browser and **Stop & Quit** to close the
launcher and its server. A matching server that was already running is reused
and left alone. The normal port is `8765`; if occupied, the launcher uses a free
local port. Saved browser workspaces are separate for each port.

## Add mouse

Quit the launcher, prepare M34, then reinstall with human still selected as
the default:

```bash
./scripts/setup_local.sh --dataset mouse-gencode-m34 --no-start
./desktop_app/install_macos_app.sh human-gencode-v45
```

The installer includes all locally built, validated datasets. Reinstall after
adding a dataset or optional PPI context. To make mouse the startup default
instead, pass `mouse-gencode-m34` to the installer.

## Update or diagnose

Quit the launcher before updating. For a source update that does not change
annotation inputs:

```bash
git pull
.venv/bin/python -m pip install --requirement requirements.lock
cd frontend
npx --yes pnpm@11.7.0 install --frozen-lockfile
npx --yes pnpm@11.7.0 run build
cd ..
./desktop_app/install_macos_app.sh human-gencode-v45
```

Open the installed app again. If the release changes data preparation, rerun
the relevant setup command before reinstalling.

For a startup check, run this in a normal Mac terminal:

```bash
"$HOME/Applications/SpliceImpactR Browser.app/Contents/MacOS/SpliceImpactRBrowserLauncher" --self-test
```

Success prints a JSON receipt and exits without opening a browser. Logs are at
`~/Library/Logs/Transcript Browser/server.log`. The app keeps its packaged code
and data under `~/Library/Application Support/Transcript Browser/Runtime`, but
still uses the Python installation it was built with; keep that Python available.

Share the GitHub source, not the generated `.app`, runtime ZIP/manifests, or
private caches. Each user should build their own local launcher.
