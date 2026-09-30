#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SOURCE_DIR="$ROOT/desktop_app"
OUTPUT_APP="${1:-$SOURCE_DIR/dist/Transcript Browser.app}"
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The optional desktop launcher can only be built on macOS. Use ./run_local.sh on Linux/WSL2." >&2
  exit 2
fi
if ! xcrun --find swiftc >/dev/null 2>&1; then
  echo "Install Apple's Xcode Command Line Tools (xcode-select --install), then retry." >&2
  exit 2
fi
if [[ ! -x "$ROOT/.venv/bin/python" ]] || [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "First complete ./scripts/setup_local.sh --no-start in this checkout." >&2
  exit 2
fi
case "$OUTPUT_APP" in
  *.app) ;;
  *) echo "The output must be an .app bundle path." >&2; exit 2 ;;
esac
if [[ -L "$OUTPUT_APP" ]] || { [[ -e "$OUTPUT_APP" ]] && [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$OUTPUT_APP/Contents/Info.plist" 2>/dev/null || true)" != "local.transcript-browser.launcher" ]]; }; then
  echo "Refusing to replace an unrelated file or bundle at the output path." >&2
  exit 2
fi
ARCH="$(uname -m)"
case "$ARCH" in
  arm64|x86_64) ;;
  *) echo "Unsupported Mac architecture: $ARCH" >&2; exit 2 ;;
esac
STAGE="$(mktemp -d /private/tmp/transcript-browser-launcher.XXXXXX)"
STAGED_APP="$STAGE/Transcript Browser.app"
CONTENTS="$STAGED_APP/Contents"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources" "$STAGE/ModuleCache"

xcrun swiftc \
  -O \
  -target "$ARCH-apple-macosx12.0" \
  -module-cache-path "$STAGE/ModuleCache" \
  -framework AppKit \
  "$SOURCE_DIR/TranscriptBrowserLauncher.swift" \
  -o "$CONTENTS/MacOS/TranscriptBrowserLauncher"

cp "$SOURCE_DIR/Info.plist" "$CONTENTS/Info.plist"
cp "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$CONTENTS/Resources/"
"$ROOT/.venv/bin/python" -B "$SOURCE_DIR/make_icon.py" "$CONTENTS/Resources/AppIcon.icns"
"$ROOT/.venv/bin/python" -B "$SOURCE_DIR/package_runtime.py" "$ROOT" "$CONTENTS/Resources/Runtime.zip"
chmod +x "$CONTENTS/MacOS/TranscriptBrowserLauncher"

plutil -lint "$CONTENTS/Info.plist"
xattr -cr "$STAGED_APP"
codesign --force --deep --sign - "$STAGED_APP"
codesign --verify --deep --strict "$STAGED_APP"

mkdir -p "$(dirname -- "$OUTPUT_APP")"
if [[ -e "$OUTPUT_APP" ]]; then rm -rf "$OUTPUT_APP"; fi
ditto --norsrc --noextattr "$STAGED_APP" "$OUTPUT_APP"
verified=0
for _ in 1 2 3 4 5; do
  xattr -d com.apple.FinderInfo "$OUTPUT_APP" 2>/dev/null || :
  xattr -d 'com.apple.fileprovider.fpfs#P' "$OUTPUT_APP" 2>/dev/null || :
  if codesign --verify --deep --strict "$OUTPUT_APP" 2>/dev/null; then
    verified=1
    break
  fi
done
if [[ "$verified" != "1" ]]; then
  echo "Copied app could not be verified after clearing Desktop metadata." >&2
  exit 1
fi

echo "Built $OUTPUT_APP"
