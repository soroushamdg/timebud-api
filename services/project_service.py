from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from uuid import UUID

from models.db import Project, User
from models.schemas import ProjectCreate, ProjectUpdate

async def create_project(
    db: AsyncSession,
    user_id: str,
    project_data: ProjectCreate
) -> Project:
    """Create a new project for a user."""
    async with db.begin():
        new_project = Project(
            user_id=user_id,
            name=project_data.name,
            description=project_data.description,
            deadline=project_data.deadline,
            priority=project_data.priority,
            knows_steps=project_data.knows_steps,
            status=project_data.status,
            color=project_data.color,
            is_active=project_data.is_active
        )
        db.add(new_project)
        await db.flush()
        return new_project

async def get_user_projects(
    db: AsyncSession,
    user_id: str,
    active_only: bool = False
) -> List[Project]:
    """Get all projects for a user, optionally filtered by active status."""
    async with db.begin():
        stmt = select(Project).where(Project.user_id == user_id)
        if active_only:
            stmt = stmt.where(Project.is_active == True)
        stmt = stmt.order_by(Project.created_at.desc())
        
        result = await db.execute(stmt)
        return list(result.scalars().all())

async def get_project_by_id(
    db: AsyncSession,
    project_id: UUID,
    user_id: str
) -> Optional[Project]:
    """Get a specific project by ID, ensuring it belongs to the user."""
    async with db.begin():
        stmt = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

async def update_project(
    db: AsyncSession,
    project_id: UUID,
    user_id: str,
    project_update: ProjectUpdate
) -> Optional[Project]:
    """Update a project, ensuring it belongs to the user."""
    async with db.begin():
        # Get the project
        stmt = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if not project:
            return None
        
        # Update only provided fields
        if project_update.name is not None:
            project.name = project_update.name
        if project_update.description is not None:
            project.description = project_update.description
        if project_update.color is not None:
            project.color = project_update.color
        if project_update.is_active is not None:
            project.is_active = project_update.is_active
        
        await db.flush()
        return project

async def delete_project(
    db: AsyncSession,
    project_id: UUID,
    user_id: str
) -> bool:
    """Soft delete a project by setting is_active to False."""
    async with db.begin():
        # Get the project
        stmt = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if not project:
            return False
        
        # Soft delete
        project.is_active = False
        await db.flush()
        return True
