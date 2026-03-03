from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from database import Base

class User(Base):
    __tablename__ = "users"
    
    clerk_id = Column(String, primary_key=True, nullable=False, index=True)  # Use Clerk ID as primary key
    email = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    projects = relationship("Project", back_populates="user")
    sessions = relationship("Session", back_populates="user")

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.clerk_id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    deadline = Column(DateTime(timezone=True))
    priority = Column(String)
    knows_steps = Column(Boolean)
    status = Column(String)
    color = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="projects")
    milestones = relationship("Milestone", back_populates="project")
    tasks = relationship("Task", back_populates="project")

class Milestone(Base):
    __tablename__ = "milestones"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    target_date = Column(DateTime(timezone=True))
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="milestones")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    milestone_id = Column(UUID(as_uuid=True), ForeignKey("milestones.id"))
    title = Column(String, nullable=False)
    description = Column(Text)
    priority = Column(String, default="medium")  # low, medium, high
    status = Column(String, default="pending")  # pending, in_progress, completed
    estimated_minutes = Column(Integer)
    actual_minutes = Column(Integer, default=0)
    due_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="tasks")
    session_tasks = relationship("SessionTask", back_populates="task")

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.clerk_id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    start_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    end_time = Column(DateTime(timezone=True))
    duration_minutes = Column(Integer)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    project = relationship("Project")
    session_tasks = relationship("SessionTask", back_populates="session")

class SessionTask(Base):
    __tablename__ = "session_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    time_spent_minutes = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("Session", back_populates="session_tasks")
    task = relationship("Task", back_populates="session_tasks")
