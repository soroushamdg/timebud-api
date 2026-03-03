from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List
from uuid import UUID

from database import get_db
from auth import get_current_user
from models.schemas import TaskCreate, TaskUpdate, TaskResponse
from services import task_service, user_service

router = APIRouter(prefix="/milestones", tags=["tasks"])

@router.post("/{milestone_id}/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    milestone_id: UUID,
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> TaskResponse:
    """
    Create a new task for a milestone.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Create task
    task = await task_service.create_task_for_milestone(db, milestone_id, clerk_id, task_data)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Milestone not found or access denied."
        )
    
    return TaskResponse.model_validate(task)

@router.get("/{milestone_id}/tasks", response_model=List[TaskResponse])
async def list_milestone_tasks(
    milestone_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[TaskResponse]:
    """
    Get all tasks for a milestone.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Get tasks
    tasks = await task_service.get_milestone_tasks(db, milestone_id, clerk_id)
    
    return [TaskResponse.model_validate(task) for task in tasks]

# Create a separate router for task-specific operations
task_router = APIRouter(prefix="/tasks", tags=["tasks"])

@task_router.patch("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> TaskResponse:
    """
    Mark a task as completed.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Complete task
    task = await task_service.complete_task(db, task_id, clerk_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or access denied."
        )
    
    return TaskResponse.model_validate(task)

@task_router.patch("/{task_id}/skip", response_model=TaskResponse)
async def skip_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> TaskResponse:
    """
    Skip a task (mark as skipped).
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Skip task
    task = await task_service.skip_task(db, task_id, clerk_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or access denied."
        )
    
    return TaskResponse.model_validate(task)
