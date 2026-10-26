#!/bin/bash
# After a package is installed (inside a container): the dependencies import, the launcher and
# desktop entry exist, and the real viewer opens a document in a headless compositor without
# a traceback. Needs cage. Run by scripts/package-check.sh.
set -euo pipefail

python3 -c "
import gi, markdown, nh3, pygments, pymdownx
gi.require_version('Gtk', '4.0'); gi.require_version('WebKit', '6.0')
from gi.repository import Gtk, WebKit
print('imports ok')"
test -x /usr/bin/zeile
test -f /usr/share/applications/zeile.desktop
test -f /usr/share/zeile/icons/hicolor/512x512/apps/zeile.png
test -f /usr/share/zeile/locale/de/LC_MESSAGES/zeile.mo

HOME="$(mktemp -d)"
export HOME
XDG_RUNTIME_DIR="$(mktemp -d)"
export XDG_RUNTIME_DIR
chmod 700 "$XDG_RUNTIME_DIR"
# shellcheck disable=SC2016  # backticks are markdown, not command substitution
printf '# Smoke\n\n```python\nprint(1)\n```\n' > "$HOME/smoke.md"

# WebKit's sandbox needs user namespaces, which containers lack; the document is our fixture.
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1
export WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman
status=0
timeout 20 cage -d -- /usr/bin/zeile "$HOME/smoke.md" > "$HOME/run.log" 2>&1 || status=$?
# 124 = still running when the timeout hit, i.e. the viewer stayed up.
if [[ "$status" -ne 124 ]] || grep -q Traceback "$HOME/run.log"; then
    cat "$HOME/run.log" >&2
    printf 'smoke FAILED (exit %s)\n' "$status" >&2
    exit 1
fi
grep -q '"intro_seen": "true"' "$HOME/.config/zeile/settings.json"
printf 'smoke OK\n'
