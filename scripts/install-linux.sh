#!/usr/bin/env bash
# Install Quire for the current user: a venv under ~/.local/share/quire-app,
# a `quire` command in ~/.local/bin, and a desktop menu entry.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
prefix="${XDG_DATA_HOME:-$HOME/.local/share}"
app="$prefix/quire-app"

python3 -m venv "$app" 2>/dev/null || python3 -m venv --without-pip "$app"
if [ ! -x "$app/bin/pip" ]; then
    curl -sSfL https://bootstrap.pypa.io/get-pip.py | "$app/bin/python" - -q
fi
"$app/bin/pip" install -q --upgrade "$here"

app_id="io.github.quezka.Quire"
mkdir -p "$HOME/.local/bin" "$prefix/applications" "$prefix/metainfo" \
    "$prefix/icons/hicolor/scalable/apps"
ln -sf "$app/bin/quire" "$HOME/.local/bin/quire"
cp "$here/quire/assets/icon.svg" "$prefix/icons/hicolor/scalable/apps/$app_id.svg"
cp "$here/packaging/$app_id.desktop" "$prefix/applications/$app_id.desktop"
cp "$here/packaging/$app_id.metainfo.xml" "$prefix/metainfo/$app_id.metainfo.xml"
# Entries from installs before the app id was introduced.
rm -f "$prefix/applications/quire.desktop" "$prefix/icons/hicolor/scalable/apps/quire.svg"
update-desktop-database "$prefix/applications" 2>/dev/null || true
echo "Installed. Launch Quire from your app menu or run: quire"
