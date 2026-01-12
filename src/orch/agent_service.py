from __future__ import annotations

import shlex
from pathlib import Path
from typing import Optional

from .models import AgentRunSpec, ProviderConfig
from .tmux_service import TmuxService


class AgentServiceError(RuntimeError):
    pass


class AgentService:
    def __init__(self, tmux: TmuxService, prompt_dir: Path) -> None:
        self.tmux = tmux
        self.prompt_dir = prompt_dir

    def start_agent(
        self,
        pane_target: str,
        provider: ProviderConfig,
        run_spec: AgentRunSpec,
        prompt_file: Optional[Path],
    ) -> Optional[Path]:
        prompt_path = prompt_file
        if provider.prompt_mode in {"stdin", "file"}:
            prompt_path = prompt_path or self._write_prompt(run_spec.prompt, run_spec)
        command = self._render_command(provider, run_spec, prompt_path)
        self.tmux.send_keys(pane_target, command, enter=True)
        return prompt_path

    def stop_agent(self, pane_target: str) -> None:
        self.tmux.send_ctrl_c(pane_target)

    def _write_prompt(self, prompt: str, run_spec: AgentRunSpec) -> Path:
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        story_id = run_spec.env.get("STORY_ID", "task")
        prompt_path = self.prompt_dir / f"{story_id}.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        return prompt_path

    def _render_command(
        self,
        provider: ProviderConfig,
        run_spec: AgentRunSpec,
        prompt_path: Optional[Path],
    ) -> str:
        template = provider.start_command_template or ""
        model = run_spec.model
        prompt_text = run_spec.prompt
        prompt_file = str(prompt_path) if prompt_path else ""

        if provider.prompt_mode == "arg":
            if "{prompt}" in template:
                command = template.format(model=model, prompt=shlex.quote(prompt_text), prompt_file=prompt_file)
            else:
                base = template.format(model=model, prompt_file=prompt_file)
                command = f"{base} --prompt {shlex.quote(prompt_text)}"
            return command

        base = template.format(model=model, prompt_file=prompt_file)
        if provider.prompt_mode == "stdin":
            if not prompt_path:
                raise AgentServiceError("prompt file required for stdin mode")
            return f"cat {shlex.quote(str(prompt_path))} | {base}"
        if provider.prompt_mode == "file":
            return base
        raise AgentServiceError(f"unsupported prompt mode: {provider.prompt_mode}")
