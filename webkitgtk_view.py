# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The Linux backend of `view.DocumentView`: a WebKitGTK 6.0 WebView."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import Gio, Gtk, WebKit  # noqa: E402

from view import Action, Decision  # noqa: E402


class WebKitGtkView:
    def __init__(self, *, debug: bool = False) -> None:
        # Ephemeral session: no cookie jar, no HTTP cache persisted to disk.
        # decide-policy below is what actually stops any request from being
        # made in the first place for anything but the local document's tree.
        session = WebKit.NetworkSession.new_ephemeral()
        self.widget = WebKit.WebView(network_session=session)
        settings = self.widget.get_settings()
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

        # Defaults are inert (and deny every navigation) until the shell sets them.
        self.on_navigation: Callable[[str], Decision] = lambda _u: Decision(Action.EXTERNAL)
        self.on_load_finished: Callable[[], None] = lambda: None
        self.on_hover_link: Callable[[str | None], None] = lambda _uri: None
        self.on_find_result: Callable[[int], None] = lambda _count: None

        self.widget.connect("decide-policy", self._on_decide_policy)
        self.widget.connect("load-changed", self._on_load_changed)
        self.widget.connect("mouse-target-changed", self._on_mouse_target_changed)
        self._finder = self.widget.get_find_controller()
        # failed-to-find-text is the reliable "zero matches" signal;
        # counted-matches does not fire on all builds, so found-text
        # (which fires on search()) carries the count.
        self._finder.connect("found-text", lambda _c, count: self.on_find_result(count))
        self._finder.connect("failed-to-find-text", lambda _c: self.on_find_result(0))

    @property
    def zoom(self) -> float:
        return self.widget.get_zoom_level()

    @zoom.setter
    def zoom(self, level: float) -> None:
        self.widget.set_zoom_level(level)

    def load_html(self, html: str, base_uri: str) -> None:
        self.widget.load_html(html, base_uri)

    def run_js(self, js: str) -> None:
        self.widget.evaluate_javascript(js, -1, None, None, None, None, None)

    def get_scroll_y(self, callback: Callable[[int], None]) -> None:
        def _done(src: WebKit.WebView, result: Gio.AsyncResult, _user_data) -> None:
            try:
                raw = src.evaluate_javascript_finish(result).to_string() or "0"
                y = int(float(raw))
            except Exception:
                y = 0
            callback(y)

        self.widget.evaluate_javascript(
            "window.scrollY | 0", -1, None, None, None, _done, None
        )

    def find(self, text: str) -> None:
        options = WebKit.FindOptions.CASE_INSENSITIVE | WebKit.FindOptions.WRAP_AROUND
        self._finder.search(text, options, 1000)

    def find_next(self) -> None:
        self._finder.search_next()

    def find_previous(self) -> None:
        self._finder.search_previous()

    def find_finish(self) -> None:
        self._finder.search_finish()

    def print_dialog(self, parent: Gtk.Window) -> None:
        WebKit.PrintOperation.new(self.widget).run_dialog(parent)

    def export_pdf(self, uri: str) -> None:
        settings = Gtk.PrintSettings()
        settings.set("output-uri", uri)
        settings.set("output-file-format", "pdf")
        op = WebKit.PrintOperation.new(self.widget)
        op.set_print_settings(settings)
        op.print_()

    def grab_focus(self) -> None:
        self.widget.grab_focus()

    def _on_decide_policy(
        self,
        _webview: WebKit.WebView,
        decision: WebKit.PolicyDecision,
        decision_type: WebKit.PolicyDecisionType,
    ) -> bool:
        if decision_type != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            decision.use()
            return True
        uri = decision.get_navigation_action().get_request().get_uri()
        if self.on_navigation(uri).action is Action.LOAD:
            decision.use()
        else:
            decision.ignore()
        return True

    def _on_load_changed(self, _webview: WebKit.WebView, event: WebKit.LoadEvent) -> None:
        if event == WebKit.LoadEvent.FINISHED:
            self.on_load_finished()

    def _on_mouse_target_changed(
        self, _webview: WebKit.WebView, hit: WebKit.HitTestResult, _modifiers: int
    ) -> None:
        self.on_hover_link(hit.get_link_uri() if hit.context_is_link() else None)
