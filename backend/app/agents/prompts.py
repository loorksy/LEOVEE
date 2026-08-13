"""The prompt registry: prompts as versioned, content-hashed files.

Prompts here are **files on disk**, not string literals in Python. Three
consequences follow, and each is why:

**Every run records which prompt produced it.** ``prompt_hash`` is the SHA-256
of the exact text sent. Without it the learning loop (M8) attributes outcomes to
decisions it cannot identify — a calibration curve built across a prompt change
is measuring two different analysts as one, and the noise looks like a signal.

**Editing a prompt is a reviewable diff.** A literal buried in a function is
changed silently; a file is changed in a commit, with a reason.

**Skills load lazily.** The atlas is 200 lines of reference. Attaching it to
every call spends the token budget on material most runs never consult, so a
skill is a named body of knowledge loaded only when the run needs it.

The registry is read-only at runtime and caches by path: prompts change between
deploys, never between requests.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "PROMPTS_ROOT",
    "Prompt",
    "PromptNotFound",
    "load_prompt",
    "load_skill",
    "constitution",
    "available_prompts",
    "available_skills",
    "render",
]

PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts"

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


class PromptNotFound(LookupError):
    """A prompt was requested by a name that is not on disk.

    Raised rather than returning an empty string: a missing prompt must stop the
    run. Silently sending an empty system prompt produces an unguided model with
    no constitution at all, which is the single worst failure this layer has.
    """


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    body: str
    #: SHA-256 of the body, stable across machines and deploys.
    hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return str(self.metadata.get("version", "0.0.0"))

    @property
    def short_hash(self) -> str:
        return self.hash[:12]


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a leading ``---`` block off the body.

    Deliberately a flat key/value reader rather than a YAML parser: the metadata
    is a handful of scalars and lists, and pulling in a YAML dependency to read
    ``version: 1.0.0`` would let arbitrary structure into a file whose whole
    purpose is to be reviewable at a glance.
    """
    match = _FRONTMATTER.match(text)
    if match is None:
        return {}, text
    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            meta[key.strip()] = [item for item in items if item]
        else:
            meta[key.strip()] = value.strip('"').strip("'")
    return meta, text[match.end() :]


def _read(path: Path, name: str) -> Prompt:
    if not path.is_file():
        raise PromptNotFound(f"no prompt at {path}")
    text = path.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(text)
    body = body.strip()
    if not body:
        raise PromptNotFound(f"prompt {name!r} is empty")
    return Prompt(
        name=name,
        body=body,
        # The BODY is hashed, not the file: reordering frontmatter or fixing a
        # typo in a tag must not read as a changed prompt, because the model
        # never saw the frontmatter.
        hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        metadata=metadata,
    )


@lru_cache(maxsize=64)
def load_prompt(name: str) -> Prompt:
    """Load ``system/constitution`` or ``stages/structure`` by slash-path name."""
    if ".." in name or name.startswith("/"):
        raise PromptNotFound(f"illegal prompt name {name!r}")
    return _read(PROMPTS_ROOT / f"{name}.md", name)


@lru_cache(maxsize=32)
def load_skill(name: str) -> Prompt:
    """Load ``prompts/skills/<name>/SKILL.md``, on demand and never eagerly."""
    if "/" in name or ".." in name:
        raise PromptNotFound(f"illegal skill name {name!r}")
    return _read(PROMPTS_ROOT / "skills" / name / "SKILL.md", f"skills/{name}")


def constitution() -> Prompt:
    return load_prompt("system/constitution")


def available_prompts() -> list[str]:
    root = PROMPTS_ROOT
    return sorted(
        str(path.relative_to(root).with_suffix("")).replace("\\", "/")
        for path in root.rglob("*.md")
        if path.name != "SKILL.md"
    )


def available_skills() -> list[str]:
    skills = PROMPTS_ROOT / "skills"
    if not skills.is_dir():
        return []
    return sorted(p.parent.name for p in skills.glob("*/SKILL.md"))


def render(prompt: Prompt, **values: Any) -> str:
    """Fill ``{{ placeholder }}`` slots.

    An unfilled placeholder raises. A prompt that reaches the model still saying
    ``{{ symbol }}`` is a bug that produces confident nonsense rather than an
    error, and it is invisible in the output.
    """
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            missing.append(key)
            return match.group(0)
        return str(values[key])

    filled = _PLACEHOLDER.sub(substitute, prompt.body)
    if missing:
        raise KeyError(
            f"prompt {prompt.name!r} has unfilled placeholders: {', '.join(sorted(set(missing)))}"
        )
    return filled
