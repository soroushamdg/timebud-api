from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List
from uuid import UUID

from database import get_db
from auth import get_current_user
from models.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    MilestoneCreate, MilestoneResponse
)
from services import project_service, user_service, milestone_service

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[ProjectResponse]:
    """
    List all projects for the current user.
    By default, only returns active projects.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Get projects
    projects = await project_service.get_user_projects(db, clerk_id, active_only)
    
    return [ProjectResponse.model_validate(project) for project in projects]

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> ProjectResponse:
    """
    Create a new project for the current user.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Create project
    project = await project_service.create_project(db, clerk_id, project_data)
    
    return ProjectResponse.model_validate(project)

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> ProjectResponse:
    """
    Get a specific project by ID.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Get project
    project = await project_service.get_project_by_id(db, project_id, clerk_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied."
        )
    
    return ProjectResponse.model_validate(project)

@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    project_update: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> ProjectResponse:
    """
    Update a project.
    """
    # Get user from database
    user = await user_service.get_user_by_clerk_id(db, current_user["clerk_user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )
    
    # Update project
    project = await project_service.update_project(db, project_id, user.id, project_update)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied."
        )
    
    return ProjectResponse.model_validate(project)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> None:
    """
    Soft delete (archive) a project by setting is_active to False.
    """
    # Get user from database
    user = await user_service.get_user_by_clerk_id(db, current_user["clerk_user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )
    
    # Delete project
    success = await project_service.delete_project(db, project_id, user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied."
        )

@router.post("/{project_id}/milestones", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    project_id: UUID,
    milestone_data: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> MilestoneResponse:
    """
    Create a new milestone for a project.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Ensure milestone data has the correct project_id
    milestone_data.project_id = project_id
    
    # Create milestone
    milestone = await milestone_service.create_milestone(db, clerk_id, milestone_data)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied."
        )
    
    return MilestoneResponse.model_validate(milestone)

@router.get("/{project_id}/milestones", response_model=List[MilestoneResponse])
async def list_project_milestones(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[MilestoneResponse]:
    """
    Get all milestones for a project.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Get milestones
    milestones = await milestone_service.get_project_milestones(db, project_id, clerk_id)
    
    return [MilestoneResponse.model_validate(milestone) for milestone in milestones]
