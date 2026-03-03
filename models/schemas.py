from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime
from typing import Optional, List
from uuid import UUID

# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserCreate(UserBase):
    clerk_id: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    created_at: datetime
    updated_at: Optional[datetime] = None

# Project Schemas
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: Optional[str] = None
    knows_steps: Optional[bool] = None
    status: Optional[str] = None
    color: Optional[str] = None
    is_active: bool = True

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: Optional[str] = None
    knows_steps: Optional[bool] = None
    status: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None

class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

# Milestone Schemas
class MilestoneBase(BaseModel):
    title: str
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    is_completed: bool = False

class MilestoneCreate(MilestoneBase):
    project_id: UUID

class MilestoneUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    is_completed: Optional[bool] = None

class MilestoneResponse(MilestoneBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

# Task Schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    status: str = "pending"
    estimated_minutes: Optional[int] = None
    actual_minutes: int = 0
    due_date: Optional[datetime] = None

class TaskCreate(TaskBase):
    project_id: UUID

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    due_date: Optional[datetime] = None

class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

# Session Schemas
class SessionBase(BaseModel):
    project_id: Optional[UUID] = None
    notes: Optional[str] = None

class SessionCreate(SessionBase):
    pass

class SessionUpdate(BaseModel):
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None

class SessionResponse(SessionBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    created_at: datetime

# SessionTask Schemas
class SessionTaskBase(BaseModel):
    task_id: UUID
    time_spent_minutes: int = 0
    notes: Optional[str] = None

class SessionTaskCreate(SessionTaskBase):
    session_id: UUID

class SessionTaskUpdate(BaseModel):
    time_spent_minutes: Optional[int] = None
    notes: Optional[str] = None

class SessionTaskResponse(SessionTaskBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    session_id: UUID
    created_at: datetime
