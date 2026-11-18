from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    outgoing = relationship(
        "Edge", foreign_keys="Edge.source_id", cascade="all, delete-orphan", passive_deletes=True
    )
    incoming = relationship(
        "Edge", foreign_keys="Edge.destination_id", cascade="all, delete-orphan", passive_deletes=True
    )


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint("source_id", "destination_id", name="uq_edge_source_destination"),
        CheckConstraint("latency > 0", name="ck_edge_latency_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    latency: Mapped[float] = mapped_column(Float, nullable=False)

    source = relationship("Node", foreign_keys=[source_id], overlaps="outgoing")
    destination = relationship("Node", foreign_keys=[destination_id], overlaps="incoming")


class RouteQuery(Base):
    # storing names instead of node ids so history is kept even if a node is deleted

    __tablename__ = "route_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    destination: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    total_latency: Mapped[float] = mapped_column(Float, nullable=False)
    path: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
