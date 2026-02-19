"""Initial schema creation for IB Trading Bot.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables for the bot."""

    # Bot Settings table
    op.create_table(
        'bot_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('buy_amount_usd', sa.Float(), nullable=False, server_default='300.0'),
        sa.Column('max_open_positions', sa.Integer(), nullable=False, server_default='200'),
        sa.Column('max_daily_buys', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('max_total_investment', sa.Float(), nullable=False, server_default='90000.0'),
        sa.Column('max_per_ticker', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('max_daily_loss', sa.Float(), nullable=False, server_default='5000.0'),
        sa.Column('min_cash_reserve', sa.Float(), nullable=False, server_default='1000.0'),
        sa.Column('is_paused', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_killed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('regular_hours_only', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('queue_outside_hours', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

    # Positions table
    op.create_table(
        'position',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('entry_amount_usd', sa.Float(), nullable=False),
        sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('entry_order_id', sa.String(50), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('exit_amount_usd', sa.Float(), nullable=True),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exit_order_id', sa.String(50), nullable=True),
        sa.Column('pnl_usd', sa.Float(), nullable=True),
        sa.Column('pnl_pct', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='OPEN'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_position_ticker', 'position', ['ticker'])
    op.create_index('ix_position_status', 'position', ['status'])
    op.create_index('ix_position_created_at', 'position', ['created_at'])

    # Trades table
    op.create_table(
        'trade',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('order_type', sa.String(10), nullable=False),
        sa.Column('requested_qty', sa.Float(), nullable=False),
        sa.Column('requested_amount_usd', sa.Float(), nullable=True),
        sa.Column('filled_qty', sa.Float(), nullable=True),
        sa.Column('avg_fill_price', sa.Float(), nullable=True),
        sa.Column('total_fill_amount_usd', sa.Float(), nullable=True),
        sa.Column('commission', sa.Float(), nullable=True, server_default='0'),
        sa.Column('ib_order_id', sa.String(50), nullable=True),
        sa.Column('ib_perm_id', sa.String(50), nullable=True),
        sa.Column('position_ids', sa.String(1000), nullable=True),
        sa.Column('total_pnl_usd', sa.Float(), nullable=True),
        sa.Column('alert_id', sa.String(100), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trade_ticker', 'trade', ['ticker'])
    op.create_index('ix_trade_side', 'trade', ['side'])
    op.create_index('ix_trade_status', 'trade', ['status'])
    op.create_index('ix_trade_created_at', 'trade', ['created_at'])

    # Alert Log table
    op.create_table(
        'alert_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(50), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('alert_id', sa.String(100), nullable=True),
        sa.Column('idempotency_key', sa.String(200), nullable=False, unique=True),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('source_ip', sa.String(50), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_log_ticker', 'alert_log', ['ticker'])
    op.create_index('ix_alert_log_action', 'alert_log', ['action'])
    op.create_index('ix_alert_log_idempotency_key', 'alert_log', ['idempotency_key'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('alert_log')
    op.drop_table('trade')
    op.drop_table('position')
    op.drop_table('bot_settings')
