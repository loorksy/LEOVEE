"""Revisions, activation rules and tradability on recommendations (M7).

**A revision records what an evaluation *declared*, not what is true now.** That
distinction is the reason the table exists rather than a status column being
overwritten. A recommendation that was READY at 09:14 and INVALIDATED at 09:31
has two facts in its history, and a user asking "why did this change" is asking
about the transition, not the endpoint.

The trap it creates is worth naming because it is easy to fall into: a card that
renders its badge from the **latest revision** shows a status that was true when
that revision was written, which is not the same as the row's current state — a
plan invalidated by the tracker after the last evaluation still shows READY. The
row is the live state; revisions are the history. Anything a user looks at reads
the row.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021_recommendation_revisions"
down_revision: str | None = "020_telegram_transport"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_revisions",
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
        # Monotonic per recommendation. Ordering by timestamp alone breaks when
        # two evaluations land in the same millisecond, which the tracker does.
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        # What this evaluation declared — a snapshot, not a pointer to the row.
        sa.Column("declared_status", sa.String(32), nullable=False),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("snapshot_json", sa.dialects.postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("changes_json", sa.dialects.postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.UniqueConstraint("recommendation_id", "seq", name="uq_recommendation_revision_seq"),
    )
    op.execute("ALTER TABLE recommendation_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recommendation_revisions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY recommendation_revisions_workspace_isolation ON recommendation_revisions
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

    # The live state a card reads. Kept on the row rather than derived from the
    # newest revision, so a tracker transition is visible immediately.
    op.add_column(
        "recommendations",
        sa.Column("activation_rule_json", sa.dialects.postgresql.JSONB(), nullable=True),
    )
    op.add_column("recommendations", sa.Column("activation_condition", sa.Text(), nullable=True))
    op.add_column(
        "recommendations", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "recommendations", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("recommendations", sa.Column("timeframe", sa.String(8), nullable=True))
    op.add_column("recommendations", sa.Column("plan_type", sa.String(16), nullable=True))
    # The third axis of the decision contract, persisted. It lived only in the
    # analysis payload, so "this plan is waiting on its trigger" survived the
    # response and nothing afterwards could tell it from a plan valid right now.
    op.add_column("recommendations", sa.Column("execution_state", sa.String(24), nullable=True))
    op.add_column("recommendations", sa.Column("tradability", sa.String(16), nullable=True))
    op.add_column("recommendations", sa.Column("tradability_reason", sa.Text(), nullable=True))
    op.add_column(
        "recommendations", sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The tracker polls "open and due"; without this it scans the table on every
    # tick of every workspace.
    op.create_index(
        "ix_recommendations_open_expiry",
        "recommendations",
        ["workspace_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_open_expiry", table_name="recommendations")
    for column in (
        "execution_state",
        "last_evaluated_at",
        "tradability_reason",
        "tradability",
        "plan_type",
        "timeframe",
        "expires_at",
        "activated_at",
        "activation_condition",
        "activation_rule_json",
    ):
        op.drop_column("recommendations", column)
    op.execute(
        "DROP POLICY IF EXISTS recommendation_revisions_workspace_isolation "
        "ON recommendation_revisions"
    )
    op.drop_table("recommendation_revisions")
