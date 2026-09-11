#!/bin/bash
# Install zeile: launcher in ~/.local/bin, desktop entry, and mime association.
# Run with --uninstall to remove everything this script wrote.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SRC_DIR
readonly BIN_DIR="$HOME/.local/bin"
readonly APP_DIR="$HOME/.local/share/applications"
readonly ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
readonly LAUNCHER="$BIN_DIR/zeile"
readonly DESKTOP_FILE="$APP_DIR/zeile.desktop"
readonly ICON_FILE="$ICON_DIR/zeile.svg"

uninstall() {
    rm -f "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE"
    update-desktop-database "$APP_DIR" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    printf 'uninstalled: %s %s %s\n' "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE"
    printf 'note: text/markdown default handler is left as-is -- reassign it\n'
    printf 'yourself (xdg-mime default <app>.desktop text/markdown) if needed.\n'
    exit 0
}

if [[ "${1:-}" == "--uninstall" ]]; then
    uninstall
fi

# Fails loudly and specifically, not with a cryptic ImportError only when
# the user finally double-clicks a .md file. Each check names the exact
# pacman package so the fix is a single copy-pasteable line, not a search.
check_dependency() {
    local description="$1" pacman_package="$2"
    shift 2
    if ! "$@" >/dev/null 2>&1; then
        printf 'missing dependency: %s\n' "$description" >&2
        printf '  fix: sudo pacman -S --needed %s\n' "$pacman_package" >&2
        exit 1
    fi
}

check_dependency "python3" "python" command -v python3
check_dependency "GTK4 GObject bindings (python-gobject)" "python-gobject" \
    /usr/bin/python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk"
check_dependency "WebKitGTK 6.0 (webkitgtk-6.0)" "webkitgtk-6.0" \
    /usr/bin/python3 -c "import gi; gi.require_version('WebKit', '6.0'); from gi.repository import WebKit"
check_dependency "python-markdown" "python-markdown" /usr/bin/python3 -c "import markdown; markdown.markdown"
check_dependency "python-nh3" "python-nh3" /usr/bin/python3 -c "import nh3; nh3.clean"
check_dependency "python-pymdown-extensions" "python-pymdown-extensions" \
    /usr/bin/python3 -c "import pymdownx.tasklist"

mkdir -p "$BIN_DIR" "$APP_DIR" "$ICON_DIR"

# Compile translations (po/*.po -> locale/<lang>/LC_MESSAGES/zeile.mo), if
# msgfmt is available. The repo ships a pre-compiled de.po result for users
# without gettext installed; this just keeps it current after an edit.
if command -v msgfmt >/dev/null 2>&1; then
    for po_file in "$SRC_DIR"/po/*.po; do
        [[ -e "$po_file" ]] || continue
        lang="$(basename "$po_file" .po)"
        mo_dir="$SRC_DIR/locale/$lang/LC_MESSAGES"
        mkdir -p "$mo_dir"
        msgfmt "$po_file" -o "$mo_dir/zeile.mo"
    done
fi

# Launcher pins /usr/bin/python3: brew/mise pythons have no gi bindings.
# Checks its own target exists first -- a moved or deleted repo directory
# otherwise fails as a bare "No such file or directory" from python3 itself,
# which does not say which file it means.
cat > "$LAUNCHER" <<EOF
#!/bin/bash
SRC="$SRC_DIR/zeile.py"
if [[ ! -f "\$SRC" ]]; then
    printf 'zeile: %s no longer exists (did the repo move? re-run install.sh)\n' "\$SRC" >&2
    exit 1
fi
exec /usr/bin/python3 "\$SRC" "\$@"
EOF
chmod +x "$LAUNCHER"

install -m 644 "$SRC_DIR/assets/zeile.svg" "$ICON_FILE"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=zeile
GenericName=Markdown Viewer
Comment=View markdown files
Exec=$LAUNCHER %f
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

printf 'installed: %s\n' "$LAUNCHER"
handler="$(xdg-mime query default text/markdown)"
printf 'default handler: %s\n' "$handler"
