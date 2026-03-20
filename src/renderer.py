"""Render the tailored resume context into LaTeX using Jinja2."""

import os
import re

import jinja2

import config


def latex_escape(text: str) -> str:
    """Escape special LaTeX characters, skipping already-escaped sequences."""
    if not isinstance(text, str):
        return str(text)
    # Use negative lookbehind to skip characters already preceded by a backslash
    text = re.sub(r'(?<!\\)%', r'\\%', text)
    text = re.sub(r'(?<!\\)&', r'\\&', text)
    text = re.sub(r'(?<!\\)\$', r'\\$', text)
    text = re.sub(r'(?<!\\)#', r'\\#', text)
    text = re.sub(r'(?<!\\)_', r'\\_', text)
    return text


def _make_env() -> jinja2.Environment:
    """Create Jinja2 environment with LaTeX-safe delimiters."""
    loader = jinja2.FileSystemLoader(config.TEMPLATES_DIR)
    env = jinja2.Environment(
        loader=loader,
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
    )
    env.filters["latex_escape"] = latex_escape
    return env


def render(context: dict) -> str:
    """Render the resume template with the given context. Returns LaTeX string."""
    env = _make_env()
    template = env.get_template("resume.tex.j2")
    return template.render(**context)
