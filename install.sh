#!/bin/bash
# Install zeile: launcher in ~/.local/bin, desktop entry, and mime association.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SRC_DIR
readonly BIN_DIR="$HOME/.local/bin"
readonly APP_DIR="$HOME/.local/share/applications"
readonly ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

# Launcher pins /usr/bin/python3: brew/mise pythons have no gi bindings.
cat > "$BIN_DIR/zeile" <<EOF
#!/bin/bash
exec /usr/bin/python3 "$SRC_DIR/zeile.py" "\$@"
EOF
chmod +x "$BIN_DIR/zeile"

install -m 644 "$SRC_DIR/assets/zeile.svg" "$ICON_DIR/zeile.svg"

cat > "$APP_DIR/zeile.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=zeile
GenericName=Markdown Viewer
Comment=View markdown files
Exec=$BIN_DIR/zeile %f
Icon=zeile
Terminal=false
Categories=Utility;TextEditor;Viewer;
MimeType=text/markdown;text/x-markdown;
StartupWMClass=com.erdlabs.zeile
NoDisplay=false
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
xdg-mime default zeile.desktop text/markdown text/x-markdown

printf 'installed: %s\n' "$BIN_DIR/zeile"
handler="$(xdg-mime query default text/markdown)"
printf 'default handler: %s\n' "$handler"
