from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from models.db import Milestone, Project
from models.schemas import MilestoneCreate, MilestoneUpdate

async def create_milestone(
    db: AsyncSession,
    user_id: str,
    milestone_data: MilestoneCreate
) -> Optional[Milestone]:
    """Create a new milestone for a project, ensuring the project belongs to the user."""
    async with db.begin():
        # Verify project ownership
        stmt = select(Project).where(
            and_(
                Project.id == milestone_data.project_id,
                Project.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if not project:
            return None
        
        # Create milestone
        new_milestone = Milestone(
            project_id=milestone_data.project_id,
            title=milestone_data.title,
            description=milestone_data.description,
            target_date=milestone_data.target_date,
            is_completed=milestone_data.is_completed
        )
        db.add(new_milestone)
        await db.flush()
        return new_milestone

async def get_project_milestones(
    db: AsyncSession,
    project_id: UUID,
    user_id: str
) -> List[Milestone]:
    """Get all milestones for a project, ensuring the project belongs to the user."""
    async with db.begin():
        # First verify project ownership
        stmt = select(Project).where(
            and_(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        result = await db.execute(stmt)
        project = result.scalar_one_or_none()
        
        if not project:
            return []
        
        # Get milestones
        stmt = select(Milestone).where(
            Milestone.project_id == project_id
        ).order_by(Milestone.target_date, Milestone.created_at)
        
        result = await db.execute(stmt)
        return list(result.scalars().all())

async def get_milestone_by_id(
    db: AsyncSession,
    milestone_id: UUID,
    user_id: str
) -> Optional[Milestone]:
    """Get a specific milestone, ensuring it belongs to a project owned by the user."""
    async with db.begin():
        stmt = select(Milestone).options(
            selectinload(Milestone.project)
        ).where(Milestone.id == milestone_id)
        
        result = await db.execute(stmt)
        milestone = result.scalar_one_or_none()
        
        # Verify ownership through project
        if milestone and milestone.project.user_id == user_id:
            return milestone
        return None

async def update_milestone(
    db: AsyncSession,
    milestone_id: UUID,
    user_id: str,
    milestone_update: MilestoneUpdate
) -> Optional[Milestone]:
    """Update a milestone, ensuring it belongs to a project owned by the user."""
    async with db.begin():
        # Get milestone with project
        stmt = select(Milestone).options(
            selectinload(Milestone.project)
        ).where(Milestone.id == milestone_id)
        
        result = await db.execute(stmt)
        milestone = result.scalar_one_or_none()
        
        # Verify ownership through project
        if not milestone or milestone.project.user_id != user_id:
            return None
        
        # Update only provided fields
        if milestone_update.title is not None:
            milestone.title = milestone_update.title
        if milestone_update.description is not None:
            milestone.description = milestone_update.description
        if milestone_update.target_date is not None:
            milestone.target_date = milestone_update.target_date
        if milestone_update.is_completed is not None:
            milestone.is_completed = milestone_update.is_completed
        
        await db.flush()
        return milestone
