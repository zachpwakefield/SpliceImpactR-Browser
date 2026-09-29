#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SOURCE_DIR="$ROOT/desktop_app"
BUILT_APP="$SOURCE_DIR/dist/Transcript Browser.app"
INSTALLED_APP="$HOME/Applications/Transcript Browser.app"
DESKTOP_APP="$HOME/Desktop/Transcript Browser.app"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This optional installer requires macOS. Use ./run_local.sh on Linux/WSL2." >&2
  exit 2
fi
# Do not silently delete a user's unrelated Desktop item or follow an app
# symlink during an update. Quit an existing launcher before reinstalling.
if [[ -L "$INSTALLED_APP" ]] || { [[ -e "$INSTALLED_APP" ]] && [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$INSTALLED_APP/Contents/Info.plist" 2>/dev/null || true)" != "local.transcript-browser.launcher" ]]; }; then
  echo "An unrelated item occupies $INSTALLED_APP; move it before installing." >&2
  exit 2
fi
if [[ -L "$DESKTOP_APP" ]]; then
  if [[ "$(readlink "$DESKTOP_APP")" != "$INSTALLED_APP" ]]; then
    echo "An unrelated Desktop link exists; move it before installing." >&2
    exit 2
  fi
elif [[ -e "$DESKTOP_APP" ]]; then
  echo "A Desktop item already uses this name; move it before installing (it will not be deleted)." >&2
  exit 2
fi

"$SOURCE_DIR/build_macos_app.sh"

MANIFEST="$BUILT_APP/Contents/Resources/Runtime-manifest.json"
ARCHIVE="$BUILT_APP/Contents/Resources/Runtime.zip"
RUNTIME_VERSION="$("$ROOT/.venv/bin/python" -B -c \
  'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["runtimeVersion"])' \
  "$MANIFEST")"
RUNTIME_ROOT="$HOME/Library/Application Support/Transcript Browser/Runtime"
CACHED_RUNTIME="$RUNTIME_ROOT/$RUNTIME_VERSION"
STAGING_RUNTIME=""
STAGED_APP=""
STAGED_APP_ROOT=""
PREVIOUS_APP=""

cleanup() {
  if [[ -n "$STAGING_RUNTIME" ]]; then rm -rf "$STAGING_RUNTIME"; fi
  if [[ -n "$STAGED_APP_ROOT" ]]; then rm -rf "$STAGED_APP_ROOT"; fi
  if [[ -n "$PREVIOUS_APP" ]] && [[ -e "$PREVIOUS_APP" ]] && [[ ! -e "$INSTALLED_APP" ]]; then
    mv "$PREVIOUS_APP" "$INSTALLED_APP"
  fi
}
trap cleanup EXIT

mkdir -p "$RUNTIME_ROOT"
if [[ -e "$CACHED_RUNTIME" ]] || [[ -L "$CACHED_RUNTIME" ]]; then
  "$ROOT/.venv/bin/python" -B "$SOURCE_DIR/materialize_runtime_data.py" --verify-cached "$CACHED_RUNTIME"
else
  STAGING_RUNTIME="$(mktemp -d "$RUNTIME_ROOT/.install.XXXXXX")"
  /usr/bin/ditto -x -k "$ARCHIVE" "$STAGING_RUNTIME"
  "$ROOT/.venv/bin/python" -B "$SOURCE_DIR/materialize_runtime_data.py" \
    "$ROOT" "$STAGING_RUNTIME" "$CACHED_RUNTIME"
fi
mkdir -p "$HOME/Applications" "$HOME/Desktop"
STAGED_APP_ROOT="$(mktemp -d "$HOME/Applications/.transcript-browser-install.XXXXXX")"
STAGED_APP="$STAGED_APP_ROOT/Transcript Browser.app"
ditto --norsrc --noextattr "$BUILT_APP" "$STAGED_APP"
xattr -cr "$STAGED_APP"
codesign --verify --deep --strict "$STAGED_APP"
if [[ -e "$INSTALLED_APP" ]]; then
  PREVIOUS_APP="$HOME/Applications/.Transcript Browser.previous-$$.app"
  mv "$INSTALLED_APP" "$PREVIOUS_APP"
fi
mv "$STAGED_APP" "$INSTALLED_APP"
rmdir "$STAGED_APP_ROOT"
STAGED_APP=""
STAGED_APP_ROOT=""
if [[ -n "$PREVIOUS_APP" ]]; then
  rm -rf "$PREVIOUS_APP"
  PREVIOUS_APP=""
fi
if [[ ! -L "$DESKTOP_APP" ]]; then
  ln -s "$INSTALLED_APP" "$DESKTOP_APP"
fi

echo "Installed $INSTALLED_APP"
echo "Created clickable Desktop app $DESKTOP_APP"
echo "Prepared private runtime $CACHED_RUNTIME"
