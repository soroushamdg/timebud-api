from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from models.db import Task, Project, Milestone
from models.schemas import TaskCreate, TaskUpdate

async def create_task_for_milestone(
    db: AsyncSession,
    milestone_id: UUID,
    user_id: int,
    task_data: TaskCreate
) -> Optional[Task]:
    """Create a new task for a milestone, ensuring ownership through project."""
    async with db.begin():
        # Verify milestone ownership through project
        stmt = select(Milestone).options(
            selectinload(Milestone.project)
        ).where(Milestone.id == milestone_id)
        
        result = await db.execute(stmt)
        milestone = result.scalar_one_or_none()
        
        if not milestone or milestone.project.user_id != user_id:
            return None
        
        # Create task with the milestone's project_id and milestone_id
        new_task = Task(
            project_id=milestone.project_id,
            milestone_id=milestone_id,
            title=task_data.title,
            description=task_data.description,
            priority=task_data.priority,
            status=task_data.status,
            estimated_minutes=task_data.estimated_minutes,
            actual_minutes=task_data.actual_minutes,
            due_date=task_data.due_date
        )
        db.add(new_task)
        await db.flush()
        return new_task

async def get_milestone_tasks(
    db: AsyncSession,
    milestone_id: UUID,
    user_id: int
) -> List[Task]:
    """Get all tasks for a milestone, ensuring ownership through project."""
    async with db.begin():
        # First verify milestone ownership
        stmt = select(Milestone).options(
            selectinload(Milestone.project)
        ).where(Milestone.id == milestone_id)
        
        result = await db.execute(stmt)
        milestone = result.scalar_one_or_none()
        
        if not milestone or milestone.project.user_id != user_id:
            return []
        
        # Get tasks for the milestone's project
        # Note: Tasks are linked to projects, not milestones directly
        # This gets all tasks for the project - you may want to add a milestone_id field to Task model
        stmt = select(Task).where(
            Task.project_id == milestone.project_id
        ).order_by(Task.created_at.desc())
        
        result = await db.execute(stmt)
        return list(result.scalars().all())

async def get_task_by_id(
    db: AsyncSession,
    task_id: UUID,
    user_id: str
) -> Optional[Task]:
    """Get a specific task, ensuring it belongs to a project owned by the user."""
    stmt = select(Task).options(
        selectinload(Task.project)
    ).where(Task.id == task_id)
    
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    # Verify ownership through project
    if task and task.project.user_id == user_id:
        return task
    return None

async def update_task(
    db: AsyncSession,
    task_id: UUID,
    user_id: str,
    task_update: TaskUpdate
) -> Optional[Task]:
    """Update a task, ensuring it belongs to a project owned by the user."""
    async with db.begin():
        # Get task with project
        stmt = select(Task).options(
            selectinload(Task.project)
        ).where(Task.id == task_id)
        
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        
        # Verify ownership through project
        if not task or task.project.user_id != user_id:
            return None
        
        # Update only provided fields
        if task_update.title is not None:
            task.title = task_update.title
        if task_update.description is not None:
            task.description = task_update.description
        if task_update.priority is not None:
            task.priority = task_update.priority
        if task_update.status is not None:
            task.status = task_update.status
        if task_update.estimated_minutes is not None:
            task.estimated_minutes = task_update.estimated_minutes
        if task_update.actual_minutes is not None:
            task.actual_minutes = task_update.actual_minutes
        if task_update.due_date is not None:
            task.due_date = task_update.due_date
        
        await db.flush()
        return task

async def complete_task(
    db: AsyncSession,
    task_id: UUID,
    user_id: str
) -> Optional[Task]:
    """Mark a task as completed."""
    async with db.begin():
        task = await get_task_by_id(db, task_id, user_id)
        if task:
            task.status = "completed"
            await db.flush()
            await db.refresh(task)
        return task

async def skip_task(
    db: AsyncSession,
    task_id: UUID,
    user_id: str
) -> Optional[Task]:
    """Skip a task (mark as skipped/cancelled)."""
    async with db.begin():
        task = await get_task_by_id(db, task_id, user_id)
        if task:
            task.status = "skipped"
            await db.flush()
            await db.refresh(task)
        return task
