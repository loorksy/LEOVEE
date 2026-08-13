"""The prompt registry: files, hashes, skills, and the constitution's own rules.

The constitution is tested like code because it behaves like code — it is the
single largest determinant of what the product says, and a clause quietly
dropped in an edit changes every answer with nothing failing.
"""

from __future__ import annotations

import pytest

from app.agents.prompts import (
    PROMPTS_ROOT,
    Prompt,
    PromptNotFound,
    available_prompts,
    available_skills,
    constitution,
    load_prompt,
    load_skill,
    render,
)
from app.engines.geometry.types import PatternStage, PatternType

pytestmark = pytest.mark.no_db


def test_the_constitution_loads_and_is_substantial() -> None:
    doc = constitution()
    assert doc.version == "1.0.0"
    assert len(doc.body) > 2_000
    assert len(doc.hash) == 64


def test_the_hash_covers_the_body_and_not_the_frontmatter() -> None:
    """Editing a tag must not read as a changed prompt: the model never saw it."""
    doc = constitution()
    same_body = Prompt(name="x", body=doc.body, hash=doc.hash)
    assert same_body.hash == doc.hash
    assert doc.short_hash == doc.hash[:12]


def test_a_missing_prompt_raises_rather_than_returning_empty() -> None:
    """An empty system prompt is an unguided model, which is the worst failure."""
    with pytest.raises(PromptNotFound):
        load_prompt("system/does_not_exist")
    with pytest.raises(PromptNotFound):
        load_skill("no-such-skill")


@pytest.mark.parametrize("name", ["../secrets", "/etc/passwd", "system/../../x"])
def test_prompt_names_cannot_escape_the_prompts_directory(name: str) -> None:
    with pytest.raises(PromptNotFound):
        load_prompt(name)


def test_every_prompt_on_disk_parses() -> None:
    names = available_prompts()
    assert "system/constitution" in names
    for name in names:
        assert load_prompt(name).body


def test_placeholders_must_all_be_filled() -> None:
    """A prompt reaching the model still saying {{ symbol }} is invisible nonsense."""
    stage = load_prompt("stages/analysis")
    with pytest.raises(KeyError, match="unfilled placeholders"):
        render(stage, symbol="XAUUSD")
    filled = render(stage, symbol="XAUUSD", evidence="{}")
    assert "{{" not in filled
    assert "XAUUSD" in filled


# --- the constitution's non-negotiables --------------------------------------


@pytest.mark.parametrize(
    "clause",
    [
        "NO_TRADE",  # the operational-failure rule exists
        "شراء",  # a direction is always required
        "بيع",
        "M15",  # the scalp range is named
        "H4",  # context frames survive
        "كنس",  # a wick through a level is a sweep, not a break
    ],
)
def test_the_constitution_still_states_its_load_bearing_rules(clause: str) -> None:
    """A clause dropped in an edit changes every answer and fails nothing else."""
    assert clause in constitution().body


def test_the_constitution_forbids_claiming_statistics_it_does_not_have() -> None:
    assert "بلا دعم إحصائي" in constitution().body


def test_the_threshold_lives_in_the_atlas_and_the_principle_in_the_constitution() -> None:
    """Deliberate division of labour, and worth pinning.

    The constitution states rules that never change with a tuning pass — a wick
    is a sweep, not a break. The atlas carries the number that implements it
    (0.25xATR). Putting the constant in the constitution would mean editing the
    document the whole product is judged against every time a threshold moves.
    """
    assert "0.25" not in constitution().body
    assert "0.25" in load_skill("pattern-atlas").body


# --- skills ------------------------------------------------------------------


def test_both_skills_are_present_and_load_lazily() -> None:
    assert set(available_skills()) == {"pattern-atlas", "trading-lexicon"}
    atlas = load_skill("pattern-atlas")
    assert atlas.metadata["name"] == "pattern-atlas"
    assert len(atlas.body) > 2_000


@pytest.mark.parametrize("pattern", list(PatternType))
def test_the_atlas_names_every_pattern_the_engine_can_emit(pattern: PatternType) -> None:
    """The atlas and the detector are one vocabulary, or the model is taught
    about shapes it will never be shown — and shown shapes it was never taught."""
    assert pattern.value in load_skill("pattern-atlas").body


@pytest.mark.parametrize("stage", list(PatternStage))
def test_the_atlas_explains_every_stage(stage: PatternStage) -> None:
    assert stage.value in load_skill("pattern-atlas").body


def test_skills_live_beside_the_prompts_and_are_not_loaded_eagerly() -> None:
    """`available_prompts` must not sweep skill bodies into every call."""
    assert (PROMPTS_ROOT / "skills").is_dir()
    assert not any(name.startswith("skills/") for name in available_prompts())
