from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from homesrvctl.models import RenderContext


def template_root() -> Path:
    return Path(__file__).resolve().parent


def build_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_root())),
        autoescape=select_autoescape(enabled_extensions=("html", "xml")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(template_name: str, context: RenderContext | dict[str, object]) -> str:
    env = build_environment()
    template = env.get_template(template_name)
    payload = asdict(context) if isinstance(context, RenderContext) else context
    return template.render(**payload).rstrip() + "\n"
