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
            'init:init repository config'
            'new:create a worktree'
            'add:add existing branch'
            'open:open a worktree'
            'purpose:set worktree purpose'
            'runs:list worktree runs'
            'locks:list worktree locks'
            'bootstrap:bootstrap worktree'
            'ls:list worktrees'
            'sync:sync worktree branch'
            'land:land worktree branch'
            'lock:lock a worktree'
            'unlock:unlock a worktree'
            'run:run command in worktree'
            'rm:remove a worktree'
            'reindex:rebuild cache'
            'doctor:check worktree health'
            'api:start api server'
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
                init)
                  _arguments
                  ;;
                new)
                  _arguments \
                    '1:name:' \
                    '--base[base ref]:ref:' \
                    '--profile[profile name]:profile:' \
                    '--open[open after create]' \
                    '--bootstrap[bootstrap after create]' \
                    '--purpose[purpose text]:text:'
                  ;;
                add)
                  _arguments \
                    '1:name:' \
                    '--branch[branch ref]:ref:' \
                    '--profile[profile name]:profile:' \
                    '--open[open after add]' \
                    '--bootstrap[bootstrap after add]' \
                    '--purpose[purpose text]:text:'
                  ;;
                open)
                  _arguments \
                    '1:name:($(_wt_tasks))' \
                    '--layout[tmux layout]:layout:' \
                    '--editor[open editor]' \
                    '--no-editor[skip editor]'
                  ;;
                purpose)
                  _arguments \
                    '1:name:($(_wt_tasks))' \
                    '--clear[clear purpose]' \
                    '2:purpose:'
                  ;;
                runs)
                  _arguments \
                    '1:name:($(_wt_tasks))' \
                    '--limit[limit results]:count:'
                  ;;
                locks)
                  _arguments
                  ;;
                bootstrap)
                  _arguments '1:name:($(_wt_tasks))'
                  ;;
                ls)
                  _arguments '--json[json output]'
                  ;;
                sync)
                  _arguments \
                    '1:name:($(_wt_tasks))' \
                    '--strategy[merge or rebase]:strategy:(rebase merge)' \
                    '--from[base ref]:ref:'
                  ;;
                land)
                  _arguments \
                    '1:name:($(_wt_tasks))' \
                    '--strategy[merge or rebase]:strategy:(merge rebase)' \
                    '--run-checks[run checks]' \
                    '--cleanup[cleanup after land]'
                  ;;
                lock)
                  _arguments '1:name:($(_wt_tasks))' '--reason[lock reason]:reason:'
                  ;;
                unlock)
                  _arguments '1:name:($(_wt_tasks))'
                  ;;
                run)
                  _arguments \
                    '1:name:($(_wt_tasks))' \
                    '--lock-on-run[lock worktree while command runs]' \
                    '--artifacts[artifacts directory]:dir:_files -/' \
                    '--[end of wt args]' \
                    '*:command and args:->cmd'
                  ;;
                rm)
                  _arguments '1:name:($(_wt_removable_tasks))' '--force[force removal]'
                  ;;
                reindex)
                  _arguments
                  ;;
                doctor)
                  _arguments
                  ;;
                api)
                  _arguments \
                    '--host[host]:host:' \
                    '--port[port]:port:' \
                    '--reload[reload server]'
                  ;;
                tui)
                  _arguments
                  ;;
              esac
              ;;
          esac
        }

        # Dynamic task-id completion from `wt ls --json` using python3
        _wt_tasks() {
          local data
          if command -v python3 >/dev/null 2>&1; then
            data=$(wt ls --json 2>/dev/null)
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
            data=$(wt ls --json 2>/dev/null)
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
