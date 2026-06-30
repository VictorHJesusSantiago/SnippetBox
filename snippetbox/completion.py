"""Scripts de autocompletar para bash, zsh e PowerShell.

Gerados estaticamente (sem dependencias). Instale com:
    snippetbox complete bash   >> ~/.bashrc
    snippetbox complete zsh    >> ~/.zshrc
    snippetbox complete powershell >> $PROFILE
"""

from __future__ import annotations

COMMANDS = [
    "add", "list", "search", "show", "copy", "cat", "run", "edit", "rm",
    "tags", "pin", "unpin", "history", "export", "import", "complete", "gui",
]

_BASH = """\
# SnippetBox completion (bash)
_snippetbox_complete() {
    local cur prev cmds
    cur="${COMP_WORDS[COMP_CWORD]}"
    cmds="%(cmds)s"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$cmds" -- "$cur") )
        return 0
    fi
    COMPREPLY=( $(compgen -W "$(snippetbox tags 2>/dev/null | tr -d '#')" -- "$cur") )
}
complete -F _snippetbox_complete snippetbox
"""

_ZSH = """\
# SnippetBox completion (zsh)
_snippetbox() {
    local -a cmds
    cmds=(%(cmds)s)
    if (( CURRENT == 2 )); then
        compadd -- $cmds
    else
        compadd -- ${(f)"$(snippetbox tags 2>/dev/null | tr -d '#')"}
    fi
}
compdef _snippetbox snippetbox
"""

_PWSH = """\
# SnippetBox completion (PowerShell)
Register-ArgumentCompleter -Native -CommandName snippetbox -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $cmds = @(%(pwsh_cmds)s)
    $cmds | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
"""


def script(shell: str) -> str:
    shell = shell.lower()
    cmds = " ".join(COMMANDS)
    if shell == "bash":
        return _BASH % {"cmds": cmds}
    if shell == "zsh":
        return _ZSH % {"cmds": cmds}
    if shell in ("powershell", "pwsh"):
        pwsh_cmds = ", ".join(f"'{c}'" for c in COMMANDS)
        return _PWSH % {"pwsh_cmds": pwsh_cmds}
    raise ValueError(f"shell desconhecido: {shell}")
