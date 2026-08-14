"""Conformance guards for the AiChart migration.

These tests do not test a feature. They test a *property* of the codebase that
must hold at every phase of the migration (docs/AICHART_MIGRATION_PLAN.md M0):

- every workspace-scoped table is actually protected by RLS;
- the protection provably works across two workspaces;
- the subsystems ruled out by owner decisions D3, D4, D5 and D7 stay absent.

They are enumerated from SQLAlchemy metadata and the source tree rather than
hand-listed, so tables and modules added by later phases are covered without
anyone remembering to update a list.
"""
