#!/bin/bash
# Stage a system-wide zeile install into DESTDIR. Shared by the Arch, deb and rpm builds so
# the layout is defined once.   packaging/stage.sh DESTDIR [PREFIX=/usr]
set -euo pipefail

readonly DESTDIR="${1:?usage: stage.sh DESTDIR [PREFIX]}"
readonly PREFIX="${2:-/usr}"
cd "$(dirname "$0")/.."

readonly APP="$DESTDIR$PREFIX/share/zeile"

# read_asset() resolves assets relative to zeile.py, so assets/, locale/ and the
# start-sequence logo (launch_asset_path) must stay next to the script.
install -d "$APP"
install -m 644 zeile.py code_lang.py markdown_ext.py mermaid_render.py "$APP/"
cp -r assets "$APP/assets"
install -Dm 644 icons/hicolor/512x512/apps/zeile.png "$APP/icons/hicolor/512x512/apps/zeile.png"

# Compile translations when msgfmt is available; otherwise ship the committed catalogues.
install -d "$APP/locale"
if command -v msgfmt >/dev/null 2>&1; then
    for po_file in po/*.po; do
        lang="$(basename "$po_file" .po)"
        install -d "$APP/locale/$lang/LC_MESSAGES"
        msgfmt "$po_file" -o "$APP/locale/$lang/LC_MESSAGES/zeile.mo"
    done
else
    cp -r locale/. "$APP/locale/"
fi

# A package never touches ~/.local and never claims the text/markdown default handler;
# users opt in with: xdg-mime default zeile.desktop text/markdown text/x-markdown
install -d "$DESTDIR$PREFIX/bin"
printf '#!/bin/bash\nexec /usr/bin/python3 %s/share/zeile/zeile.py "$@"\n' "$PREFIX" \
    > "$DESTDIR$PREFIX/bin/zeile"
chmod 755 "$DESTDIR$PREFIX/bin/zeile"

install -d "$DESTDIR$PREFIX/share/applications"
cat > "$DESTDIR$PREFIX/share/applications/zeile.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=zeile
GenericName=Markdown Viewer
GenericName[de]=Markdown-Betrachter
Comment=View markdown files
Comment[de]=Markdown-Dateien anzeigen
Exec=$PREFIX/bin/zeile %f
Icon=zeile
Terminal=false
Categories=Utility;TextEditor;Viewer;
MimeType=text/markdown;text/x-markdown;
StartupWMClass=com.erdlabs.zeile
DESKTOP

for size in 16 24 32 48 64 128 256 512; do
    install -Dm 644 "icons/hicolor/${size}x${size}/apps/zeile.png" \
        "$DESTDIR$PREFIX/share/icons/hicolor/${size}x${size}/apps/zeile.png"
done
install -Dm 644 icons/hicolor/scalable/apps/zeile.svg \
    "$DESTDIR$PREFIX/share/icons/hicolor/scalable/apps/zeile.svg"

# Man pages and shell completions (mode 644; leave ungzipped).
install -Dm 644 man/zeile.1 "$DESTDIR$PREFIX/share/man/man1/zeile.1"
install -Dm 644 man/de/zeile.1 "$DESTDIR$PREFIX/share/man/de/man1/zeile.1"
install -Dm 644 completions/zeile.bash \
    "$DESTDIR$PREFIX/share/bash-completion/completions/zeile"
install -Dm 644 completions/zeile.zsh \
    "$DESTDIR$PREFIX/share/zsh/site-functions/_zeile"
install -Dm 644 completions/zeile.fish \
    "$DESTDIR$PREFIX/share/fish/vendor_completions.d/zeile.fish"
