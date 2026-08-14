"""Seed XAUUSD and drop any symbol outside the allowlist.

Leovee analyses gold only (ADR 0007). The symbols table previously filled
itself on demand from whatever a caller asked for, deriving base and quote by
slicing the ticker and leaving pip_location at its default of 4 — a positive
exponent, when OANDA's convention is negative, so every pip-derived number
would have been off by eight orders of magnitude had anything read it yet.

This seeds gold with correct metadata and removes rows for instruments the
platform no longer admits. Deleting cascades to their candles, which is the
intent: keeping candle history for instruments that can never be analysed again
costs storage and leaves the door open for a stale symbol to be resurrected by
a lookup that predates the allowlist.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "018_seed_gold_symbol"
down_revision: str | None = "017_watchlist_items_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GOLD = {
    "code": "XAUUSD",
    "base_currency": "XAU",
    "quote_currency": "USD",
    "asset_class": "METAL",
    "pip_location": -2,
}


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO symbols
                (id, code, base_currency, quote_currency, asset_class,
                 pip_location, is_active, provider_mappings_json)
            VALUES
                (gen_random_uuid(), :code, :base_currency, :quote_currency,
                 :asset_class, :pip_location, true, '{"oanda": "XAU_USD"}')
            ON CONFLICT (code) DO UPDATE SET
                base_currency = EXCLUDED.base_currency,
                quote_currency = EXCLUDED.quote_currency,
                asset_class = EXCLUDED.asset_class,
                pip_location = EXCLUDED.pip_location,
                is_active = true,
                provider_mappings_json = EXCLUDED.provider_mappings_json
            """
        ).bindparams(**GOLD)
    )
    op.execute(sa.text("DELETE FROM symbols WHERE code <> :code").bindparams(code=GOLD["code"]))


def downgrade() -> None:
    # The seeded row is left in place. Removing it would cascade to every candle
    # and every artifact keyed on gold, which is a far larger action than
    # reversing a seed, and nothing else in this migration needs undoing.
    pass
