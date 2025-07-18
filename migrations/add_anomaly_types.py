"""Add anomaly detection alert types

Revision ID: add_anomaly_types
Revises: 
Create Date: 2025-07-18

"""
from alembic import op
import sqlalchemy as sa

# No database schema changes needed since we're using string enum values
# The new enum values will be automatically available

def upgrade():
    # No schema changes needed - enum values are stored as strings
    pass

def downgrade():
    # No schema changes needed
    pass