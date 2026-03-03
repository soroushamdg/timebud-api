from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from models.db import Session, SessionTask, Task, Project
from models.schemas import SessionCreate, SessionUpdate

async def create_session(
    db: AsyncSession,
    user_id: str,
    session_data: SessionCreate
) -> Session:
    """Create a new session for a user."""
    async with db.begin():
        # If project_id is provided, verify ownership
        if session_data.project_id:
            stmt = select(Project).where(
                and_(
                    Project.id == session_data.project_id,
                    Project.user_id == user_id
                )
            )
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            
            if not project:
                raise ValueError("Project not found or access denied")
        
        # Create session
        new_session = Session(
            user_id=user_id,
            project_id=session_data.project_id,
            notes=session_data.notes
        )
        db.add(new_session)
        await db.flush()
        return new_session

async def get_session_by_id(
    db: AsyncSession,
    session_id: UUID,
    user_id: str
) -> Optional[Session]:
    """Get a specific session by ID, ensuring it belongs to the user."""
    async with db.begin():
        stmt = select(Session).options(
            selectinload(Session.session_tasks).selectinload(SessionTask.task),
            selectinload(Session.project)
        ).where(
            and_(
                Session.id == session_id,
                Session.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

async def get_session_tasks(
    db: AsyncSession,
    session_id: UUID,
    user_id: str
) -> List[SessionTask]:
    """Get all tasks for a session, ensuring the session belongs to the user."""
    async with db.begin():
        # First verify session ownership
        stmt = select(Session).where(
            and_(
                Session.id == session_id,
                Session.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            return []
        
        # Get session tasks
        stmt = select(SessionTask).options(
            selectinload(SessionTask.task)
        ).where(
            SessionTask.session_id == session_id
        ).order_by(SessionTask.created_at)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())

async def end_session(
    db: AsyncSession,
    session_id: UUID,
    user_id: str
) -> Optional[Session]:
    """End a session by setting end_time and calculating duration."""
    async with db.begin():
        stmt = select(Session).where(
            and_(
                Session.id == session_id,
                Session.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        
        if not session:
            return None
        
        # Set end time and calculate duration
        session.end_time = datetime.now(timezone.utc)
        duration = session.end_time - session.start_time
        session.duration_minutes = int(duration.total_seconds() / 60)
        
        await db.flush()
        return session

async def get_user_sessions(
    db: AsyncSession,
    user_id: str,
    project_id: Optional[UUID] = None,
    limit: int = 20
) -> List[Session]:
    """Get recent sessions for a user, optionally filtered by project."""
    async with db.begin():
        stmt = select(Session).options(
            selectinload(Session.project),
            selectinload(Session.session_tasks).selectinload(SessionTask.task)
        ).where(Session.user_id == user_id)
        
        if project_id:
            stmt = stmt.where(Session.project_id == project_id)
        
        stmt = stmt.order_by(Session.start_time.desc()).limit(limit)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
