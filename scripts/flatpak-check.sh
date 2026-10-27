#!/bin/bash
# Prove what the Flatpak sandbox really does: deps import, read-only home,
# network isolation, and sibling-image rendering under headless cage.
#   scripts/flatpak-check.sh
set -euo pipefail

script_dir="${BASH_SOURCE[0]%/*}"
[[ "$script_dir" == "${BASH_SOURCE[0]}" ]] && script_dir=.
cd "$script_dir/.."
REPO="$(pwd)"
readonly REPO

MISSING=()
for cmd in flatpak flatpak-builder cage; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        MISSING+=("$cmd")
    fi
done
if ((${#MISSING[@]} > 0)); then
    printf 'flatpak-check requires flatpak, flatpak-builder and cage on PATH\n' >&2
    exit 2
fi

# The cleanup below removes the app and its data: never run over a real installation.
if flatpak info com.erdlabs.zeile >/dev/null 2>&1; then  # user or system installation
    printf 'refusing to run: com.erdlabs.zeile is already installed (this check replaces it and deletes its data)\n' >&2
    exit 2
fi

# Data left behind by an earlier installation would be deleted by the cleanup too.
if [[ -e "$HOME/.var/app/com.erdlabs.zeile" ]]; then
    printf 'refusing to run: %s exists and would be deleted by the cleanup\n' \
        "$HOME/.var/app/com.erdlabs.zeile" >&2
    exit 2
fi

STATE="$(mktemp -d)"
BUILD="$(mktemp -d)"
DOC_DIR=""
COUNTER_FILE=""
PORT_FILE=""
LISTENER_PID=""

cleanup() {
    if [[ -n "${LISTENER_PID:-}" ]]; then
        kill "$LISTENER_PID" 2>/dev/null || true
        wait "$LISTENER_PID" 2>/dev/null || true
    fi
    flatpak uninstall --user -y com.erdlabs.zeile com.erdlabs.zeile.Debug >/dev/null 2>&1 || true
    rm -rf "${HOME}/.var/app/com.erdlabs.zeile"
    rm -rf "$STATE" "$BUILD"
    [[ -n "${DOC_DIR:-}" ]] && rm -rf "$DOC_DIR"
    [[ -n "${COUNTER_FILE:-}" ]] && rm -f "$COUNTER_FILE"
    [[ -n "${PORT_FILE:-}" ]] && rm -f "$PORT_FILE"
}
trap cleanup EXIT

flatpak-builder --user --install --force-clean --state-dir "$STATE" "$BUILD" \
    packaging/flatpak/com.erdlabs.zeile.yml

FAILED=0

# --- a. imports ---
if flatpak run --command=python3 com.erdlabs.zeile -c "
import nh3, markdown, pygments, pymdownx, gi
gi.require_version('WebKit', '6.0')
from gi.repository import WebKit
print('imports ok')
"; then
    printf 'PASS: imports\n'
else
    printf 'FAIL: imports\n'
    FAILED=1
fi

# --- b. probe under headless cage (with host TCP listener) ---
DOC_DIR="$(mktemp -d -p "$HOME")"
COUNTER_FILE="$(mktemp)"
PORT_FILE="$(mktemp)"
printf '0\n' >"$COUNTER_FILE"

python3 - "$COUNTER_FILE" "$PORT_FILE" <<'PY' &
import pathlib
import socket
import sys

counter = pathlib.Path(sys.argv[1])
port_path = pathlib.Path(sys.argv[2])
counter.write_text("0\n", encoding="utf-8")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", 0))
port_path.write_text(str(sock.getsockname()[1]), encoding="utf-8")
sock.listen()
n = 0
while True:
    conn, _addr = sock.accept()
    n += 1
    counter.write_text(f"{n}\n", encoding="utf-8")
    conn.close()
PY
LISTENER_PID=$!

for _ in $(seq 1 50); do
    if [[ -s "$PORT_FILE" ]]; then
        break
    fi
    sleep 0.1
done
if [[ ! -s "$PORT_FILE" ]]; then
    printf 'FAIL: probe\n' >&2
    printf 'listener did not publish a port\n' >&2
    exit 1
fi
PORT="$(cat "$PORT_FILE")"
if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
    printf 'FAIL: probe\nthe host listener died before the probe ran\n' >&2
    exit 1
fi

# Minimal valid 4x4 RGB PNG (no external tooling).
python3 - "$DOC_DIR/pic.png" <<'PY'
import struct
import sys
import zlib
from pathlib import Path


def chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


ihdr = struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)
row = b"\x00" + (b"\xff\x00\x00" * 4)
raw = row * 4
png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", ihdr)
    + chunk(b"IDAT", zlib.compress(raw))
    + chunk(b"IEND", b"")
)
Path(sys.argv[1]).write_bytes(png)
PY

# shellcheck disable=SC2016  # backticks are markdown, not command substitution
printf '%s\n' \
    '# Flatpak heading' \
    '' \
    'See [sibling](sibling.md).' \
    '' \
    '![pic](pic.png)' \
    >"$DOC_DIR/doc.md"
printf '# Sibling\n' >"$DOC_DIR/sibling.md"

PROBE_STATUS=0
WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 \
    cage -d -- flatpak run --command=python3 com.erdlabs.zeile \
    "$REPO/scripts/flatpak_probe.py" "$DOC_DIR" "$PORT" || PROBE_STATUS=$?

if [[ "$PROBE_STATUS" -eq 0 ]]; then
    printf 'PASS: probe\n'
else
    printf 'FAIL: probe\n'
    FAILED=1
fi

# --- c. host listener must stay untouched ---
COUNT="$(tr -d '[:space:]' <"$COUNTER_FILE")"
if [[ "$COUNT" == "0" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
    printf 'PASS: network isolation (host listener saw 0 connections)\n'
else
    printf 'FAIL: network isolation (listener saw %s connection(s) or died)\n' "$COUNT"
    FAILED=1
fi

if [[ "$FAILED" -ne 0 ]]; then
    exit 1
fi
printf 'flatpak-check OK\n'
