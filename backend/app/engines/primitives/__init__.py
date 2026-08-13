"""Deterministic primitives ported from AiChart.

Everything under here is a pure function over bars: no I/O, no LLM, no session.
That is what makes them pinnable to the reference implementation
(docs/PORTING.md), and the conformance test asserts this package never imports
from app.providers.llm.
"""
