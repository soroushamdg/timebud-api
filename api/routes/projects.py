from typing import List
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import get_current_user
from database import get_db
from schemas import ProjectCreate, ProjectUpdate, ProjectResponse, SuccessResponse, ProjectStatus

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects for current user (excluding deleted)."""
    query = text("""
        SELECT id, user_id, name, description, deadline, priority, status, color, created_at
        FROM projects
        WHERE user_id = :user_id AND status != 'deleted'
        ORDER BY created_at DESC
    """)
    
    result = await db.execute(query, {"user_id": current_user["clerk_user_id"]})
    projects = result.mappings().all()
    
    return [
        ProjectResponse(
            id=str(project["id"]),
            user_id=project["user_id"],
            name=project["name"],
            description=project["description"],
            deadline=project["deadline"],
            priority=project["priority"],
            status=project["status"],
            color=project["color"],
            created_at=project["created_at"],
        )
        for project in projects
    ]


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new project."""
    project_id = str(uuid4())
    
    query = text("""
        INSERT INTO projects (id, user_id, name, description, deadline, priority, status, color)
        VALUES (:id, :user_id, :name, :description, :deadline, :priority, :status, :color)
        RETURNING id, user_id, name, description, deadline, priority, status, color, created_at
    """)
    
    result = await db.execute(
        query,
        {
            "id": project_id,
            "user_id": current_user["clerk_user_id"],
            "name": project.name,
            "description": project.description,
            "deadline": project.deadline,
            "priority": project.priority if project.priority is not None else False,
            "status": project.status.value if project.status else ProjectStatus.active.value,
            "color": project.color,
        },
    )
    await db.commit()
    
    project_row = result.mappings().first()
    
    return ProjectResponse(
        id=str(project_row["id"]),
        user_id=project_row["user_id"],
        name=project_row["name"],
        description=project_row["description"],
        deadline=project_row["deadline"],
        priority=project_row["priority"],
        status=project_row["status"],
        color=project_row["color"],
        created_at=project_row["created_at"],
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single project by ID."""
    query = text("""
        SELECT id, user_id, name, description, deadline, priority, status, color, created_at
        FROM projects
        WHERE id = :id AND user_id = :user_id AND status != 'deleted'
    """)
    
    result = await db.execute(
        query, {"id": project_id, "user_id": current_user["clerk_user_id"]}
    )
    project_row = result.mappings().first()
    
    if not project_row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return ProjectResponse(
        id=str(project_row["id"]),
        user_id=project_row["user_id"],
        name=project_row["name"],
        description=project_row["description"],
        deadline=project_row["deadline"],
        priority=project_row["priority"],
        status=project_row["status"],
        color=project_row["color"],
        created_at=project_row["created_at"],
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partially update a project."""
    # Get only the fields that were actually provided
    update_data = project_update.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided for update")
    
    # Build dynamic SET clause
    set_clauses = []
    params = {"id": project_id, "user_id": current_user["clerk_user_id"]}
    
    for field, value in update_data.items():
        set_clauses.append(f"{field} = :{field}")
        # Convert enum to its value if needed
        if field == "status" and value is not None:
            params[field] = value.value
        else:
            params[field] = value
    
    query = text(f"""
        UPDATE projects
        SET {', '.join(set_clauses)}
        WHERE id = :id AND user_id = :user_id AND status != 'deleted'
        RETURNING id, user_id, name, description, deadline, priority, status, color, created_at
    """)
    
    result = await db.execute(query, params)
    await db.commit()
    
    project_row = result.mappings().first()
    
    if not project_row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return ProjectResponse(
        id=str(project_row["id"]),
        user_id=project_row["user_id"],
        name=project_row["name"],
        description=project_row["description"],
        deadline=project_row["deadline"],
        priority=project_row["priority"],
        status=project_row["status"],
        color=project_row["color"],
        created_at=project_row["created_at"],
    )


@router.delete("/{project_id}", response_model=SuccessResponse)
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a project by setting status to 'deleted'."""
    query = text("""
        UPDATE projects
        SET status = 'deleted'
        WHERE id = :id AND user_id = :user_id AND status != 'deleted'
        RETURNING id
    """)
    
    result = await db.execute(
        query, {"id": project_id, "user_id": current_user["clerk_user_id"]}
    )
    await db.commit()
    
    deleted_row = result.mappings().first()
    
    if not deleted_row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return SuccessResponse(
        success=True,
        data={"id": project_id, "message": "Project deleted successfully"},
    )
