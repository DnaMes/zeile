# zeile-installer-owned
# fish completion for zeile
# Theme and font ids mirrored from zeile.THEME_OPTIONS / BODY_FONT_OPTIONS /
# CODE_FONT_OPTIONS — kept in sync by tests/test_shell_integration.py.
# Long options: --enable-mermaid --debug --theme --body-font --code-font --help

complete -c zeile -f
complete -c zeile -s h -l help -d 'Show help message and exit'
complete -c zeile -l enable-mermaid -d 'Render mermaid fences via mmdc'
complete -c zeile -l debug -d 'Enable WebKit developer tools'
complete -c zeile -l theme -x -a 'auto github-light github-dark catppuccin-latte catppuccin-frappe catppuccin-macchiato catppuccin-mocha solarized-light solarized-dark gruvbox-light gruvbox-dark nord dracula rose-pine rose-pine-dawn tokyo-night tokyo-night-day cyberpunk' -d 'Start with a theme'
complete -c zeile -l body-font -x -a 'system inter atkinson ia-writer noto-serif ibmplex-sans' -d 'Body font selection'
complete -c zeile -l code-font -x -a 'system jetbrains-mono ia-writer fira-code cascadia-code' -d 'Monospace/code font selection'
complete -c zeile -a '(__fish_complete_suffix .md)'
complete -c zeile -a '(__fish_complete_suffix .markdown)'
