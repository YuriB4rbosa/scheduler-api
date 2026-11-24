"""create initial schema

Revision ID: ae5d6a5111fb
Revises: 
Create Date: 2026-11-24 16:55:03.651748

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ae5d6a5111fb'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # btree_gist permite combinar igualdade (user_id) com sobreposição de intervalo (&&)
    # na mesma exclusion constraint de appointments.
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('customers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=30), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'email', name='uq_customers_user_email')
    )
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_customers_user_id'), ['user_id'], unique=False)

    op.create_table('services',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('duration_minutes > 0', name='ck_services_duration_positive'),
    sa.CheckConstraint('price >= 0', name='ck_services_price_non_negative'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_services_user_id'), ['user_id'], unique=False)

    op.create_table('appointments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='scheduled', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    postgresql.ExcludeConstraint((sa.column('user_id'), '='), (sa.text('tstzrange(start_at, end_at)'), '&&'), where=sa.text("status = 'scheduled'"), using='gist', name='ex_appointments_no_overlap'),
    sa.CheckConstraint("status IN ('scheduled', 'completed', 'canceled')", name='ck_appointments_status'),
    sa.CheckConstraint('end_at > start_at', name='ck_appointments_end_after_start'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_appointments_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointments_service_id'), ['service_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointments_start_at'), ['start_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointments_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_appointments_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_appointments_user_id'))
        batch_op.drop_index(batch_op.f('ix_appointments_status'))
        batch_op.drop_index(batch_op.f('ix_appointments_start_at'))
        batch_op.drop_index(batch_op.f('ix_appointments_service_id'))
        batch_op.drop_index(batch_op.f('ix_appointments_customer_id'))

    op.drop_table('appointments')
    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_services_user_id'))

    op.drop_table('services')
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customers_user_id'))

    op.drop_table('customers')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
    # ### end Alembic commands ###
