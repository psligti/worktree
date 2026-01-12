from __future__ import annotations

import os
import textwrap


def zsh_completion_script() -> str:
    return textwrap.dedent(
        """\
        #compdef wt

        _wt() {
          local -a subcommands
          subcommands=(
            'create:create a worktree'
            'list:list worktrees'
            'show:show worktree details'
            'path:print worktree path'
            'lock:lock a worktree'
            'unlock:unlock a worktree'
            'remove:remove a worktree'
            'prune:prune stale worktrees'
            'repair:repair worktrees'
            'run:run command in worktree'
            'completion:print completion script'
            'tui:open TUI'
          )

          _arguments -C \
            '1:command:->cmds' \
            '*::args:->args'

          case $state in
            cmds)
              _describe 'command' subcommands
              return
              ;;
            args)
              case $words[1] in
                create)
                  _arguments \
                    '1:task-id:' \
                    '--base[base ref]:ref:' \
                    '--branch[branch name]:name:' \
                    '--path[worktree path]:dir:_files -/' \
                    '--detached[create detached worktree]' \
                    '--lock[lock worktree after create]' \
                    '--reason[lock reason]:reason:' \
                    '--json[json output]'
                  ;;
                list)
                  _arguments \
                    '--porcelain[porcelain output]' \
                    '--json[json output]' \
                    '--verbose[verbose output]'
                  ;;
                show)
                  _arguments '1:task-id:($(_wt_tasks))' '--json[json output]'
                  ;;
                path)
                  _arguments '1:task-id:($(_wt_tasks))'
                  ;;
                lock)
                  _arguments '1:task-id:($(_wt_tasks))' '--reason[lock reason]:reason:'
                  ;;
                unlock)
                  _arguments '1:task-id:($(_wt_tasks))'
                  ;;
                remove)
                  _arguments '1:task-id:($(_wt_removable_tasks))' '--force[force removal]'
                  ;;
                prune)
                  _arguments '--dry-run[show prune results only]'
                  ;;
                repair)
                  _arguments '1:task-id:($(_wt_tasks))' '--all[repair all worktrees]'
                  ;;
                run)
                  _arguments \
                    '1:task-id:($(_wt_tasks))' \
                    '--lock-on-run[lock worktree while command runs]' \
                    '--artifacts[artifacts directory]:dir:_files -/' \
                    '--json[json output]' \
                    '--[end of wt args]' \
                    '*:command and args:->cmd'
                  ;;
                completion)
                  _arguments '1:format:(zsh)'
                  ;;
                tui)
                  _arguments
                  ;;
              esac
              ;;
          esac
        }

        # Dynamic task-id completion from `wt list --json` using python3
        _wt_tasks() {
          local data
          if command -v python3 >/dev/null 2>&1; then
            data=$(wt list --json 2>/dev/null)
            python3 - <<'PY' "$data"
        import json
        import sys
        try:
            data = json.loads(sys.argv[1])
            for item in data:
                print(item.get("task_id", ""))
        except Exception:
            pass
        PY
          fi
        }

        # Optionally exclude locked worktrees from remove unless --force
        _wt_removable_tasks() {
          local data
          if command -v python3 >/dev/null 2>&1; then
            data=$(wt list --json 2>/dev/null)
            python3 - <<'PY' "$data"
        import json
        import sys
        try:
            data = json.loads(sys.argv[1])
            for item in data:
                if not item.get("locked", False):
                    print(item.get("task_id", ""))
        except Exception:
            pass
        PY
          fi
        }

        _wt "$@"
        """
    )


def oh_my_zsh_custom_dir() -> str:
    custom = os.environ.get("ZSH_CUSTOM")
    if custom:
        return custom
    return os.path.expanduser("~/.oh-my-zsh/custom")


def install_oh_my_zsh_completion(target_dir: str | None = None) -> str:
    base_dir = target_dir or oh_my_zsh_custom_dir()
    plugin_dir = os.path.join(base_dir, "plugins", "wt")
    os.makedirs(plugin_dir, exist_ok=True)

    plugin_path = os.path.join(plugin_dir, "wt.plugin.zsh")
    completion_path = os.path.join(plugin_dir, "_wt")

    with open(plugin_path, "w", encoding="utf-8") as handle:
        handle.write("fpath=(${0:A:h} $fpath)\n")

    with open(completion_path, "w", encoding="utf-8") as handle:
        handle.write(zsh_completion_script())

    return plugin_dir
