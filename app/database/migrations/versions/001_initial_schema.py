"""Initial schema creation for IB Trading Bot.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables for the bot."""
    position_status = sa.Enum("OPEN", "CLOSED", name="positionstatus")
    trade_side = sa.Enum("BUY", "SELL", name="tradeside")
    trade_status = sa.Enum(
        "PENDING",
        "FILLED",
        "PARTIAL",
        "CANCELLED",
        "FAILED",
        name="tradestatus",
    )

    bind = op.get_bind()
    position_status.create(bind, checkfirst=True)
    trade_side.create(bind, checkfirst=True)
    trade_status.create(bind, checkfirst=True)

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
        'positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('entry_amount_usd', sa.Float(), nullable=False),
        sa.Column('entry_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('exit_amount_usd', sa.Float(), nullable=True),
        sa.Column('exit_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pnl_usd', sa.Float(), nullable=True),
        sa.Column('pnl_pct', sa.Float(), nullable=True),
        sa.Column('status', position_status, nullable=False, server_default='OPEN'),
        sa.Column('entry_order_id', sa.Integer(), nullable=True),
        sa.Column('exit_order_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_positions_ticker', 'positions', ['ticker'])
    op.create_index('ix_positions_status', 'positions', ['status'])
    op.create_index('ix_positions_ticker_status', 'positions', ['ticker', 'status'])

    # Trades table
    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('side', trade_side, nullable=False),
        sa.Column('order_type', sa.String(10), nullable=False, server_default='MKT'),
        sa.Column('requested_qty', sa.Float(), nullable=True),
        sa.Column('filled_qty', sa.Float(), nullable=True),
        sa.Column('requested_amount_usd', sa.Float(), nullable=True),
        sa.Column('avg_fill_price', sa.Float(), nullable=True),
        sa.Column('total_fill_amount_usd', sa.Float(), nullable=True),
        sa.Column('commission', sa.Float(), nullable=True),
        sa.Column('ib_order_id', sa.Integer(), nullable=True),
        sa.Column('ib_perm_id', sa.Integer(), nullable=True),
        sa.Column('status', trade_status, nullable=False, server_default='PENDING'),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('position_ids', sa.String(2000), nullable=True),
        sa.Column('total_pnl_usd', sa.Float(), nullable=True),
        sa.Column('alert_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_trades_ticker', 'trades', ['ticker'])
    op.create_index('ix_trades_created_at', 'trades', ['created_at'])
    op.create_index('ix_trades_ticker_side', 'trades', ['ticker', 'side'])

    # Alert Log table
    op.create_table(
        'alert_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('alert_id', sa.String(100), nullable=True),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('source_ip', sa.String(50), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('queued', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('skip_reason', sa.String(200), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('idempotency_key', sa.String(100), nullable=True, unique=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_logs_ticker', 'alert_logs', ['ticker'])
    op.create_index('ix_alert_logs_idempotency_key', 'alert_logs', ['idempotency_key'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index('ix_alert_logs_idempotency_key', table_name='alert_logs')
    op.drop_index('ix_alert_logs_ticker', table_name='alert_logs')
    op.drop_table('alert_logs')

    op.drop_index('ix_trades_ticker_side', table_name='trades')
    op.drop_index('ix_trades_created_at', table_name='trades')
    op.drop_index('ix_trades_ticker', table_name='trades')
    op.drop_table('trades')

    op.drop_index('ix_positions_ticker_status', table_name='positions')
    op.drop_index('ix_positions_status', table_name='positions')
    op.drop_index('ix_positions_ticker', table_name='positions')
    op.drop_table('positions')

    op.drop_table('bot_settings')

    bind = op.get_bind()
    sa.Enum(name='tradestatus').drop(bind, checkfirst=True)
    sa.Enum(name='tradeside').drop(bind, checkfirst=True)
    sa.Enum(name='positionstatus').drop(bind, checkfirst=True)
