"""Add portfolio snapshots table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-17 21:15:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("broker", sa.String(length=20), nullable=False),
        sa.Column("total_asset_krw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("purchase_amount_krw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cash_krw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("today_eval_pnl_krw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("today_eval_pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date", "broker", name="uq_portfolio_snapshots_date_broker"),
    )
    op.create_index(
        "ix_portfolio_snapshots_date_broker",
        "portfolio_snapshots",
        ["snapshot_date", "broker"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_date_broker", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
