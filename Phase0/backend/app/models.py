"""SQLAlchemy models for the platform database.

Phase 0 uses SQLite (file `phase0.db`) via async SQLAlchemy. Swappable to
Postgres later by setting DATABASE_URL — the models are engine-agnostic.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# The only fields the admin screen may change. Everything else on a catalog entry
# is sourced from AgentCore (ARN, name, protocol, status, version) and is read-only.
EDITABLE_FIELDS = {"display_name", "description", "ui_mode", "enabled", "required_role"}
UI_MODES = {"static", "a2ui"}


class AgentCatalogEntry(Base):
    """One registered agent. Joined to a live AgentCore runtime by `runtime_arn`.

    Two kinds of columns:
      * platform-owned (editable in the admin screen) — display_name, description,
        ui_mode, enabled, required_role, and the routing slug agent_id.
      * AgentCore-sourced (read-only, refreshed on sync) — runtime_arn, runtime_name,
        protocol, status, version, last_synced_at.
    """

    __tablename__ = "agent_catalog"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # --- platform-owned ---
    agent_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # routing slug
    display_name: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    ui_mode: Mapped[str] = mapped_column(String(16), default="a2ui")  # 'static' | 'a2ui'
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    required_role: Mapped[str] = mapped_column(String(64), default="")

    # --- AgentCore-sourced (read-only) ---
    runtime_arn: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    runtime_name: Mapped[str] = mapped_column(String(256), default="")
    protocol: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="")
    version: Mapped[str] = mapped_column(String(32), default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "description": self.description,
            "ui_mode": self.ui_mode,
            "enabled": self.enabled,
            "required_role": self.required_role,
            # AgentCore-sourced (read-only in the UI)
            "runtime_arn": self.runtime_arn,
            "runtime_name": self.runtime_name,
            "protocol": self.protocol,
            "status": self.status,
            "version": self.version,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AuditLog(Base):
    """One admin/platform mutation — a queryable audit trail (who, when, what).

    Deliberately NOT for operational/request logs: those go to structlog → stdout
    → CloudWatch. This table is low-volume and holds only intentional state changes
    (catalog edits, syncs) so "who changed this agent?" is answerable from the DB.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Actor — resolved from the Entra ID identity on the request. Empty in iam mode
    # (SSO off / local dev), where there is no authenticated caller.
    actor_oid: Mapped[str] = mapped_column(String(128), default="", index=True)
    actor_email: Mapped[str] = mapped_column(String(256), default="")

    action: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "catalog.update", "catalog.sync"
    target: Mapped[str] = mapped_column(String(256), default="")  # e.g. the agent_id acted on
    detail: Mapped[str] = mapped_column(Text, default="")  # JSON blob: the change / result

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "actor_oid": self.actor_oid,
            "actor_email": self.actor_email,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
