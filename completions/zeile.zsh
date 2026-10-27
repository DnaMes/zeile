#compdef zeile
# Theme and font ids mirrored from zeile.THEME_OPTIONS / BODY_FONT_OPTIONS /
# CODE_FONT_OPTIONS — kept in sync by tests/test_shell_integration.py.

_zeile() {
  local themes=(
    auto github-light github-dark
    catppuccin-latte catppuccin-frappe catppuccin-macchiato catppuccin-mocha
    solarized-light solarized-dark gruvbox-light gruvbox-dark
    nord dracula rose-pine rose-pine-dawn tokyo-night tokyo-night-day cyberpunk
  )
  local body_fonts=(system inter atkinson ia-writer noto-serif ibmplex-sans)
  local code_fonts=(system jetbrains-mono ia-writer fira-code cascadia-code)

  _arguments -s -S \
    '(-h --help)'{-h,--help}'[show help message and exit]' \
    '--enable-mermaid[render mermaid fences via mmdc]' \
    '--debug[enable WebKit developer tools]' \
    '--theme[start with a theme]:theme:('"${themes[*]}"')' \
    '--body-font[body font selection]:body font:('"${body_fonts[*]}"')' \
    '--code-font[monospace/code font selection]:code font:('"${code_fonts[*]}"')' \
    '*:markdown file:_files -g "*.md *.markdown"'
}

_zeile "$@"
