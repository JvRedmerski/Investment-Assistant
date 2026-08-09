"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-09 15:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # 2. investor_profiles
    op.create_table(
        'investor_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('risk_profile', sa.Enum('CONSERVATIVE', 'MODERATE', 'AGGRESSIVE', name='riskprofileenum'), nullable=False),
        sa.Column('monthly_contribution', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_investor_profiles_id'), 'investor_profiles', ['id'], unique=False)

    # 3. assets
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('asset_type', sa.String(length=50), nullable=False),
        sa.Column('sector', sa.String(length=100), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker')
    )
    op.create_index(op.f('ix_assets_id'), 'assets', ['id'], unique=False)
    op.create_index(op.f('ix_assets_ticker'), 'assets', ['ticker'], unique=True)

    # 4. asset_prices
    op.create_table(
        'asset_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('adjusted_close', sa.Float(), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'date', name='uq_asset_price_date')
    )
    op.create_index('idx_asset_price_date', 'asset_prices', ['asset_id', 'date'], unique=False)
    op.create_index(op.f('ix_asset_prices_id'), 'asset_prices', ['id'], unique=False)

    # 5. intraday_prices
    op.create_table(
        'intraday_prices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('volume', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'timestamp', 'timeframe', name='uq_intraday_timestamp_timeframe')
    )
    op.create_index('idx_intraday_asset_timestamp', 'intraday_prices', ['asset_id', 'timestamp'], unique=False)
    op.create_index(op.f('ix_intraday_prices_id'), 'intraday_prices', ['id'], unique=False)

    # 6. portfolios
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_portfolios_id'), 'portfolios', ['id'], unique=False)

    # 7. transactions
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.Enum('BUY', 'SELL', 'DIVIDEND', 'DEPOSIT', 'WITHDRAWAL', name='transactiontypeenum'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('fees', sa.Float(), nullable=False),
        sa.Column('transaction_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_transactions_portfolio_asset', 'transactions', ['portfolio_id', 'asset_id'], unique=False)
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)

    # 8. portfolio_snapshots
    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('cash_value', sa.Float(), nullable=False),
        sa.Column('return_daily', sa.Float(), nullable=True),
        sa.Column('return_monthly', sa.Float(), nullable=True),
        sa.Column('return_ytd', sa.Float(), nullable=True),
        sa.Column('return_yearly', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_snapshot_portfolio_date', 'portfolio_snapshots', ['portfolio_id', 'date'], unique=False)
    op.create_index(op.f('ix_portfolio_snapshots_id'), 'portfolio_snapshots', ['id'], unique=False)

    # 9. fundamentals
    op.create_table(
        'fundamentals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('reference_date', sa.Date(), nullable=False),
        sa.Column('revenue', sa.Float(), nullable=True),
        sa.Column('ebitda', sa.Float(), nullable=True),
        sa.Column('net_income', sa.Float(), nullable=True),
        sa.Column('equity', sa.Float(), nullable=True),
        sa.Column('debt', sa.Float(), nullable=True),
        sa.Column('cash', sa.Float(), nullable=True),
        sa.Column('free_cash_flow', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fundamentals_asset_refdate', 'fundamentals', ['asset_id', 'reference_date'], unique=False)
    op.create_index(op.f('ix_fundamentals_id'), 'fundamentals', ['id'], unique=False)

    # 10. financial_indicators
    op.create_table(
        'financial_indicators',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('reference_date', sa.Date(), nullable=False),
        sa.Column('pe', sa.Float(), nullable=True),
        sa.Column('pb', sa.Float(), nullable=True),
        sa.Column('roe', sa.Float(), nullable=True),
        sa.Column('roic', sa.Float(), nullable=True),
        sa.Column('dy', sa.Float(), nullable=True),
        sa.Column('debt_ebitda', sa.Float(), nullable=True),
        sa.Column('net_margin', sa.Float(), nullable=True),
        sa.Column('ebitda_margin', sa.Float(), nullable=True),
        sa.Column('revenue_growth', sa.Float(), nullable=True),
        sa.Column('profit_growth', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_indicators_asset_refdate', 'financial_indicators', ['asset_id', 'reference_date'], unique=False)
    op.create_index(op.f('ix_financial_indicators_id'), 'financial_indicators', ['id'], unique=False)

    # 11. recommendations
    op.create_table(
        'recommendations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('recommendation_type', sa.String(length=50), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('target_weight', sa.Float(), nullable=False),
        sa.Column('suggested_amount', sa.Float(), nullable=False),
        sa.Column('horizon', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendations_id'), 'recommendations', ['id'], unique=False)

    # 12. daytrade_setups
    op.create_table(
        'daytrade_setups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('strategy', sa.String(length=50), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('entry_price', sa.Float(), nullable=False),
        sa.Column('stop_price', sa.Float(), nullable=False),
        sa.Column('target_price', sa.Float(), nullable=False),
        sa.Column('risk_reward', sa.Float(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_daytrade_setups_id'), 'daytrade_setups', ['id'], unique=False)

    # 13. daytrade_results
    op.create_table(
        'daytrade_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('setup_id', sa.Integer(), nullable=False),
        sa.Column('exit_price', sa.Float(), nullable=False),
        sa.Column('exit_timestamp', sa.DateTime(), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),
        sa.Column('pnl', sa.Float(), nullable=False),
        sa.Column('pnl_percent', sa.Float(), nullable=False),
        sa.Column('costs', sa.Float(), nullable=False),
        sa.Column('slippage', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['setup_id'], ['daytrade_setups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('setup_id')
    )
    op.create_index(op.f('ix_daytrade_results_id'), 'daytrade_results', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_daytrade_results_id'), table_name='daytrade_results')
    op.drop_table('daytrade_results')
    op.drop_index(op.f('ix_daytrade_setups_id'), table_name='daytrade_setups')
    op.drop_table('daytrade_setups')
    op.drop_index(op.f('ix_recommendations_id'), table_name='recommendations')
    op.drop_table('recommendations')
    op.drop_index(op.f('ix_financial_indicators_id'), table_name='financial_indicators')
    op.drop_index('idx_indicators_asset_refdate', table_name='financial_indicators')
    op.drop_table('financial_indicators')
    op.drop_index(op.f('ix_fundamentals_id'), table_name='fundamentals')
    op.drop_index('idx_fundamentals_asset_refdate', table_name='fundamentals')
    op.drop_table('fundamentals')
    op.drop_index(op.f('ix_portfolio_snapshots_id'), table_name='portfolio_snapshots')
    op.drop_index('idx_snapshot_portfolio_date', table_name='portfolio_snapshots')
    op.drop_table('portfolio_snapshots')
    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    op.drop_index('idx_transactions_portfolio_asset', table_name='transactions')
    op.drop_table('transactions')
    op.drop_index(op.f('ix_portfolios_id'), table_name='portfolios')
    op.drop_table('portfolios')
    op.drop_index(op.f('ix_intraday_prices_id'), table_name='intraday_prices')
    op.drop_index('idx_intraday_asset_timestamp', table_name='intraday_prices')
    op.drop_table('intraday_prices')
    op.drop_index(op.f('ix_asset_prices_id'), table_name='asset_prices')
    op.drop_index('idx_asset_price_date', table_name='asset_prices')
    op.drop_table('asset_prices')
    op.drop_index(op.f('ix_assets_ticker'), table_name='assets')
    op.drop_index(op.f('ix_assets_id'), table_name='assets')
    op.drop_table('assets')
    op.drop_index(op.f('ix_investor_profiles_id'), table_name='investor_profiles')
    op.drop_table('investor_profiles')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS riskprofileenum")
    op.execute("DROP TYPE IF EXISTS transactiontypeenum")
