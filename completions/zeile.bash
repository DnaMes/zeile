# zeile-installer-owned
# shellcheck disable=SC2207  # the -W word lists are fixed, glob-free ids
# bash completion for zeile
# Theme and font ids mirrored from zeile.THEME_OPTIONS / BODY_FONT_OPTIONS /
# CODE_FONT_OPTIONS — kept in sync by tests/test_shell_integration.py.

_zeile() {
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD - 1]}"

    local themes="auto github-light github-dark catppuccin-latte catppuccin-frappe catppuccin-macchiato catppuccin-mocha solarized-light solarized-dark gruvbox-light gruvbox-dark nord dracula rose-pine rose-pine-dawn tokyo-night tokyo-night-day cyberpunk vscode-dark one-dark monokai"
    local body_fonts="system inter atkinson ia-writer noto-serif ibmplex-sans"
    local code_fonts="system jetbrains-mono ia-writer fira-code cascadia-code"
    local opts="--enable-mermaid --debug --theme --body-font --code-font --help -h"

    case "${prev}" in
        --theme)
            COMPREPLY=($(compgen -W "${themes}" -- "${cur}"))
            return 0
            ;;
        --body-font)
            COMPREPLY=($(compgen -W "${body_fonts}" -- "${cur}"))
            return 0
            ;;
        --code-font)
            COMPREPLY=($(compgen -W "${code_fonts}" -- "${cur}"))
            return 0
            ;;
    esac

    if [[ ${cur} == -* ]]; then
        COMPREPLY=($(compgen -W "${opts}" -- "${cur}"))
        return 0
    fi

    # Literal completion for names with spaces, quotes and glob characters: read the
    # candidates line by line (no word splitting, no pathname expansion), keep
    # directories (to descend into) and .md / .markdown files.
    compopt -o filenames 2>/dev/null || true
    local -a candidates=()
    local candidate
    mapfile -t candidates < <(compgen -f -- "${cur}")
    for candidate in "${candidates[@]}"; do
        if [[ -d ${candidate} ]]; then
            COMPREPLY+=("${candidate}")
        else
            case "${candidate,,}" in
                *.md | *.markdown) COMPREPLY+=("${candidate}") ;;
            esac
        fi
    done
}

complete -F _zeile zeile
