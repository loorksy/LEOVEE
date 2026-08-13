# 0001 — AiChart is ported into Leovee, not the other way round

**Status:** accepted · **Supersedes:** `LEOVEE_SPEC.md` §0 (greenfield rule)

## Context

`loorksy/AiChart` (internally "Lonora") is a working production Forex analysis
platform: roughly 196,600 lines of TypeScript, 169 API routes, 68 tables, and
227 test files. Leovee was specified and built as a greenfield rebuild of the
same product, on FastAPI + SQLAlchemy + Postgres + React/Vite.

§0 of the specification states there is no existing repository, no legacy system
to migrate, and that no migration plan should be produced. Two consequences
followed. Leovee's architecture is genuinely better in the places the
specification concentrated on — real Postgres RLS, forced and non-bypassable,
with an organization/workspace hierarchy AiChart has no equivalent of. And its
analytical engines were written against prose rather than ported from a working
implementation, leaving `backend/app/engines/` as 656 lines of placeholders,
some of which fabricated evidence.

## Decision

Leovee's architecture is final. AiChart is the reference implementation that the
domain logic is ported *from*, rewritten in Python rather than transplanted.

The deciding factor is tenancy. AiChart scopes rows with a `user_id` column and
a manual `WHERE` clause in every query — no RLS, no organization or workspace
entity. Leovee enforces isolation in the database, with `FORCE ROW LEVEL
SECURITY`, a runtime role that is neither superuser nor `BYPASSRLS`, and session
GUCs bound only after a membership check. Moving the intelligence into the
isolation is tractable; moving the isolation into the intelligence would mean
retrofitting a tenancy model through 68 tables and ~90 data-access functions.

## Consequences

- Ported repository functions take **no tenant parameter at all**. AiChart's
  `canonical/repository.ts` threads `userId` through 630 lines of manual
  filters; porting that signature would port the bug class with it. In Leovee a
  data-access function must be incapable of expressing a cross-tenant query.
- Deterministic logic is pinned to the reference implementation's output rather
  than reviewed into correctness — see `docs/PORTING.md`.
- The AiChart tree stays read-only. Nothing is committed or pushed there.
