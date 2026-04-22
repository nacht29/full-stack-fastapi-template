"""Edit replace id integers in all models to use UUID instead

Revision ID: d98dd8ec85a3
Revises: 9c0a54914c78
Create Date: 2024-07-19 04:08:04.000976

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'd98dd8ec85a3'
down_revision = '9c0a54914c78'
branch_labels = None
depends_on = None


def _dialect_name():
    return op.get_bind().dialect.name


def _uuid_type():
    if _dialect_name() == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.Uuid()


def _uuid_sql():
    if _dialect_name() == "postgresql":
        return "uuid_generate_v4()"
    return "REPLACE(UUID(), '-', '')"


def _user_table():
    if _dialect_name() in {"mysql", "mariadb"}:
        return "`user`"
    return '"user"'


def _primary_key_name(table_name):
    if _dialect_name() in {"mysql", "mariadb"}:
        return "PRIMARY"
    return f"{table_name}_pkey"


def _remove_auto_increment(table_name):
    if _dialect_name() in {"mysql", "mariadb"}:
        op.alter_column(
            table_name,
            "id",
            existing_type=sa.Integer(),
            nullable=False,
            autoincrement=False,
        )


def upgrade():
    uuid_type = _uuid_type()
    uuid_sql = _uuid_sql()
    user_table = _user_table()

    if _dialect_name() == "postgresql":
        # Ensure uuid-ossp extension is available
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Create a new UUID column with a default UUID value
    op.add_column('user', sa.Column('new_id', uuid_type, nullable=True))
    op.add_column('item', sa.Column('new_id', uuid_type, nullable=True))
    op.add_column('item', sa.Column('new_owner_id', uuid_type, nullable=True))

    # Populate the new columns with UUIDs
    op.execute(f'UPDATE {user_table} SET new_id = {uuid_sql}')
    op.execute(f'UPDATE item SET new_id = {uuid_sql}')
    op.execute(
        f'UPDATE item SET new_owner_id = (SELECT new_id FROM {user_table} '
        f'WHERE {user_table}.id = item.owner_id)'
    )

    # Set the new_id as not nullable
    op.alter_column('user', 'new_id', existing_type=uuid_type, nullable=False)
    op.alter_column('item', 'new_id', existing_type=uuid_type, nullable=False)

    # Drop old columns and rename new columns
    op.drop_constraint('item_owner_id_fkey', 'item', type_='foreignkey')
    _remove_auto_increment('item')
    _remove_auto_increment('user')
    op.drop_constraint(_primary_key_name('item'), 'item', type_='primary')
    op.drop_constraint(_primary_key_name('user'), 'user', type_='primary')
    op.drop_column('item', 'owner_id')
    op.alter_column(
        'item',
        'new_owner_id',
        new_column_name='owner_id',
        existing_type=uuid_type,
        existing_nullable=True,
    )

    op.drop_column('user', 'id')
    op.alter_column(
        'user',
        'new_id',
        new_column_name='id',
        existing_type=uuid_type,
        existing_nullable=False,
    )

    op.drop_column('item', 'id')
    op.alter_column(
        'item',
        'new_id',
        new_column_name='id',
        existing_type=uuid_type,
        existing_nullable=False,
    )

    # Create primary key constraint
    op.create_primary_key('user_pkey', 'user', ['id'])
    op.create_primary_key('item_pkey', 'item', ['id'])

    # Recreate foreign key constraint
    op.create_foreign_key('item_owner_id_fkey', 'item', 'user', ['owner_id'], ['id'])

def downgrade():
    user_table = _user_table()

    # Reverse the upgrade process
    op.add_column('user', sa.Column('old_id', sa.Integer(), nullable=True))
    op.add_column('item', sa.Column('old_id', sa.Integer(), nullable=True))
    op.add_column('item', sa.Column('old_owner_id', sa.Integer, nullable=True))

    # Populate the old columns with default values
    # Generate sequences for the integer IDs if not exist
    if _dialect_name() == "postgresql":
        op.execute('CREATE SEQUENCE IF NOT EXISTS user_id_seq AS INTEGER OWNED BY "user".old_id')
        op.execute('CREATE SEQUENCE IF NOT EXISTS item_id_seq AS INTEGER OWNED BY item.old_id')

        op.execute('SELECT setval(\'user_id_seq\', COALESCE((SELECT MAX(old_id) + 1 FROM "user"), 1), false)')
        op.execute('SELECT setval(\'item_id_seq\', COALESCE((SELECT MAX(old_id) + 1 FROM item), 1), false)')

        op.execute('UPDATE "user" SET old_id = nextval(\'user_id_seq\')')
        op.execute('UPDATE item SET old_id = nextval(\'item_id_seq\'), old_owner_id = (SELECT old_id FROM "user" WHERE "user".id = item.owner_id)')
    else:
        op.execute('SET @user_row_number = 0')
        op.execute('SET @item_row_number = 0')
        op.execute(f'UPDATE {user_table} SET old_id = (@user_row_number := @user_row_number + 1)')
        op.execute(
            f'UPDATE item SET old_id = (@item_row_number := @item_row_number + 1), '
            f'old_owner_id = (SELECT old_id FROM {user_table} '
            f'WHERE {user_table}.id = item.owner_id)'
        )

    # Drop new columns and rename old columns back
    op.drop_constraint('item_owner_id_fkey', 'item', type_='foreignkey')
    op.drop_constraint(_primary_key_name('item'), 'item', type_='primary')
    op.drop_constraint(_primary_key_name('user'), 'user', type_='primary')
    op.drop_column('item', 'owner_id')
    op.alter_column(
        'item',
        'old_owner_id',
        new_column_name='owner_id',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    op.drop_column('user', 'id')
    op.alter_column(
        'user',
        'old_id',
        new_column_name='id',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    op.drop_column('item', 'id')
    op.alter_column(
        'item',
        'old_id',
        new_column_name='id',
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    # Create primary key constraint
    op.create_primary_key('user_pkey', 'user', ['id'])
    op.create_primary_key('item_pkey', 'item', ['id'])

    # Recreate foreign key constraint
    op.create_foreign_key('item_owner_id_fkey', 'item', 'user', ['owner_id'], ['id'])
