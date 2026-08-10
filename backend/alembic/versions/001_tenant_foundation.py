"""tenant foundation: organizations, users, organization_members

Revision ID: 001_tenant_foundation
Revises:
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001_tenant_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    organization_status = sa.Enum("ACTIVE", "SUSPENDED", name="organization_status")
    user_status = sa.Enum(
        "ACTIVE",
        "SUSPENDED",
        "PENDING_VERIFICATION",
        name="user_status",
    )
    member_role = sa.Enum(
        "ORG_OWNER",
        "ORG_ADMIN",
        "ORG_MEMBER",
        name="organization_member_role",
    )
    organization_status.create(op.get_bind(), checkfirst=True)
    user_status.create(op.get_bind(), checkfirst=True)
    member_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("status", organization_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", user_status, nullable=False),
        sa.Column("mfa_secret_enc", sa.LargeBinary(), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", member_role, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_org_member_tenant_user"),
    )
    op.create_index(
        "ix_organization_members_tenant_id", "organization_members", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_organization_members_user_id", "organization_members", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("organization_members")
    op.drop_table("users")
    op.drop_table("organizations")
    sa.Enum(name="organization_member_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="organization_status").drop(op.get_bind(), checkfirst=True)
