# Privacy Policy — zeile

Last updated: 2026-09-11

## Summary

zeile collects nothing, transmits nothing, and contains no advertising,
analytics, or tracking of any kind.

## What it is

zeile is a desktop GTK4 application for Linux. It is not distributed through
an app store. It runs locally, renders the markdown file you open, and exits.

## Data collection

zeile does not collect, store, or transmit personal data.

There is no account, no registration, and no identifier of any kind. No
usage statistics, crash reports, or diagnostic data are produced or sent.

**Verified, not merely asserted.** `zeile.py`, `markdown_ext.py`, and
`mermaid_render.py` contain no outbound network call of any kind — checked
2026-09-10:

```sh
grep -nE 'curl|wget|requests\.|urllib|http\.client|socket\.' zeile.py markdown_ext.py mermaid_render.py
# no matches
```

The one place network activity is even possible is a link a document
contains and you deliberately click: it opens in your system's default web
browser (`Gio.AppInfo.launch_default_for_uri`), a separate process zeile
does not control or observe. The document view itself never makes a network
request — it runs on an ephemeral `WebKit.NetworkSession` and a
navigation-policy handler that refuses to load anything but a local file
under the open document's own directory. See `README.md`'s Security section
for the full detail on how this is enforced, not just intended.

## Data storage

zeile keeps no history and no cookies. Its document WebView has HTML5 local
storage and the HTML5 database both disabled, so a `.md` file cannot plant
an identifier that survives across opens.

**One small configuration file, by request of the theme/font picker:**
`~/.config/zeile/settings.json` stores UI preferences only — the selected
theme id, body/code font ids, zoom level and window geometry (e.g.
`"tokyo-night"`, `"ia-writer"`, `"1.5"`, `"1200"`). No file paths, no
document content, no timestamps, no identifiers. Delete the file and zeile
falls back to its defaults on the next start.

**One honest exception in `~/.cache`, checked rather than assumed:** the
GPU driver (Mesa) writes compiled shader bytecode to
`~/.cache/mesa_shader_cache/` while the document window renders — confirmed
by touching a marker file, running zeile, and diffing `~/.cache` before and
after. This is shared, content-free GPU driver cache written by any
OpenGL/GTK application on the system, not something zeile writes
deliberately or that contains anything from the document you opened. No
`~/.cache/webkitgtk` or similar app-specific cache directory was created in
the same check.

If you use `--enable-mermaid`, it invokes `mmdc` (mermaid-cli) as a local
subprocess to render a diagram to a temporary SVG file, deleted immediately
after being read. No diagram source or output is written anywhere
persistent. zeile does not sandbox or network-isolate `mmdc` (it runs a headless
Chromium): enable the flag only for documents you trust.

## Third parties

zeile contains no third-party SDKs, advertising networks, or analytics
services, and no vendored third-party code (an earlier version vendored
Mermaid's JavaScript renderer; it was removed when Mermaid rendering moved
to the opt-in `mmdc` subprocess path — see `ASSETS.md`).

`mmdc`, if you install and enable it, is Mermaid's own official CLI and runs
entirely on your machine.

## Permissions

zeile requests no special permissions. It reads the markdown file you open
(and watches it for changes), and — only with `--enable-mermaid` — runs the
`mmdc` subprocess you installed yourself. It writes nothing except a PDF you
explicitly choose to export, to the location you choose, and the three-string
theme/font settings file described above.

## Children

zeile does not collect data from anyone, including children under 13.

## Source code

zeile is free software, licensed under the GNU General Public License
version 3 or later. The complete source is at
<https://github.com/DnaMes/zeile>. Every claim on this page can be checked
by reading it.

## Changes

If this policy changes, the updated version appears at this address with a
new date. Since the app collects nothing, no change can retroactively
affect data already gathered — there is none.

## Contact

erdlabs
<https://erdlabs.com>
