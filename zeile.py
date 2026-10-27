#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The Linux shell for zeile: a GTK4 window around a WebKitGTK view.

This file owns everything that is GTK: the window, the header bar, the search
bar, the settings and theme menu, the splash, printing and the CSS provider.
The platform-neutral parts -- markdown to HTML, the settings store, the launch
plan -- live in documents.py, preferences.py and launch.py, so a Windows or
macOS shell can drive the same core with a different webview.

A .md file is untrusted content a user double-clicks (install.sh makes this
the system default handler for text/markdown), so the rendered document runs
with document JavaScript structurally disabled, its HTML run through an
explicit sanitizer allowlist, the document carrying its own CSP, no persistent
storage, no network egress beyond the click-to-open-externally path, and
developer tools off unless --debug/ZEILE_DEBUG is set. The README's Security
section states the full threat model and what was measured rather than assumed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from functools import partial
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import Gdk, Gio, GLib, Gtk, Pango, WebKit  # noqa: E402

from documents import (  # noqa: E402
    EXTENSION_CONFIGS,
    EXTENSIONS,
    DocumentStats,
    build_document,
    classify_local_target,
    compute_document_stats,
    enhance_code_blocks,
    flatten_toc,
    read_asset,
    render,
    render_body,
    sanitize_html,
)
from i18n import _, _n  # noqa: E402
from launch import (  # noqa: E402
    LaunchPhase,
    launch_asset_path,
    phase_opacity,
    plan_launch_sequence,
)
from preferences import (  # noqa: E402
    BODY_FONT_OPTIONS,
    CODE_FONT_OPTIONS,
    READING_WIDTH_OPTIONS,
    THEME_OPTIONS,
    _coerce_font,
    _coerce_reading_width,
    _coerce_theme,
    _default_settings_path,
    _font_label,
    _theme_label,
    is_theme_dark,
    load_settings,
    save_settings,
)

APP_ID = "com.erdlabs.zeile"
__version__ = "0.5.0"

# The names above are re-exported on purpose: tests, scripts and the headless
# GUI matrix have always reached them as `zeile.X`, and the split into modules
# must not turn that into a scavenger hunt.
__all__ = [
    "APP_ID",
    "BODY_FONT_OPTIONS",
    "CODE_FONT_OPTIONS",
    "DocumentStats",
    "EXTENSION_CONFIGS",
    "EXTENSIONS",
    "LaunchPhase",
    "READING_WIDTH_OPTIONS",
    "THEME_OPTIONS",
    "ZeileApp",
    "_coerce_font",
    "_coerce_reading_width",
    "_coerce_theme",
    "_default_settings_path",
    "_font_label",
    "_theme_label",
    "build_document",
    "classify_local_target",
    "compute_document_stats",
    "enhance_code_blocks",
    "flatten_toc",
    "is_theme_dark",
    "launch_asset_path",
    "load_settings",
    "main",
    "phase_opacity",
    "plan_launch_sequence",
    "play_launch_sequence",
    "print_backends_available",
    "read_asset",
    "render",
    "render_body",
    "sanitize_html",
    "save_settings",
]


def print_backends_available() -> bool:
    """Whether GTK4 ships at least one print backend module.

    Recent GTK 4 releases (e.g. Arch's gtk4 1:4.22.4) no longer bundle the
    unix print backends, and nothing provides them separately -- without
    them WebKitPrintOperation quietly produces no file and no dialog. There
    is no public GTK API for enumerating backends, so this checks the
    well-known module directories. If a gtk-4.0 module tree exists at all,
    its verdict is trusted (a tree without printbackends/*.so means the
    backends are genuinely absent); only when no gtk-4.0 tree is found at
    all does this fall back to "available" -- buttons stay enabled, worst
    case is the old silent no-op.
    """
    import glob

    found_module_tree = False
    for libdir in ("/usr/lib", "/usr/lib64"):
        for version_dir in glob.glob(f"{libdir}/gtk-4.0/*"):
            found_module_tree = True
            if glob.glob(f"{version_dir}/printbackends/*.so"):
                return True
    return not found_module_tree


