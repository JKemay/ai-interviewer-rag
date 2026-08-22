"""ORM models.

Every table owned by a user carries `owner_id`, and every child of an owned row
carries a **composite** foreign key `(parent_id, owner_id)` referencing the
parent's `(id, owner_id)`. That makes it structurally impossible for a child row
to claim a different owner than its parent — not merely discouraged by
application code, but rejected by the database (ADR-0001, ADR-0003).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import BYTEA, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    created_at_column,
    deleted_at_column,
    updated_at_column,
    uuid_pk,
)


class AppUser(Base):
    """A person. `owner_id` for every other table points here.

    Named `app_user` rather than `user` because `user` is a reserved word in
    Postgres — `SELECT * FROM user` returns the current role name, not a table,
    which makes for a genuinely confusing afternoon.
    """

    __tablename__ = "app_user"
    __table_args__ = (
        # Emails are normalised to lowercase before insert. A plain unique
        # constraint then prevents Alice@x.com and alice@x.com coexisting.
        UniqueConstraint("email", name="uq_app_user_email"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    deleted_at: Mapped[datetime | None] = deleted_at_column()


class SessionToken(Base):
    """A server-side session.

    The raw token is returned to the browser once and never stored. Only its
    SHA-256 hash is persisted, so a leaked database dump does not hand over live
    sessions — the same reason passwords are hashed.
    """

    __tablename__ = "session_token"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_session_token_token_hash"),
        # Supports the expiry sweep without scanning the table.
        Index("ix_session_token_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # Revocation is explicit rather than a row delete, so "this session was
    # ended" survives in the record instead of vanishing.
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, default=None
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, default=None
    )
    # Distinct from revoked_at. `revoked_at` records that the session is no
    # longer valid — the security fact, kept for audit. `deleted_at` marks the
    # row for purge, and is what the application-role RLS policy filters on.
    deleted_at: Mapped[datetime | None] = deleted_at_column()


__all__ = ["AppUser", "SessionToken"]
