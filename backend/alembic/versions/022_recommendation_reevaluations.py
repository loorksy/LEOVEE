"""The re-evaluation ledger (M7).

**Every trigger is recorded, admitted or not.** "Why was this re-decided" and
"why was this *not* re-decided" are both questions an operator asks, and a table
that only holds the cycles that ran can answer the first. A suppressed trigger —
cooled down, capped, duplicated — is a fact about the plan's history, so it gets
a row with the reason it went nowhere.

**A cycle that confirmed the plan is a real outcome.** "The market moved, the
agent looked again, and it stood by the plan" is different information from
"nobody looked", and someone who cannot tell those apart cannot trust either.
`confirmed` writes a row and no revision.

**`dedupe_key` is the idempotency.** Sweeps overlap, a worker retries, two
tenants' cycles interleave. The unique constraint over (recommendation_id,
dedupe_key) makes a repeated write a no-op instead of a second model call —
which is the actual cost being bounded here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022_reevaluations"
down_revision: str | None = "021_recommendation_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_reevaluations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recommendation_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("reason", sa.String(48), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        # Which component noticed. Never the decider: a trigger is a request for
        # a decision cycle, and only the cycle's output may change a plan.
        sa.Column("source", sa.String(16), nullable=False),
        # The revision in force when it was raised, so a stale trigger — one
        # raised against a plan that has since been revised — is recognisable
        # rather than being applied to a plan it was never about.
        sa.Column("revision_seq", sa.Integer(), nullable=True),
        # requested | suppressed | confirmed | revised | invalidated | skipped
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=True),
        sa.Column(
            "trigger_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "decision_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "recommendation_id", "dedupe_key", name="uq_recommendation_reevaluation_dedupe"
        ),
    )
    # The admission check reads "automatic cycles for this plan, newest first".
    op.create_index(
        "ix_reevaluations_plan_raised",
        "recommendation_reevaluations",
        ["recommendation_id", "raised_at"],
    )
    op.execute("ALTER TABLE recommendation_reevaluations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_reevaluations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY recommendation_reevaluations_workspace_isolation
        ON recommendation_reevaluations
        USING (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            AND workspace_id = current_setting('app.workspace_id', true)::uuid
        )
        WITH CHECK (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            AND workspace_id = current_setting('app.workspace_id', true)::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS recommendation_reevaluations_workspace_isolation "
        "ON recommendation_reevaluations"
    )
    op.drop_index("ix_reevaluations_plan_raised", table_name="recommendation_reevaluations")
    op.drop_table("recommendation_reevaluations")
