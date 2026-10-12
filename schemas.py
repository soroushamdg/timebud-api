"""
TimeBud — Pydantic v2 schemas
All datetime fields are UTC timestamptz.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────

class ProjectStatus(str, Enum):
    active   = "active"
    paused   = "paused"
    archived = "archived"
    deleted  = "deleted"


class TaskStatus(str, Enum):
    pending   = "pending"
    completed = "completed"


# ─────────────────────────────────────────────────────────────────────
# PROJECTS
# ─────────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name:        str            = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    deadline:    Optional[datetime] = None
    priority:    bool           = False
    status:      ProjectStatus  = ProjectStatus.active
    color:       Optional[str]  = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("color must be a valid 6-digit hex value e.g. #A3B4C5")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip()


class ProjectUpdate(BaseModel):
    name:        Optional[str]           = Field(None, min_length=1, max_length=255)
    description: Optional[str]           = None
    deadline:    Optional[datetime]      = None
    priority:    Optional[bool]          = None
    status:      Optional[ProjectStatus] = None
    color:       Optional[str]           = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
            raise ValueError("color must be a valid 6-digit hex value e.g. #A3B4C5")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip() if v else v


class ProjectResponse(BaseModel):
    id:          UUID
    user_id:     str
    name:        str
    description: Optional[str]
    deadline:    Optional[datetime]
    priority:    bool
    status:      ProjectStatus
    color:       Optional[str]
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# MILESTONES
# ─────────────────────────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    title:       str            = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    order:       int            = Field(..., ge=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title cannot be blank")
        return v.strip()


class MilestoneUpdate(BaseModel):
    title:       Optional[str]      = Field(None, min_length=1, max_length=255)
    description: Optional[str]      = None
    target_date: Optional[datetime] = None
    order:       Optional[int]      = Field(None, ge=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("title cannot be blank")
        return v.strip() if v else v


class MilestoneResponse(BaseModel):
    id:          UUID
    project_id:  UUID
    title:       str
    description: Optional[str]
    target_date: Optional[datetime]
    order:       int
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# TASKS
# ─────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    project_id:       Optional[UUID]       = None
    milestone_id:     Optional[UUID]       = None
    title:            str                  = Field(..., min_length=1, max_length=255)
    description:      Optional[str]        = None
    estimated_minutes: int                 = Field(..., ge=1)
    status:           TaskStatus           = TaskStatus.pending
    due_date:         Optional[datetime]   = None
    order:            int                  = Field(1, ge=1)
    priority:         bool                 = False
    depends_on_task:  Optional[UUID]       = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title cannot be blank")
        return v.strip()

    @model_validator(mode="after")
    def milestone_requires_project(self) -> TaskCreate:
        if self.milestone_id is not None and self.project_id is None:
            raise ValueError("milestone_id requires project_id to also be set")
        return self


class TaskUpdate(BaseModel):
    project_id:        Optional[UUID]       = None
    milestone_id:      Optional[UUID]       = None
    title:             Optional[str]        = Field(None, min_length=1, max_length=255)
    description:       Optional[str]        = None
    estimated_minutes: Optional[int]        = Field(None, ge=1)
    status:            Optional[TaskStatus] = None
    due_date:          Optional[datetime]   = None
    order:             Optional[int]        = Field(None, ge=1)
    priority:          Optional[bool]       = None
    depends_on_task:   Optional[UUID]       = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("title cannot be blank")
        return v.strip() if v else v

    @model_validator(mode="after")
    def milestone_requires_project(self) -> TaskUpdate:
        if self.milestone_id is not None and self.project_id is None:
            raise ValueError("milestone_id requires project_id to also be set")
        return self


class TaskResponse(BaseModel):
    id:                UUID
    project_id:        Optional[UUID]
    milestone_id:      Optional[UUID]
    user_id:           str
    title:             str
    description:       Optional[str]
    estimated_minutes: int
    status:            TaskStatus
    due_date:          Optional[datetime]
    order:             int
    priority:          bool
    depends_on_task:   Optional[UUID]
    created_at:        datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# TASKS — query filters
# ─────────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    solo    = "solo"     # no project_id and no milestone_id
    project = "project"  # has project_id
    all     = "all"


# ─────────────────────────────────────────────────────────────────────
# SESSIONS
# ─────────────────────────────────────────────────────────────────────

class SessionPlanRequest(BaseModel):
    budget_minutes:       int        = Field(..., ge=15)
    excluded_project_ids: list[UUID] = Field(default_factory=list)


class SessionSubmitRequest(BaseModel):
    """Body for PATCH /sessions/{id} when submitting a finished session."""
    start_time: datetime
    end_time:   datetime
    tasks_list: Optional[list[UUID]] = None   # optionally update the task list too

    @model_validator(mode="after")
    def end_after_start(self) -> SessionSubmitRequest:
        if self.end_time < self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class SessionUpdateRequest(BaseModel):
    """Body for PATCH /sessions/{id} for replanning / editing budget."""
    budget_minutes: Optional[int]        = Field(None, ge=15)
    tasks_list:     Optional[list[UUID]] = None
    start_time:     Optional[datetime]   = None
    end_time:       Optional[datetime]   = None


class SessionTaskItem(BaseModel):
    """One task in the planned session output."""
    position:          int
    task_id:           UUID
    project_id:        Optional[UUID]
    is_solo:           bool
    tier1:             bool
    milestone_title:   Optional[str]
    title:             str
    priority:          bool
    scheduled_minutes: int
    partial:           bool
    carry_over_minutes: int


class SessionResponse(BaseModel):
    id:             UUID
    user_id:        str
    budget_minutes: int
    start_time:     Optional[datetime]
    end_time:       Optional[datetime]
    tasks_list:     list[UUID]
    planned_tasks:  Optional[list[SessionTaskItem]] = None  # populated on plan/get

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────
# GENERIC RESPONSES
# ─────────────────────────────────────────────────────────────────────

class SuccessResponse(BaseModel):
    success: bool = True
    message: str  = "OK"
