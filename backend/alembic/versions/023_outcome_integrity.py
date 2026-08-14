"""One closed plan, one recorded outcome (M8).

Everything the learning loop concludes is an average over `outcome_records`, so
a duplicated row is not a cosmetic problem — it is a second vote from one event.
An adversarial audit found three independent ways to cast that second vote, and
all three were reproduced against a real database:

1. `thesis_monitor_service` transitions the thesis *and* its recommendation for
   a single market event, and both transitions fire the learning pipeline.
2. A terminal transition repeated — a retried PATCH, a user pressing the button
   after the tracker already closed the plan — re-fires it, because the state
   machine returns silently when the status is already what you asked for.
3. A manual transition racing the tracker: both read a non-terminal status, both
   decide, both record.

Only the third is a concurrency bug; the first two are ordinary flows. What they
share is that no *check in application code* can stop them — the first is two
correct calls, the second is a retry, and the third is a genuine race. So the
guarantee is placed where it holds under all three: a unique key in the database.

`dedupe_key` is that key. A recommendation-linked outcome keys on the
recommendation alone — a plan closes once, however many components notice.

`kind` separates two things that were being added together. A **plan** outcome
is the analysis being right or wrong, and it is what calibrates confidence. A
**trade** outcome is what the user did about it, self-reported (D4 — Leovee
places no orders). Counting a reported trade into the same win rate lets one
plan the user took twice move the statistics twice, and lets a plan they ignored
count once instead of not at all.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023_outcome_integrity"
down_revision: str | None = "022_reevaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "outcome_records",
        sa.Column("dedupe_key", sa.String(120), nullable=True),
    )
    op.add_column(
        "outcome_records",
        sa.Column("kind", sa.String(16), nullable=False, server_default="PLAN"),
    )

    # Backfill before the constraint. Existing rows predate the key, and a
    # NOT NULL added to a populated table without one fails outright.
    #
    # Duplicates that already exist are *kept* and given distinct keys from
    # their own id. Collapsing them here would silently rewrite recorded
    # history to make a new invariant look like it always held; the invariant
    # applies from now on, and the old rows stay visible as what they are.
    op.execute(
        """
        UPDATE outcome_records
           SET dedupe_key = CASE
                 WHEN recommendation_id IS NOT NULL THEN 'rec:' || recommendation_id::text
                 WHEN trade_id IS NOT NULL THEN 'trade:' || trade_id::text
                 WHEN thesis_id IS NOT NULL THEN 'thesis:' || thesis_id::text
                 ELSE 'legacy:' || id::text
               END
         WHERE dedupe_key IS NULL
        """
    )
    op.execute(
        """
        UPDATE outcome_records o
           SET dedupe_key = o.dedupe_key || ':dup:' || o.id::text
          FROM (
            SELECT id, row_number() OVER (
                     PARTITION BY workspace_id, dedupe_key ORDER BY recorded_at, id
                   ) AS rn
              FROM outcome_records
          ) ranked
         WHERE ranked.id = o.id AND ranked.rn > 1
        """
    )
    op.execute("UPDATE outcome_records SET kind = 'TRADE' WHERE trade_id IS NOT NULL")
    op.alter_column("outcome_records", "dedupe_key", nullable=False)

    # Scoped by workspace as well as key: two tenants may legitimately hold
    # rows whose keys collide only because ids are opaque, and a global unique
    # index would make one tenant's write fail on the other's data — a
    # cross-tenant coupling through a constraint.
    op.create_unique_constraint(
        "uq_outcome_record_dedupe", "outcome_records", ["workspace_id", "dedupe_key"]
    )
    op.alter_column("outcome_records", "kind", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_outcome_record_dedupe", "outcome_records", type_="unique")
    op.drop_column("outcome_records", "kind")
    op.drop_column("outcome_records", "dedupe_key")
