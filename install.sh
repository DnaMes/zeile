#!/bin/bash
# Install mdview: launcher in ~/.local/bin, desktop entry, and mime association.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SRC_DIR
readonly BIN_DIR="$HOME/.local/bin"
readonly APP_DIR="$HOME/.local/share/applications"
readonly ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

# Launcher pins /usr/bin/python3: brew/mise pythons have no gi bindings.
cat > "$BIN_DIR/mdview" <<EOF
#!/bin/bash
exec /usr/bin/python3 "$SRC_DIR/mdview.py" "\$@"
EOF
chmod +x "$BIN_DIR/mdview"

install -m 644 "$SRC_DIR/assets/mdview.svg" "$ICON_DIR/mdview.svg"

cat > "$APP_DIR/mdview.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=mdview
GenericName=Markdown Viewer
Comment=View markdown files
Exec=$BIN_DIR/mdview %f
Icon=mdview
Terminal=false
Categories=Utility;TextEditor;Viewer;
MimeType=text/markdown;text/x-markdown;
StartupWMClass=com.erdlabs.mdview
NoDisplay=false
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
xdg-mime default mdview.desktop text/markdown text/x-markdown

printf 'installed: %s\n' "$BIN_DIR/mdview"
handler="$(xdg-mime query default text/markdown)"
printf 'default handler: %s\n' "$handler"
