from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


@dataclass(frozen=True)
class PromptTemplate:
    env: Environment
    template_name: str

    def render(self, *, previous_context: str | None) -> str:
        template = self.env.get_template(self.template_name)
        return template.render(previous_context=previous_context)


def load_prompt_template(
    registry_dir: Path, name: str, template_file: str
) -> PromptTemplate:
    template_dir = registry_dir / name
    env = Environment(
        loader=FileSystemLoader(template_dir.as_posix()),
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return PromptTemplate(env=env, template_name=template_file)
