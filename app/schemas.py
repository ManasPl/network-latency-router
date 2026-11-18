from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def check_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be empty")
    return value


class NodeCreate(BaseModel):
    name: str = Field(..., max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        return check_name(v)


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class EdgeCreate(BaseModel):
    source: str = Field(..., max_length=255)
    destination: str = Field(..., max_length=255)
    latency: float = Field(..., gt=0, strict=True, allow_inf_nan=False)

    @field_validator("source", "destination")
    @classmethod
    def validate_names(cls, v):
        return check_name(v)


class EdgeOut(BaseModel):
    id: int
    source: str
    destination: str
    latency: float


class RouteRequest(BaseModel):
    source: str = Field(..., max_length=255)
    destination: str = Field(..., max_length=255)

    @field_validator("source", "destination")
    @classmethod
    def validate_names(cls, v):
        return check_name(v)


class RouteOut(BaseModel):
    total_latency: float
    path: List[str]


class RouteHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    destination: str
    total_latency: float
    path: List[str]
    created_at: datetime

    @field_serializer("created_at")
    def format_created_at(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
