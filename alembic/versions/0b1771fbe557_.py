"""empty message

Revision ID: 0b1771fbe557
Revises: 45c6e02a9f93
Create Date: 2019-08-23 02:53:26.998657

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '0b1771fbe557'
down_revision = '45c6e02a9f93'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('access_token', sa.Text(), nullable=False))
    op.add_column('users', sa.Column('expires', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('refresh_token', sa.Text(), nullable=True))
    op.drop_column('users', 'token')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('token', mysql.TEXT(), nullable=False))
    op.drop_column('users', 'refresh_token')
    op.drop_column('users', 'expires')
    op.drop_column('users', 'access_token')
    # ### end Alembic commands ###
