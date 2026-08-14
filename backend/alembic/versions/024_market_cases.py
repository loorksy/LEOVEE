"""Case memory: what gold has looked like before, and what came next (M8).

**Platform-global, and that is the design.** A case is a fingerprint of a moment
on the shared candle store plus how the market resolved from it — a fact about
XAUUSD, identical for every workspace, exactly like `candles`, `structures` and
`price_zones` already are. Copying it per tenant would multiply storage by the
tenant count, and it would make the memory useless for months: a new workspace
would begin with no history of the *market*, not merely no history of its own
decisions.

That distinction is the whole point and it must not blur:

- **Market cases are shared.** "Gold has been in this structure 47 times" is
  objective, and every reader is entitled to it on day one.
- **Strategy statistics are per-workspace** (`strategy_stats`, RLS). "*Your*
  plans in this bucket won 61% of the time" is a fact about a workspace's own
  record, and borrowing someone else's would be the most expensive kind of wrong.

Nothing tenant-derived is stored here — no recommendation id, no workspace id,
no decision. Only candles in, and resolutions out.

The 8-dimension vector mirrors `fingerprint_vector`'s slot order and exists
purely as a **recall** device: pgvector narrows candidates cheaply, then the
exact weighted-L1 metric ranks them in process. The two are not the same metric
and must not be confused — cosine over these slots would call two moments alike
for pointing the same way regardless of magnitude, and the magnitudes are the
setup.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "024_market_cases"
down_revision: str | None = "023_outcome_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_cases",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "symbol_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("symbols.id"),
            nullable=False,
        ),
        sa.Column("timeframe", sa.String(8), nullable=False),
        # The moment being fingerprinted. Features come from bars at or before
        # it; resolutions from bars strictly after. Both halves are stored on one
        # row, which is precisely why the timestamp has to be explicit.
        sa.Column("case_ts", sa.DateTime(timezone=True), nullable=False),
        # --- the fingerprint (candles at or before case_ts) ---
        sa.Column("regime", sa.String(16), nullable=False),
        sa.Column("trend", sa.String(8), nullable=False),
        sa.Column("range_zone", sa.String(16), nullable=False),
        sa.Column("pullback_depth", sa.Float(), nullable=False),
        sa.Column("impulse_atr", sa.Float(), nullable=False),
        sa.Column("volatility", sa.Float(), nullable=False),
        sa.Column("session", sa.String(8), nullable=False),
        sa.Column("structure_run", sa.Integer(), nullable=False),
        # The ATR the resolutions were measured against, kept so a stored case
        # can be re-read without recomputing — and so a change to the ATR
        # definition is visible as a discontinuity rather than silently
        # reinterpreting every historical row.
        sa.Column("atr", sa.Float(), nullable=False),
        sa.Column("entry", sa.Float(), nullable=False),
        # --- what happened next, for each direction (bars strictly after) ---
        sa.Column("buy_resolution", sa.String(16), nullable=True),
        sa.Column("buy_bars", sa.Integer(), nullable=True),
        sa.Column("buy_net_r", sa.Float(), nullable=True),
        sa.Column("buy_mfe_atr", sa.Float(), nullable=True),
        sa.Column("buy_mae_atr", sa.Float(), nullable=True),
        sa.Column("sell_resolution", sa.String(16), nullable=True),
        sa.Column("sell_bars", sa.Integer(), nullable=True),
        sa.Column("sell_net_r", sa.Float(), nullable=True),
        sa.Column("sell_mfe_atr", sa.Float(), nullable=True),
        sa.Column("sell_mae_atr", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # One case per moment per frame. Re-indexing the same window must update
        # rather than duplicate, or a repeated sweep silently multiplies the
        # weight of whatever period it re-read.
        sa.UniqueConstraint("symbol_id", "timeframe", "case_ts", name="uq_market_case_moment"),
    )
    op.execute("ALTER TABLE market_cases ADD COLUMN embedding vector(8)")
    # The categorical prefilter the query narrows on before the vector search:
    # a case in a different trend is not a near miss, it is a different question.
    op.create_index(
        "ix_market_cases_lookup",
        "market_cases",
        ["symbol_id", "timeframe", "trend", "regime"],
    )
    op.execute(
        "CREATE INDEX ix_market_cases_embedding ON market_cases "
        "USING hnsw (embedding vector_l2_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_market_cases_embedding")
    op.drop_index("ix_market_cases_lookup", table_name="market_cases")
    op.drop_table("market_cases")
