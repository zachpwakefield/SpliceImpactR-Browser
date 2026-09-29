# Optional macOS / Dock launcher

`Transcript Browser.app` starts the verified local browser without a Terminal
window. It opens the default browser only after both the annotation build and
packaged frontend match. **Open Browser** reopens it; **Stop & Quit** stops only
the server this launcher started. An already-running matching server may be
reused and is never terminated by the launcher.

The checkout can have any name and location. There is no required Desktop
project folder or workstation-specific annotation hash.

## Install locally

First follow the repository [setup instructions](../README.md#requirements)
and prepare the full annotation package:

```bash
./scripts/setup_local.sh --no-start
```

The native launcher additionally needs Apple's Xcode Command Line Tools. If
they are absent, install them with `xcode-select --install`, complete that
installation, then run from the repository root:

```bash
./desktop_app/install_macos_app.sh
open "$HOME/Applications/Transcript Browser.app"
```

Drag the installed application from your home **Applications** folder to the
Dock, or use **Options → Keep in Dock** after opening it. The installer also
creates a Desktop link; it does not edit your Dock settings.

The default port is `8765`. If that port belongs to a different service/build,
the launcher chooses a free IPv4 loopback port and shows its URL. It never kills
an unrelated process. Browser notes and saved workspaces are origin-specific,
so a different port has separate local browser storage.

## What is installed

- Signed bundle: `~/Applications/Transcript Browser.app`.
- Desktop link: `~/Desktop/Transcript Browser.app`.
- Versioned code/data: `~/Library/Application Support/Transcript Browser/Runtime`.
- Server log: `~/Library/Logs/Transcript Browser/server.log` (cleared on the next launch if over 5 MB).

Backend code, locked Python packages, production frontend assets, and portable
metadata are packaged into a ZIP and installed privately. The immutable SQLite
database and any optional reference artifacts are cloned separately. On APFS,
copy-on-write clones initially share storage blocks; on a filesystem that does
not support cloning, ordinary copies are used and require additional space.
All cloned bytes are SHA-256 checked before publication. Optional reference
links and inode/time receipts point to the final private paths, never staging.
The original annotation package is not modified.

The Python interpreter itself is **not** embedded. Keep the Python installation
used to build the app available: its location and version are recorded in the
private runtime manifest. Moving/removing that Python installation requires
rebuilding/reinstalling the launcher. R, Node, and the source checkout are not
looked up at browser launch; the app uses its installed code/data and the
recorded Python interpreter.

This is a locally built, ad-hoc-signed application, not a notarized distributable
binary. **Do not upload the generated `.app`, `Runtime.zip`, runtime manifests,
or private caches to GitHub or send them as releases.** They contain local
interpreter/source paths and installed third-party binaries. Share the public
source and let each person build their own installation instead.

## Update or diagnose

Quit the launcher before updating source/data or reinstalling. After pulling
source changes, rebuild the frontend and any changed scientific inputs, then
rerun the installer. A new runtime identity gets a new cache directory; existing
verified caches are checked and reused, not silently overwritten. Unrelated
Desktop items or app bundles with the same name are refused, not deleted.

For a bundle-only build:

```bash
./desktop_app/build_macos_app.sh
```

Its default output is the ignored `desktop_app/dist/Transcript Browser.app`.
Installation is still required to prepare the private data. To check an
installed launcher without opening a browser or showing a window:

```bash
"$HOME/Applications/Transcript Browser.app/Contents/MacOS/TranscriptBrowserLauncher" --self-test
```

Success prints a JSON receipt and exits zero. Any server started by the test is
stopped; an existing matching server is left alone. This verifies packaging,
build/frontend identity, loopback readiness, and owned-process shutdown. It
does not substitute for visual/browser interaction review.

For a sandboxed installation replay, use a new temporary home rather than
modifying a real installed app:

```bash
TEST_HOME="$(mktemp -d "${TMPDIR:-/tmp}/transcript-browser-macos-test.XXXXXX")"
HOME="$TEST_HOME" ./desktop_app/install_macos_app.sh
HOME="$TEST_HOME" "$TEST_HOME/Applications/Transcript Browser.app/Contents/MacOS/TranscriptBrowserLauncher" \
  --self-test --state-root "$TEST_HOME/Library/Application Support/Transcript Browser"
```

Keep that temporary directory until reviewing the receipt/logs, then remove
only that directory. The launcher targets macOS 12+ and the build script selects
the host's `arm64` or `x86_64` architecture. Full isolated packaging/startup was
tested on Apple Silicon macOS 26.0.1; Intel installation and actual Dock/Finder
interaction remain separate human checks. CI compiles/signs the native source
on a [GitHub macOS 15 runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
but does not download the full scientific catalog for that job.