def _a11y_label(widget: Gtk.Widget, label: str) -> None:
    """Icon-only buttons need an accessible name; tooltips alone are not
    reliably exposed to assistive technology."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


class LaunchSplash(Gtk.Window):
    """Undecorated overlay that plays the phases, then calls `on_done` once.

    Any key press or click skips the WHOLE sequence, not just the current
    phase. The main viewer may already be open behind this window.
    """

    def __init__(
        self,
        app: Gtk.Application,
        phases: list[LaunchPhase],
        on_done,
        *,
        on_phase=None,
    ) -> None:
        super().__init__(application=app, decorated=False, resizable=False)
        self.set_default_size(360, 280)
        _a11y_label(self, _("Start sequence"))
        self.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [_("Press any key or click to skip")],
        )
        self._phases = phases
        self._on_done = on_done
        self._on_phase = on_phase
        self._index = -1
        self._start_us: int | None = None
        self._finished = False
        self.picture = Gtk.Picture(can_shrink=False)
        self.picture.set_size_request(160, 160)
        self.picture.set_halign(Gtk.Align.CENTER)
        self.picture.set_valign(Gtk.Align.CENTER)
        self.picture.set_opacity(0.0)
        self.set_child(self.picture)
        self._key = Gtk.EventControllerKey()
        self._key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._key.connect("key-pressed", lambda *_a: self.skip() or True)
        self.add_controller(self._key)
        self._click = Gtk.GestureClick()
        self._click.set_button(0)  # any mouse button
        self._click.connect("pressed", lambda *_a: self.skip())
        self.add_controller(self._click)
        self.add_tick_callback(self._tick)

    def _load(self, index: int) -> None:
        self._index = index
        self._start_us = None
        asset = launch_asset_path(self._phases[index].asset)
        try:
            texture = Gdk.Texture.new_from_filename(str(asset))
        except GLib.Error as exc:
            # A package that did not ship the image must not strand the viewer
            # behind an overlay: skip the whole sequence and open the document.
            print(f"zeile: start sequence skipped ({exc.message})", file=sys.stderr)
            self.skip()
            return
        self.picture.set_paintable(texture)
        if self._on_phase is not None:
            self._on_phase(self._phases[index])

    def _tick(self, _widget, clock) -> bool:
        if self._finished:
            return GLib.SOURCE_REMOVE
        now = clock.get_frame_time()
        if self._index < 0 or self._start_us is None:
            if self._index < 0:
                self._load(0)
                if self._finished:
                    return GLib.SOURCE_REMOVE
            self._start_us = now
        t_ms = (now - self._start_us) / 1000
        phase = self._phases[self._index]
        if t_ms >= phase.total:
            if self._index + 1 >= len(self._phases):
                self.skip()
                return GLib.SOURCE_REMOVE
            self._load(self._index + 1)
            if self._finished:
                return GLib.SOURCE_REMOVE
            self._start_us = now
            t_ms = 0
        self.picture.set_opacity(phase_opacity(self._phases[self._index], t_ms))
        return GLib.SOURCE_CONTINUE

    def skip(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._on_done()
        self.destroy()


def play_launch_sequence(
    app: Gtk.Application, settings_path: Path, on_done
) -> LaunchSplash | None:
    """Show the launch overlay on first start, then call `on_done` once."""
    settings = load_settings(path=settings_path)
    intro_seen = settings["intro_seen"] == "true"
    animations = bool(Gtk.Settings.get_default().get_property("gtk-enable-animations"))
    phases = plan_launch_sequence(intro_seen=intro_seen, animations=animations)
    if not phases:
        on_done()
        return None
    if not intro_seen:
        # Recorded at the start: a crash or kill mid-intro must not replay it.
        settings["intro_seen"] = "true"
        save_settings(settings, path=settings_path)
    splash = LaunchSplash(app, phases, on_done)
    splash.present()
    return splash


_css_initialized = False


def _ensure_gtk_css() -> None:
    global _css_initialized
    if _css_initialized:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(
        """
        .link-preview-pill {
            background-color: alpha(@window_bg_color, 0.92);
            color: @window_fg_color;
            border: 1px solid alpha(@borders, 0.7);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 0.85em;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
        }
        """
    )
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _css_initialized = True


class Viewer(Gtk.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        path: Path,
        *,
        enable_mermaid: bool,
        debug: bool,
        theme_id: str,
        body_font_id: str,
        code_font_id: str,
        settings_path: Path,
    ) -> None:
        super().__init__(application=app, title=path.name)
        self.set_default_size(900, 1000)

        # Show the name the user opened, but watch the real file: monitoring a
        # symlink itself never reports edits made to its target.
        self.display_name = path.name
        self.path = path.resolve()
        self.enable_mermaid = enable_mermaid

        self.theme_id = _coerce_theme(theme_id)
        self.body_font_id = _coerce_font(body_font_id, kind="body")
        self.code_font_id = _coerce_font(code_font_id, kind="code")
        self.settings_path = settings_path
        self._persisted = load_settings(path=settings_path)
        self.reading_width = _coerce_reading_width(self._persisted["reading_width"])
        self.set_default_size(
            int(self._persisted["window_w"]), int(self._persisted["window_h"])
        )
        if self._persisted["window_maximized"] == "true":
            self.maximize()

        self.monitor: Gio.FileMonitor | None = None
        self._reload_source: int | None = None
        self._pending_restore_scroll = False
        self._scroll_to_restore = 0
        self._back_stack: list[Path] = []
        self._forward_stack: list[Path] = []
        # Plain text of each rendered code block, index-aligned with the
        # zeile-copy://N links in the current document (see enhance_code_blocks).
        self._code_texts: list[str] = []

        # GTK preference is used for Mermaid defaults and to seed "Auto" theme.
        self.dark = Gtk.Settings.get_default().get_property(
            "gtk-application-prefer-dark-theme"
        )

        # Ephemeral session: no cookie jar, no HTTP cache persisted to disk.
        # decide-policy below is what actually stops any request from being
        # made in the first place for anything but the local document's tree.
        session = WebKit.NetworkSession.new_ephemeral()
        self.webview = WebKit.WebView(network_session=session)
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        # False here, not set_enable_javascript(False): this is the setting
        # that actually blocks a document's own <script>/onerror=, verified
        # empirically (window.* set by an injected <script> stayed
        # undefined). enable_javascript stays True so the app's own
        # evaluate_javascript() calls (scroll position, future TOC-jump)
        # keep working -- they never evaluate anything sourced from the
        # document itself.
        settings.set_enable_javascript_markup(False)
        settings.set_enable_html5_local_storage(False)
        settings.set_enable_html5_database(False)
        settings.set_enable_developer_extras(debug)

        self.webview.connect("decide-policy", self._on_decide_policy)
        self.webview.connect("load-changed", self._on_load_changed)
        self.webview.connect("mouse-target-changed", self._on_mouse_target_changed)
        self.find_controller = self.webview.get_find_controller()

        # Restore persisted zoom, and follow system light/dark flips when in
        # "Auto" (the Mermaid palette bakes the theme in, so it needs a
        # re-render, not just a CSS flip).
        try:
            self.webview.set_zoom_level(float(self._persisted["zoom"]))
        except ValueError:
            pass
        Gtk.Settings.get_default().connect(
            "notify::gtk-application-prefer-dark-theme", self._on_system_theme_changed
        )
        self.connect("close-request", self._on_close_request)

        self.back_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.back_button.set_tooltip_text(_("Back (Alt+Left)"))
        _a11y_label(self.back_button, _("Back"))
        self.back_button.connect("clicked", lambda _b: self.go_back())

        self.forward_button = Gtk.Button(icon_name="go-next-symbolic")
        self.forward_button.set_tooltip_text(_("Forward (Alt+Right)"))
        _a11y_label(self.forward_button, _("Forward"))
        self.forward_button.connect("clicked", lambda _b: self.go_forward())

        self._update_nav_sensitivity()

        self._toc_flat: list[tuple[int, str, str]] = []
        self._doc_stats = DocumentStats(words=0, chars=0, reading_time_minutes=0)

        toc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        toc_box.set_margin_start(8)
        toc_box.set_margin_end(8)
        toc_box.set_margin_top(8)
        toc_box.set_margin_bottom(8)

        self.toc_stats_label = Gtk.Label(xalign=0)
        self.toc_stats_label.add_css_class("dim-label")
        self.toc_stats_label.set_margin_start(4)
        self.toc_stats_label.set_margin_end(4)
        self.toc_stats_label.set_margin_top(2)
        self.toc_stats_label.set_margin_bottom(2)
        toc_box.append(self.toc_stats_label)

        self.toc_filter_entry = Gtk.SearchEntry()
        self.toc_filter_entry.set_placeholder_text(_("Filter headings…"))
        self.toc_filter_entry.connect("search-changed", self._on_toc_filter_changed)
        self.toc_filter_entry.connect("activate", self._on_toc_filter_activate)
        toc_box.append(self.toc_filter_entry)

        self.toc_list = Gtk.ListBox()
        self.toc_list.connect("row-activated", self._on_toc_row_activated)
        self.toc_list.set_filter_func(self._toc_filter_func)
        toc_scroller = Gtk.ScrolledWindow()
        toc_scroller.set_min_content_height(300)
        toc_scroller.set_min_content_width(260)
        toc_scroller.set_child(self.toc_list)
        toc_box.append(toc_scroller)

        self.toc_popover = Gtk.Popover()
        self.toc_popover.set_child(toc_box)
        self.toc_popover.connect("show", self._populate_toc)

        self.toc_button = Gtk.MenuButton(icon_name="view-list-symbolic")
        self.toc_button.set_tooltip_text(_("Table of contents (Ctrl+T)"))
        _a11y_label(self.toc_button, _("Table of contents"))
        self.toc_button.set_popover(self.toc_popover)

        export_button = Gtk.Button(icon_name="document-save-symbolic")
        print_button = Gtk.Button(icon_name="document-print-symbolic")
        if print_backends_available():
            export_button.set_tooltip_text(_("Export PDF…"))
            print_button.set_tooltip_text(_("Print (Ctrl+P)"))
            _a11y_label(export_button, _("Export PDF"))
            _a11y_label(print_button, _("Print"))
        else:
            # GTK 4.22+ ships no print backends on some distros; the buttons
            # would silently no-op. Degrade visibly instead.
            reason = _("Unavailable: GTK4 print backends are missing on this system")
            for button in (export_button, print_button):
                button.set_sensitive(False)
                button.set_tooltip_text(reason)
        export_button.connect("clicked", lambda _b: self._export_pdf())
        print_button.connect("clicked", lambda _b: self._print_dialog())

        about_button = Gtk.Button(icon_name="help-about-symbolic")
        about_button.set_tooltip_text(_("About zeile"))
        _a11y_label(about_button, _("About zeile"))
        about_button.connect("clicked", lambda _b: self._show_about())

        self.theme_button = Gtk.MenuButton(icon_name="preferences-color-symbolic")
        self.theme_button.set_tooltip_text(_("Theme and fonts"))
        _a11y_label(self.theme_button, _("Theme and fonts"))
        self.theme_button.set_popover(self._build_theme_popover())

        self._title_label = Gtk.Label(label=self.display_name)
        header = Gtk.HeaderBar()
        header.set_title_widget(self._title_label)
        header.pack_start(self.back_button)
        header.pack_start(self.forward_button)

        reload_button = Gtk.Button(icon_name="view-refresh-symbolic")
        reload_button.set_tooltip_text(_("Reload (Ctrl+R)"))
        _a11y_label(reload_button, _("Reload"))
        reload_button.connect("clicked", lambda _b: self.reload())
        header.pack_start(reload_button)

        header.pack_start(self.toc_button)
        header.pack_start(self.theme_button)
        header.pack_end(about_button)
        header.pack_end(export_button)
        header.pack_end(print_button)
        self.set_titlebar(header)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect(
            "next-match", lambda *_: self.find_controller.search_next()
        )
        self.search_entry.connect(
            "previous-match", lambda *_: self.find_controller.search_previous()
        )
        self.search_entry.connect("stop-search", lambda *_: self._close_search())
        # Live match count next to the entry (WebKitGTK has no "current
        # match index", only the total -- still answers "are there any?").
        # failed-to-find-text is the reliable "zero matches" signal;
        # counted-matches does not fire on all builds, so found-text
        # (which fires on search()) carries the count.
        self.find_controller.connect("found-text", self._on_found_text)
        self.find_controller.connect("failed-to-find-text", self._on_failed_to_find)
        self._match_label = Gtk.Label()
        self._match_label.add_css_class("dim-label")
        self._match_label.set_margin_end(6)
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.append(self.search_entry)
        search_box.append(self._match_label)
        self.search_bar = Gtk.SearchBar()
        self.search_bar.set_child(search_box)
        self.search_bar.connect_entry(self.search_entry)

        _ensure_gtk_css()

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.webview)
        # Without these, the ScrolledWindow collapses to its natural
        # (minimum) size inside the Box below instead of filling it --
        # vexpand on the Box alone only affects the Box's own allocation
        # from its parent, not how the Box distributes space to its own
        # children. Confirmed by reproducing a fully black WebView with
        # this missing and fixing it by adding exactly these two lines.
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)

        overlay = Gtk.Overlay()
        overlay.set_child(scroller)
        overlay.set_vexpand(True)
        overlay.set_hexpand(True)

        self._link_preview_label = Gtk.Label()
        self._link_preview_label.add_css_class("link-preview-pill")
        self._link_preview_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._link_preview_label.set_max_width_chars(60)
        self._link_preview_label.set_margin_start(12)
        self._link_preview_label.set_margin_bottom(12)

        self._link_preview_revealer = Gtk.Revealer()
        self._link_preview_revealer.set_child(self._link_preview_label)
        self._link_preview_revealer.set_transition_type(
            Gtk.RevealerTransitionType.CROSSFADE
        )
        self._link_preview_revealer.set_halign(Gtk.Align.START)
        self._link_preview_revealer.set_valign(Gtk.Align.END)
        self._link_preview_revealer.set_reveal_child(False)

        overlay.add_overlay(self._link_preview_revealer)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.search_bar)
        box.append(overlay)
        self.set_child(box)

        self._shortcut_overlay: Gtk.Window | None = None
        self._help_key = Gtk.EventControllerKey()
        self._help_key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._help_key.connect("key-pressed", self._on_help_key)
        self.add_controller(self._help_key)

        self._add_shortcuts()
        self.reload()
        self._watch()

    def _build_theme_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        theme_title = Gtk.Label(label=_("Theme"), xalign=0)
        box.append(theme_title)

        theme_model = Gtk.StringList()
        self._theme_ids: list[str] = list(THEME_OPTIONS)
        for theme_id in self._theme_ids:
            theme_model.append(_theme_label(theme_id))

        self.theme_dropdown = Gtk.DropDown.new(model=theme_model)
        self.theme_dropdown.set_selected(self._theme_ids.index(self.theme_id))
        self.theme_dropdown.connect(
            "notify::selected",
            partial(self._on_theme_dropdown_changed, self._theme_ids),
        )
        box.append(self.theme_dropdown)

        body_font_title = Gtk.Label(label=_("Body font"), xalign=0)
        body_font_title.set_margin_top(8)
        box.append(body_font_title)

        body_font_model = Gtk.StringList()
        self._body_font_ids: list[str] = list(BODY_FONT_OPTIONS)
        for body_font_id in self._body_font_ids:
            body_font_model.append(_font_label(body_font_id, is_code=False))

        self.body_font_dropdown = Gtk.DropDown.new(model=body_font_model)
        self.body_font_dropdown.set_selected(self._body_font_ids.index(self.body_font_id))
        self.body_font_dropdown.connect(
            "notify::selected",
            partial(self._on_font_dropdown_changed, self._body_font_ids, "body"),
        )
        box.append(self.body_font_dropdown)

        code_font_title = Gtk.Label(label=_("Code font"), xalign=0)
        code_font_title.set_margin_top(8)
        box.append(code_font_title)

        code_font_model = Gtk.StringList()
        self._code_font_ids: list[str] = list(CODE_FONT_OPTIONS)
        for code_font_id in self._code_font_ids:
            code_font_model.append(_font_label(code_font_id, is_code=True))

        self.code_font_dropdown = Gtk.DropDown.new(model=code_font_model)
        self.code_font_dropdown.set_selected(self._code_font_ids.index(self.code_font_id))
        self.code_font_dropdown.connect(
            "notify::selected",
            partial(self._on_font_dropdown_changed, self._code_font_ids, "code"),
        )
        box.append(self.code_font_dropdown)

        width_title = Gtk.Label(label=_("Reading width"), xalign=0)
        width_title.set_margin_top(8)
        box.append(width_title)

        width_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._width_buttons: dict[str, Gtk.ToggleButton] = {}
        width_group: Gtk.ToggleButton | None = None
        for width_id, label in (
            ("narrow", _("Narrow")),
            ("standard", _("Standard")),
            ("wide", _("Wide")),
        ):
            btn = Gtk.ToggleButton(label=label)
            if width_group is None:
                width_group = btn
            else:
                btn.set_group(width_group)
            btn.set_active(width_id == self.reading_width)
            btn.connect("toggled", partial(self._on_width_toggled, width_id))
            self._width_buttons[width_id] = btn
            width_row.append(btn)
        box.append(width_row)

        pop.set_child(box)
        return pop

    def _persist_settings(self) -> None:
        # Merge into the freshly loaded state: only the keys this method
        # owns may change -- the zoom/window keys must survive.
        current = load_settings(path=self.settings_path)
        current.update(
            {
                "theme": self.theme_id,
                "body_font": self.body_font_id,
                "code_font": self.code_font_id,
                "reading_width": self.reading_width,
            }
        )
        save_settings(current, path=self.settings_path)

    def _on_close_request(self, *_args) -> bool:
        self._save_window_state()
        return False  # keep closing

    def _save_window_state(self) -> None:
        if self.get_width() <= 0:  # never mapped -- nothing to record
            return
        current = load_settings(path=self.settings_path)
        current.update(
            {
                "window_w": str(self.get_width()),
                "window_h": str(self.get_height()),
                "window_maximized": "true" if self.is_maximized() else "false",
                "zoom": str(round(self.webview.get_zoom_level(), 3)),
            }
        )
        save_settings(current, path=self.settings_path)

    def _on_system_theme_changed(self, *_args) -> None:
        # Only Auto tracks the system: explicit themes intentionally pin the
        # GTK preference themselves (which fires this same notify -- guard
        # prevents a reload loop).
        if self.theme_id == "auto":
            self.reload()

    def _apply_theme_and_font_attrs(self) -> None:
        # No `const`/`let` here: top-level lexical bindings persist across
        # evaluate_javascript() calls on the same page, so a second call
        # would die with "Identifier 'root' has already been declared" and
        # silently do nothing (found by the headless theme-matrix harness:
        # first switch worked, every later one was a no-op).
        root = "document.documentElement"
        js = (
            (
                f"{root}.setAttribute('data-theme', {json.dumps(self.theme_id)});"
                if self.theme_id != "auto"
                else f"{root}.removeAttribute('data-theme');"
            )
            + f"{root}.setAttribute('data-font-body', {json.dumps(self.body_font_id)});"
            + f"{root}.setAttribute('data-font-code', {json.dumps(self.code_font_id)});"
            + (
                f"{root}.setAttribute('data-width', {json.dumps(self.reading_width)});"
                if self.reading_width != "standard"
                else f"{root}.removeAttribute('data-width');"
            )
        )
        # A new width, font or theme reflows the page: keep the passage the reader is on
        # where it is (the first visible block keeps its distance from the viewport top).
        # WebKitGTK's own scroll anchoring does this on Arch but not on Debian 13, Ubuntu
        # 24.04 or Fedora 43 (headless matrix, width-keeps-position). IIFE and `var` only,
        # for the same re-evaluation reason as above.
        anchored = (
            "(function(){"
            "var blocks=document.querySelectorAll("
            "'h1,h2,h3,h4,h5,h6,p,pre,table,ul,ol,blockquote,hr');"
            "var anchor=null,top=0;"
            "for(var i=0;i<blocks.length;i++){"
            "var r=blocks[i].getBoundingClientRect();"
            "if(r.bottom>4){anchor=blocks[i];top=r.top;break;}"
            "}"
            f"{js}"
            "if(anchor){window.scrollBy(0,anchor.getBoundingClientRect().top-top);}"
            "})();"
        )
        self.webview.evaluate_javascript(anchored, -1, None, None, None, None, None)

    def _on_theme_dropdown_changed(
        self, theme_ids: list[str], dropdown: Gtk.DropDown, *_pspec
    ) -> None:
        selected = dropdown.get_selected()
        if selected < 0:
            return
        self._set_theme(theme_ids[selected])

    def _on_font_dropdown_changed(
        self, font_ids: list[str], kind: str, dropdown: Gtk.DropDown, *_pspec
    ) -> None:
        selected = dropdown.get_selected()
        if selected < 0:
            return
        font_id = font_ids[selected]
        if kind == "body":
            self._set_body_font(font_id)
        else:
            self._set_code_font(font_id)

    def _set_theme(self, theme_id: str) -> None:
        theme_id = _coerce_theme(theme_id)
        if theme_id == self.theme_id:
            return

        prev_dark = is_theme_dark(self.theme_id, fallback=self.dark)
        self.theme_id = theme_id
        next_dark = is_theme_dark(self.theme_id, fallback=self.dark)

        if self.enable_mermaid and prev_dark != next_dark:
            # Mermaid SVGs bake the palette in at render time, so a
            # light<->dark flip needs a real re-render, not just a CSS flip.
            self.reload()  # also syncs the GTK chrome via _sync_theme_with_gtk
        else:
            self._apply_theme_and_font_attrs()
            self._sync_theme_with_gtk()

        self._persist_settings()

    def _set_body_font(self, body_font_id: str) -> None:
        body_font_id = _coerce_font(body_font_id, kind="body")
        if body_font_id == self.body_font_id:
            return
        self.body_font_id = body_font_id
        self._apply_theme_and_font_attrs()
        self._persist_settings()

    def _set_code_font(self, code_font_id: str) -> None:
        code_font_id = _coerce_font(code_font_id, kind="code")
        if code_font_id == self.code_font_id:
            return
        self.code_font_id = code_font_id
        self._apply_theme_and_font_attrs()
        self._persist_settings()

    def _on_width_toggled(self, width_id: str, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            return
        self._set_reading_width(width_id)

    def _set_reading_width(self, reading_width: str) -> None:
        reading_width = _coerce_reading_width(reading_width)
        if reading_width == self.reading_width:
            return
        self.reading_width = reading_width
        btn = self._width_buttons.get(reading_width)
        if btn is not None and not btn.get_active():
            btn.set_active(True)
        self._apply_theme_and_font_attrs()
        self._persist_settings()

    def _on_decide_policy(
        self,
        _webview: WebKit.WebView,
        decision: WebKit.PolicyDecision,
        decision_type: WebKit.PolicyDecisionType,
    ) -> bool:
        """Only allow file:// navigation under the open document's directory.

        A local .md/.markdown link re-enters our own renderer via
        navigate_to() instead of letting WebKit load it directly (which
        would dump raw markdown source with no way back -- confirmed broken
        before this). A local image still loads in the WebView directly.
        Everything else -- other local files such as .html or .svg (they
        would bypass the CSP), http(s), any other scheme, or a file:// path
        outside the document's directory tree --
        is handed to the system's default opener. Combined with the
        ephemeral NetworkSession above, this is what actually makes "no
        network access" true rather than aspirational.
        """
        if decision_type != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            decision.use()
            return True

        uri = decision.get_navigation_action().get_request().get_uri()
        gfile = Gio.File.new_for_uri(uri)
        local_path = gfile.get_path()
        scheme = (gfile.get_uri_scheme() or "").lower()
        if scheme == "zeile-copy":
            # Copy-button click (see enhance_code_blocks): the link is pure
            # HTML navigation -- document JavaScript stays structurally off.
            decision.ignore()
            self._copy_code_block(uri)
            return True
        if scheme == "file" and local_path is not None:
            target = Path(local_path).resolve()
            action = classify_local_target(target, self.path)
            if action == "navigate":
                decision.ignore()
                # Deferred: re-entering load_html synchronously from
                # inside the policy callback is a documented-fragile
                # WebKitGTK pattern known to break ("check this first" in
                # the security notes).
                GLib.idle_add(self.navigate_to, target)
                return True
            if action == "load":
                decision.use()
                return True

        decision.ignore()
        Gio.AppInfo.launch_default_for_uri(uri)
        return True

    _COPY_URI_RE = re.compile(r"zeile-copy://(\d+)")

    def _copy_code_block(self, uri: str) -> None:
        """Put code block N's plain text on the system clipboard.

        Index comes from our own injected href; a hostile document
        spoofing a zeile-copy: link can only ever copy text of a block
        that already exists in that same document, and an out-of-range
        index is a silent no-op.
        """
        match = self._COPY_URI_RE.fullmatch(uri)
        if match is None:
            return
        index = int(match.group(1))
        if not 0 <= index < len(self._code_texts):
            return
        display = Gdk.Display.get_default()
        if display is not None:
            # set_content(new_for_value(str)) is the GTK4 way -- there is no
            # set_text on Gdk.Clipboard (verified via introspection); the
            # round trip was verified with read_text_async.
            display.get_clipboard().set_content(
                Gdk.ContentProvider.new_for_value(self._code_texts[index])
            )
        self._flash_copy_feedback(index)

    def _flash_copy_feedback(self, index: int) -> None:
        """Briefly mark the clicked copy button as done (check icon).

        The script is app-authored and constant apart from a validated int,
        wrapped in an IIFE so no top-level bindings persist across
        evaluate_javascript() calls (the const-redeclaration trap).
        """
        selector = json.dumps(f"a.code-copy[href='zeile-copy://{index}']")
        js = (
            "(function(){var el=document.querySelector("
            + selector
            + ");if(el){el.classList.add('copied');"
            "window.setTimeout(function(){el.classList.remove('copied');},1400);}})();"
        )
        self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

    def navigate_to(self, path: Path, *, record_history: bool = True) -> None:
        """Switch the currently displayed document, without opening a new window."""
        if record_history:
            self._back_stack.append(self.path)
            self._forward_stack.clear()
        self.path = path.resolve()
        self.display_name = self.path.name
        self._title_label.set_label(self.display_name)
        self.set_title(self.display_name)
        self._update_nav_sensitivity()
        self._watch()
        self.reload()

    def go_back(self) -> bool:
        if self._back_stack:
            self._forward_stack.append(self.path)
            self.navigate_to(self._back_stack.pop(), record_history=False)
        return True

    def go_forward(self) -> bool:
        if self._forward_stack:
            self._back_stack.append(self.path)
            self.navigate_to(self._forward_stack.pop(), record_history=False)
        return True

    def _update_nav_sensitivity(self) -> None:
        self.back_button.set_sensitive(bool(self._back_stack))
        self.forward_button.set_sensitive(bool(self._forward_stack))

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text()
        if not text:
            self.find_controller.search_finish()
            self._match_label.set_text("")
            return
        options = WebKit.FindOptions.CASE_INSENSITIVE | WebKit.FindOptions.WRAP_AROUND
        self.find_controller.search(text, options, 1000)

    def _on_found_text(self, _controller: WebKit.FindController, match_count: int) -> None:
        self._match_label.set_text(_n("%d match", "%d matches", match_count) % match_count)

    def _on_failed_to_find(self, _controller: WebKit.FindController) -> None:
        self._match_label.set_text(_("No matches"))

    def _close_search(self) -> None:
        self.find_controller.search_finish()
        self._match_label.set_text("")
        self.search_bar.set_search_mode(False)

    def _toggle_search(self) -> bool:
        active = not self.search_bar.get_search_mode()
        self.search_bar.set_search_mode(active)
        if active:
            self.search_entry.grab_focus()
        else:
            self.find_controller.search_finish()
            self._match_label.set_text("")
        return True

    def _on_load_changed(self, _webview: WebKit.WebView, event: WebKit.LoadEvent) -> None:
        if event != WebKit.LoadEvent.FINISHED:
            return
        if self._pending_restore_scroll:
            self._pending_restore_scroll = False
            # Value embedded as a validated Python int -- no JS-side state,
            # clamped to the new document height (it may have shrunk).
            y = max(0, self._scroll_to_restore)
            self.webview.evaluate_javascript(
                f"window.scrollTo(0, Math.min({y}, "
                "Math.max(0, document.documentElement.scrollHeight "
                "- window.innerHeight)));",
                -1,
                None,
                None,
                None,
                None,
                None,
            )

    def _populate_toc(self, *_args) -> bool:
        child = self.toc_list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.toc_list.remove(child)
            child = following

        self.toc_filter_entry.set_text("")

        stats = self._doc_stats
        headings_count = len(self._toc_flat)
        if stats.words > 0:
            words_str = f"{stats.words:,}".replace(",", ".")
            words_text = _n("%s word", "%s words", stats.words) % words_str
            reading_text = (
                _n("~%d min read", "~%d min read", stats.reading_time_minutes)
                % stats.reading_time_minutes
            )
            sections_text = _n("%d section", "%d sections", headings_count) % headings_count
            self.toc_stats_label.set_text(
                f"{words_text} · {reading_text} · {sections_text}"
            )
            self.toc_stats_label.set_visible(True)
        else:
            self.toc_stats_label.set_visible(False)

        if not self._toc_flat:
            self.toc_filter_entry.set_visible(False)
            placeholder = Gtk.Label(label=_("No headings found"), xalign=0.5)
            placeholder.add_css_class("dim-label")
            placeholder.set_margin_top(24)
            placeholder.set_margin_bottom(24)
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.set_activatable(False)
            row.set_child(placeholder)
            self.toc_list.append(row)
            return True

        self.toc_filter_entry.set_visible(True)
        for depth, heading_id, name in self._toc_flat:
            row = Gtk.ListBoxRow()
            row._heading_id = heading_id
            row._heading_text = name
            label = Gtk.Label(label=name, xalign=0)
            label.set_margin_start(8 + depth * 14)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            row.set_child(label)
            self.toc_list.append(row)
        return True

    def _on_toc_filter_changed(self, _entry: Gtk.SearchEntry) -> None:
        self.toc_list.invalidate_filter()

    def _toc_filter_func(self, row: Gtk.ListBoxRow) -> bool:
        query = self.toc_filter_entry.get_text().strip().lower()
        if not query:
            return True
        heading_text = getattr(row, "_heading_text", "")
        return query in heading_text.lower()

    def _scroll_to_heading(self, heading_id: str) -> None:
        self.webview.evaluate_javascript(
            f"document.getElementById({json.dumps(heading_id)}).scrollIntoView();",
            -1,
            None,
            None,
            None,
            None,
            None,
        )

    def _on_toc_filter_activate(self, _entry: Gtk.SearchEntry) -> None:
        child = self.toc_list.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.ListBoxRow) and self._toc_filter_func(child):
                heading_id = getattr(child, "_heading_id", None)
                if heading_id:
                    self._scroll_to_heading(heading_id)
                    self.toc_popover.popdown()
                    break
            child = child.get_next_sibling()

    def _on_toc_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        heading_id = getattr(row, "_heading_id", None)
        if heading_id:
            self._scroll_to_heading(heading_id)
        elif 0 <= row.get_index() < len(self._toc_flat):
            _depth, fallback_id, _name = self._toc_flat[row.get_index()]
            self._scroll_to_heading(fallback_id)
        self.toc_popover.popdown()

    def _show_about(self) -> None:
        dialog = Gtk.Dialog(
            title=_("About zeile"),
            transient_for=self,
            modal=True,
        )
        dialog.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        dialog.set_default_response(Gtk.ResponseType.CLOSE)

        content = dialog.get_content_area()
        content.set_spacing(18)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.START)

        # App icon: load the shipped files first so the dialog works before the
        # icon theme has been installed system-wide. The SVG needs a gdk-pixbuf
        # SVG loader (librsvg), which not every system has; the PNG does not.
        here = Path(__file__).resolve().parent
        app_icon = Gtk.Image.new_from_icon_name("zeile")
        for candidate in (
            here / "assets" / "zeile.svg",
            here / "icons" / "hicolor" / "128x128" / "apps" / "zeile.png",
        ):
            if candidate.is_file():
                loaded = Gtk.Image.new_from_file(str(candidate))
                if loaded.get_paintable() is not None:
                    app_icon = loaded
                    break
        app_icon.set_pixel_size(128)
        box.append(app_icon)

        name_label = Gtk.Label()
        name_label.set_markup("<span size='x-large' weight='bold'>zeile</span>")
        box.append(name_label)

        version_label = Gtk.Label(label=_("Version {version}").format(version=__version__))
        box.append(version_label)

        comments_label = Gtk.Label(label=_("A small, fast, read-only markdown viewer."))
        comments_label.set_wrap(True)
        comments_label.set_max_width_chars(40)
        comments_label.set_justify(Gtk.Justification.CENTER)
        box.append(comments_label)

        # erdlabs brand mark shown below the app metadata.
        logo_path = Path(__file__).resolve().parent / "assets" / "logo_erdlabs.png"
        if logo_path.is_file():
            logo = Gtk.Image.new_from_file(str(logo_path))
            logo.set_pixel_size(192)
            box.append(logo)

        link = Gtk.LinkButton.new_with_label("https://erdlabs.com", "erdlabs.com")
        box.append(link)

        license_label = Gtk.Label()
        license_label.set_markup(
            '<a href="https://www.gnu.org/licenses/gpl-3.0.html">'
            + _("GNU General Public License, version 3")
            + "</a>"
        )
        license_label.set_wrap(True)
        license_label.set_max_width_chars(50)
        box.append(license_label)

        content.append(box)
        dialog.connect("response", lambda _d, _response: dialog.destroy())
        dialog.present()

    def _print_dialog(self) -> bool:
        """Interactive Ctrl+P: the OS print dialog, printer/copies/etc."""
        op = WebKit.PrintOperation.new(self.webview)
        op.run_dialog(self)
        return True

    def _export_pdf(self) -> None:
        """Non-interactive PDF export: a save-location picker, then straight
        to a PDF file -- no OS print dialog in between."""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Export PDF"))
        dialog.set_initial_name(self.path.stem + ".pdf")
        dialog.save(self, None, self._on_export_pdf_chosen)

    def _on_export_pdf_chosen(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # user cancelled
        settings = Gtk.PrintSettings()
        settings.set("output-uri", gfile.get_uri())
        settings.set("output-file-format", "pdf")
        op = WebKit.PrintOperation.new(self.webview)
        op.set_print_settings(settings)
        op.print_()

    def _add_shortcuts(self) -> None:
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, callback in (
            ("<Control>r", lambda *_: self.reload()),
            ("<Control>w", lambda *_: self.close()),
            ("<Control>q", lambda *_: self.close()),
            ("<Control>plus", lambda *_: self._zoom(0.1)),
            ("<Control>equal", lambda *_: self._zoom(0.1)),
            ("<Control>minus", lambda *_: self._zoom(-0.1)),
            ("<Control>0", lambda *_: self.webview.set_zoom_level(1.0)),
            ("<Control>f", lambda *_: self._toggle_search()),
            ("<Alt>Left", lambda *_: self.go_back()),
            ("<Alt>Right", lambda *_: self.go_forward()),
            ("<Control>t", lambda *_: self.toc_popover.popup()),
            ("<Control>p", lambda *_: self._print_dialog()),
            ("F11", lambda *_: self._toggle_fullscreen()),
        ):
            controller.add_shortcut(
                Gtk.Shortcut(
                    trigger=Gtk.ShortcutTrigger.parse_string(accel),
                    action=Gtk.CallbackAction.new(callback),
                )
            )
        self.add_controller(controller)

    def _on_help_key(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        # Capture only F1 so the find entry keeps receiving typed characters.
        if keyval != Gdk.KEY_F1:
            return False
        return self._toggle_shortcut_overlay()

    def _shortcut_help_entries(self) -> list[tuple[str, str]]:
        return [
            ("Ctrl+R", _("Reload")),
            ("Ctrl+W / Ctrl+Q", _("Close")),
            ("Ctrl++ / Ctrl+- / Ctrl+0", _("Zoom")),
            ("Ctrl+F", _("Find")),
            ("Alt+Left / Alt+Right", _("Back / Forward")),
            ("Ctrl+T", _("Outline")),
            ("Ctrl+P", _("Print")),
            ("F11", _("Fullscreen")),
            ("F1", _("This help")),
        ]

    def _toggle_shortcut_overlay(self) -> bool:
        if self._shortcut_overlay is not None:
            self._close_shortcut_overlay()
            return True

        overlay = Gtk.Window(
            application=self.get_application(),
            title=_("Keyboard shortcuts"),
            transient_for=self,
            destroy_with_parent=True,  # closing the viewer must not strand this window
            modal=False,
            resizable=False,
        )
        overlay.set_default_size(340, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(16)
        box.set_margin_end(16)

        heading = Gtk.Label(label=_("Keyboard shortcuts"), xalign=0)
        heading.add_css_class("title-4")
        heading.set_margin_bottom(8)
        box.append(heading)

        for accel, action in self._shortcut_help_entries():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            accel_label = Gtk.Label(label=accel, xalign=0)
            accel_label.set_width_chars(26)
            action_label = Gtk.Label(label=action, xalign=0)
            row.append(accel_label)
            row.append(action_label)
            box.append(row)

        overlay.set_child(box)

        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_shortcut_overlay_key)
        overlay.add_controller(key)
        overlay._key = key  # headless tests synthesize Escape/F1 here
        overlay.connect("close-request", self._on_shortcut_overlay_close_request)

        self._shortcut_overlay = overlay
        overlay.present()
        return True

    def _on_shortcut_overlay_key(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_F1):
            self._close_shortcut_overlay()
            return True
        return False

    def _on_shortcut_overlay_close_request(self, _window: Gtk.Window) -> bool:
        self._close_shortcut_overlay()
        return True

    def _close_shortcut_overlay(self) -> None:
        overlay = self._shortcut_overlay
        if overlay is None:
            return
        self._shortcut_overlay = None
        overlay.destroy()
        self.webview.grab_focus()

    def _zoom(self, delta: float) -> bool:
        level = min(3.0, max(0.4, self.webview.get_zoom_level() + delta))
        self.webview.set_zoom_level(level)
        return True

    def _toggle_fullscreen(self) -> bool:
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()
        return True

    def _format_preview_uri(self, uri: str) -> str:
        current_uri = self.path.as_uri()
        if uri == current_uri:
            return "#top"
        if uri.startswith(current_uri + "#"):
            return uri[len(current_uri) :]
        return uri

    def _on_mouse_target_changed(
        self,
        _webview: WebKit.WebView,
        hit_test_result: WebKit.HitTestResult,
        _modifiers: int,
    ) -> None:
        if hit_test_result.context_is_link():
            uri = hit_test_result.get_link_uri()
            if uri:
                self._link_preview_label.set_text(self._format_preview_uri(uri))
                self._link_preview_revealer.set_reveal_child(True)
                return
        self._link_preview_revealer.set_reveal_child(False)

    def _sync_theme_with_gtk(self) -> None:
        if self.theme_id == "auto":
            return
        Gtk.Settings.get_default().set_property(
            "gtk-application-prefer-dark-theme",
            is_theme_dark(self.theme_id, fallback=False),
        )

    def reload(self) -> bool:
        """Re-render the file, preserving the current scroll position.

        The offset is read back into Python BEFORE the new document is
        loaded: a fresh document gets a fresh JS global object, so a value
        stashed on `window` (the old `__zeileScroll` approach) is gone by
        the time the restore runs -- and reading it asynchronously means
        the actual load_html must wait for that callback, not race it.
        """

        def _got_scroll(src: WebKit.WebView, result: Gio.AsyncResult, _u) -> None:
            try:
                raw = src.evaluate_javascript_finish(result).to_string() or "0"
                self._scroll_to_restore = int(float(raw))
            except Exception:
                self._scroll_to_restore = 0
            # Re-read the desktop dark preference on every render: for the
            # "Auto" theme it decides the Mermaid palette, and the system
            # preference can flip mid-session. Explicit themes override it
            # via is_theme_dark.
            self.dark = Gtk.Settings.get_default().get_property(
                "gtk-application-prefer-dark-theme"
            )
            html_doc, toc_tokens, code_texts = render(
                self.path,
                enable_mermaid=self.enable_mermaid,
                dark=self.dark,
                theme_id=self.theme_id,
                body_font_id=self.body_font_id,
                code_font_id=self.code_font_id,
                reading_width=self.reading_width,
            )
            try:
                raw_text = self.path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                raw_text = ""
            self._doc_stats = compute_document_stats(raw_text)
            self._toc_flat = flatten_toc(toc_tokens)
            self._code_texts = code_texts
            self._pending_restore_scroll = True
            self.webview.load_html(html_doc, self.path.as_uri())
            self._sync_theme_with_gtk()
            if self.toc_popover.get_visible():
                self._populate_toc()

        self.webview.evaluate_javascript(
            "window.scrollY | 0", -1, None, None, None, _got_scroll, None
        )
        return True

    def _watch(self) -> None:
        """(Re-)establish the file monitor for self.path.

        Safe to call again after navigate_to() switches documents -- cancels
        whatever monitor was watching the previous file first, so an edit to
        a document we've since navigated away from doesn't trigger a reload.
        """
        if self.monitor is not None:
            self.monitor.cancel()
        gfile = Gio.File.new_for_path(str(self.path))
        self.monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
        assert self.monitor is not None
        self.monitor.connect("changed", self._on_changed)

    def _on_changed(self, _monitor, _f, _other, event) -> None:
        if event not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            return
        # Editors write in bursts; coalesce them into a single reload.
        if self._reload_source is not None:
            GLib.source_remove(self._reload_source)
        self._reload_source = GLib.timeout_add(120, self._debounced_reload)

    def _debounced_reload(self) -> bool:
        self._reload_source = None
        self.reload()
        return GLib.SOURCE_REMOVE


class ZeileApp(Gtk.Application):
    def __init__(
        self,
        path: Path | None,
        *,
        enable_mermaid: bool,
        debug: bool,
        settings: dict[str, str],
        settings_path: Path,
        launch_sequence: bool = True,
    ) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.launch_sequence = launch_sequence
        self.path = path
        self.enable_mermaid = enable_mermaid
        self.debug = debug
        self.settings = settings
        self.settings_path = settings_path

    def do_activate(self) -> None:
        # Open the document immediately; the splash is a skippable overlay only.
        self._open_initial()
        if self.launch_sequence:
            play_launch_sequence(self, self.settings_path, lambda: None)

    def _open_initial(self) -> None:
        if self.path is None:
            # Launched without a file (app menu / launcher with no %f):
            # offer a picker instead of erroring out. Cancel = quit.
            dialog = Gtk.FileDialog()
            dialog.set_title(_("Open markdown file"))

            def chosen(d: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
                try:
                    gfile = d.open_finish(result)
                except GLib.Error:
                    self.quit()  # user cancelled
                    return
                self._present_path(Path(gfile.get_path()))

            dialog.open(None, None, chosen)
            return
        self._present_path(self.path)

    def _present_path(self, path: Path) -> None:
        Viewer(
            self,
            path,
            enable_mermaid=self.enable_mermaid,
            debug=self.debug,
            theme_id=self.settings["theme"],
            body_font_id=self.settings["body_font"],
            code_font_id=self.settings["code_font"],
            settings_path=self.settings_path,
        ).present()


def main() -> int:
    parser = argparse.ArgumentParser(description=_("Minimal GTK4 markdown viewer."))
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help=_("markdown file to display (omit to pick one in a dialog)"),
    )
    parser.add_argument(
        "--enable-mermaid",
        action="store_true",
        help=_(
            "render ```mermaid fences via mmdc (mermaid-cli); off by default "
            "so the base install needs no Node.js"
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=_("enable WebKit developer tools (same as setting ZEILE_DEBUG)"),
    )
    parser.add_argument(
        "--theme",
        choices=THEME_OPTIONS,
        default=None,
        help=_("start with a theme (saved selection is used otherwise)"),
    )
    parser.add_argument(
        "--body-font",
        choices=BODY_FONT_OPTIONS,
        default=None,
        help=_("body font selection (saved selection is used otherwise)"),
    )
    parser.add_argument(
        "--code-font",
        choices=CODE_FONT_OPTIONS,
        default=None,
        help=_("monospace/code font selection (saved selection is used otherwise)"),
    )

    args = parser.parse_args()

    if args.file is not None and not args.file.exists():
        print(f"zeile: no such file: {args.file}", file=sys.stderr)
        return 1

    debug = args.debug or bool(os.environ.get("ZEILE_DEBUG"))
    settings = load_settings()
    if args.theme is not None:
        settings["theme"] = _coerce_theme(args.theme)
    if args.body_font is not None:
        settings["body_font"] = _coerce_font(args.body_font, kind="body")
    if args.code_font is not None:
        settings["code_font"] = _coerce_font(args.code_font, kind="code")
    save_settings(settings)

    settings_path = _default_settings_path()
    return ZeileApp(
        args.file,
        enable_mermaid=args.enable_mermaid,
        debug=debug,
        settings=settings,
        settings_path=settings_path,
    ).run([])


if __name__ == "__main__":
    sys.exit(main())
