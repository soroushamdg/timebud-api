from typing import List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import get_current_user
from database import get_db
from schemas import TaskCreate, TaskUpdate, TaskResponse, TaskStatus, TaskType, SuccessResponse

# Router for /tasks endpoints
task_router = APIRouter(tags=["tasks"])

# Router for project-nested endpoints
router = APIRouter(prefix="/projects", tags=["tasks"])


async def verify_project_ownership(
    project_id: str, user_id: str, db: AsyncSession
) -> bool:
    """Verify project exists and belongs to user."""
    query = text("""
        SELECT 1 FROM projects
        WHERE id = :project_id AND user_id = :user_id AND status != 'deleted'
    """)
    result = await db.execute(query, {"project_id": project_id, "user_id": user_id})
    return result.scalar() is not None


async def verify_milestone_ownership(
    milestone_id: str, project_id: str, db: AsyncSession
) -> bool:
    """Verify milestone exists and belongs to project."""
    query = text("""
        SELECT 1 FROM milestones
        WHERE id = :milestone_id AND project_id = :project_id
    """)
    result = await db.execute(
        query, {"milestone_id": milestone_id, "project_id": project_id}
    )
    return result.scalar() is not None


async def verify_task_ownership(
    task_id: str, user_id: str, db: AsyncSession
) -> bool:
    """Verify task exists and belongs to user."""
    query = text("""
        SELECT 1 FROM tasks
        WHERE id = :task_id AND user_id = :user_id
    """)
    result = await db.execute(query, {"task_id": task_id, "user_id": user_id})
    return result.scalar() is not None


@task_router.get("/tasks/", response_model=List[TaskResponse])
async def list_tasks(
    type: TaskType = Query(default=TaskType.all),
    status: Optional[TaskStatus] = Query(default=None),
    project_id: Optional[str] = Query(default=None),
    priority: Optional[bool] = Query(default=None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tasks with filters."""
    # Build WHERE clause
    where_conditions = ["user_id = :user_id"]
    params = {"user_id": current_user["clerk_user_id"]}
    
    # Apply type filter
    if type == TaskType.solo:
        where_conditions.append("project_id IS NULL AND milestone_id IS NULL")
    elif type == TaskType.project:
        where_conditions.append("project_id IS NOT NULL")
    
    # Apply other filters
    if status is not None:
        where_conditions.append("status = :status")
        params["status"] = status.value
    
    if project_id is not None:
        where_conditions.append("project_id = :project_id")
        params["project_id"] = project_id
    
    if priority is not None:
        where_conditions.append("priority = :priority")
        params["priority"] = priority
    
    query = text(f"""
        SELECT id, project_id, milestone_id, user_id, title, description,
               estimated_minutes, status, due_date, "order", priority,
               depends_on_task, created_at
        FROM tasks
        WHERE {' AND '.join(where_conditions)}
        ORDER BY "order" ASC, created_at ASC
    """)
    
    result = await db.execute(query, params)
    tasks = result.mappings().all()
    
    return [
        TaskResponse(
            id=str(task["id"]),
            project_id=str(task["project_id"]) if task["project_id"] else None,
            milestone_id=str(task["milestone_id"]) if task["milestone_id"] else None,
            user_id=task["user_id"],
            title=task["title"],
            description=task["description"],
            estimated_minutes=task["estimated_minutes"],
            status=task["status"],
            due_date=task["due_date"],
            order=task["order"],
            priority=task["priority"],
            depends_on_task=str(task["depends_on_task"]) if task["depends_on_task"] else None,
            created_at=task["created_at"],
        )
        for task in tasks
    ]


@task_router.post("/tasks/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task (solo, project, or milestone)."""
    task_id = str(uuid4())
    user_id = current_user["clerk_user_id"]
    
    # Verify project ownership if project_id is provided
    if task.project_id:
        if not await verify_project_ownership(task.project_id, user_id, db):
            raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify milestone belongs to project if milestone_id is provided
    if task.milestone_id:
        if not task.project_id:
            raise HTTPException(
                status_code=422,
                detail="milestone_id requires project_id to be set"
            )
        if not await verify_milestone_ownership(task.milestone_id, task.project_id, db):
            raise HTTPException(status_code=404, detail="Milestone not found in project")
    
    # Verify depends_on_task if provided
    if task.depends_on_task:
        if task.depends_on_task == task_id:
            raise HTTPException(
                status_code=422,
                detail="Task cannot depend on itself"
            )
        if not await verify_task_ownership(task.depends_on_task, user_id, db):
            raise HTTPException(status_code=404, detail="Dependency task not found")
    
    query = text("""
        INSERT INTO tasks (id, project_id, milestone_id, user_id, title, description,
                          estimated_minutes, status, due_date, "order", priority, depends_on_task)
        VALUES (:id, :project_id, :milestone_id, :user_id, :title, :description,
                :estimated_minutes, :status, :due_date, :order, :priority, :depends_on_task)
        RETURNING id, project_id, milestone_id, user_id, title, description,
                  estimated_minutes, status, due_date, "order", priority,
                  depends_on_task, created_at
    """)
    
    result = await db.execute(
        query,
        {
            "id": task_id,
            "project_id": task.project_id,
            "milestone_id": task.milestone_id,
            "user_id": user_id,
            "title": task.title,
            "description": task.description,
            "estimated_minutes": task.estimated_minutes,
            "status": task.status.value if task.status else TaskStatus.pending.value,
            "due_date": task.due_date,
            "order": task.order if task.order is not None else 0,
            "priority": task.priority if task.priority is not None else False,
            "depends_on_task": task.depends_on_task,
        },
    )
    await db.commit()
    
    task_row = result.mappings().first()
    
    return TaskResponse(
        id=str(task_row["id"]),
        project_id=str(task_row["project_id"]) if task_row["project_id"] else None,
        milestone_id=str(task_row["milestone_id"]) if task_row["milestone_id"] else None,
        user_id=task_row["user_id"],
        title=task_row["title"],
        description=task_row["description"],
        estimated_minutes=task_row["estimated_minutes"],
        status=task_row["status"],
        due_date=task_row["due_date"],
        order=task_row["order"],
        priority=task_row["priority"],
        depends_on_task=str(task_row["depends_on_task"]) if task_row["depends_on_task"] else None,
        created_at=task_row["created_at"],
    )


@task_router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single task."""
    query = text("""
        SELECT id, project_id, milestone_id, user_id, title, description,
               estimated_minutes, status, due_date, "order", priority,
               depends_on_task, created_at
        FROM tasks
        WHERE id = :id AND user_id = :user_id
    """)
    
    result = await db.execute(
        query, {"id": task_id, "user_id": current_user["clerk_user_id"]}
    )
    task_row = result.mappings().first()
    
    if not task_row:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResponse(
        id=str(task_row["id"]),
        project_id=str(task_row["project_id"]) if task_row["project_id"] else None,
        milestone_id=str(task_row["milestone_id"]) if task_row["milestone_id"] else None,
        user_id=task_row["user_id"],
        title=task_row["title"],
        description=task_row["description"],
        estimated_minutes=task_row["estimated_minutes"],
        status=task_row["status"],
        due_date=task_row["due_date"],
        order=task_row["order"],
        priority=task_row["priority"],
        depends_on_task=str(task_row["depends_on_task"]) if task_row["depends_on_task"] else None,
        created_at=task_row["created_at"],
    )


@task_router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_update: TaskUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a task."""
    user_id = current_user["clerk_user_id"]
    
    # Get only the fields that were actually provided
    update_data = task_update.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided for update")
    
    # Verify ownership/references if changing project_id, milestone_id, or depends_on_task
    if "project_id" in update_data and update_data["project_id"]:
        if not await verify_project_ownership(update_data["project_id"], user_id, db):
            raise HTTPException(status_code=404, detail="Project not found")
    
    if "milestone_id" in update_data and update_data["milestone_id"]:
        project_id = update_data.get("project_id")
        if not project_id:
            # Get current project_id if not being updated
            query = text("SELECT project_id FROM tasks WHERE id = :id AND user_id = :user_id")
            result = await db.execute(query, {"id": task_id, "user_id": user_id})
            current = result.mappings().first()
            if not current:
                raise HTTPException(status_code=404, detail="Task not found")
            project_id = current["project_id"]
        
        if not project_id:
            raise HTTPException(
                status_code=422,
                detail="milestone_id requires project_id to be set"
            )
        
        if not await verify_milestone_ownership(update_data["milestone_id"], project_id, db):
            raise HTTPException(status_code=404, detail="Milestone not found in project")
    
    if "depends_on_task" in update_data and update_data["depends_on_task"]:
        if update_data["depends_on_task"] == task_id:
            raise HTTPException(
                status_code=422,
                detail="Task cannot depend on itself"
            )
        if not await verify_task_ownership(update_data["depends_on_task"], user_id, db):
            raise HTTPException(status_code=404, detail="Dependency task not found")
    
    # Build dynamic SET clause
    set_clauses = []
    params = {"id": task_id, "user_id": user_id}
    
    for field, value in update_data.items():
        if field == "order":
            set_clauses.append('"order" = :order')
        elif field == "status" and value is not None:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value.value
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value
    
    query = text(f"""
        UPDATE tasks
        SET {', '.join(set_clauses)}
        WHERE id = :id AND user_id = :user_id
        RETURNING id, project_id, milestone_id, user_id, title, description,
                  estimated_minutes, status, due_date, "order", priority,
                  depends_on_task, created_at
    """)
    
    result = await db.execute(query, params)
    await db.commit()
    
    task_row = result.mappings().first()
    
    if not task_row:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResponse(
        id=str(task_row["id"]),
        project_id=str(task_row["project_id"]) if task_row["project_id"] else None,
        milestone_id=str(task_row["milestone_id"]) if task_row["milestone_id"] else None,
        user_id=task_row["user_id"],
        title=task_row["title"],
        description=task_row["description"],
        estimated_minutes=task_row["estimated_minutes"],
        status=task_row["status"],
        due_date=task_row["due_date"],
        order=task_row["order"],
        priority=task_row["priority"],
        depends_on_task=str(task_row["depends_on_task"]) if task_row["depends_on_task"] else None,
        created_at=task_row["created_at"],
    )


@task_router.delete("/tasks/{task_id}", response_model=SuccessResponse)
async def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task (hard delete)."""
    query = text("""
        DELETE FROM tasks
        WHERE id = :id AND user_id = :user_id
        RETURNING id
    """)
    
    result = await db.execute(
        query, {"id": task_id, "user_id": current_user["clerk_user_id"]}
    )
    await db.commit()
    
    deleted_row = result.mappings().first()
    
    if not deleted_row:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return SuccessResponse(
        success=True,
        data={"id": task_id, "message": "Task deleted successfully"},
    )


# Project-nested convenience routes

@router.get("/{project_id}/tasks", response_model=List[TaskResponse])
async def list_project_tasks(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks for a project."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    query = text("""
        SELECT id, project_id, milestone_id, user_id, title, description,
               estimated_minutes, status, due_date, "order", priority,
               depends_on_task, created_at
        FROM tasks
        WHERE project_id = :project_id
        ORDER BY milestone_id NULLS LAST, "order" ASC
    """)
    
    result = await db.execute(query, {"project_id": project_id})
    tasks = result.mappings().all()
    
    return [
        TaskResponse(
            id=str(task["id"]),
            project_id=str(task["project_id"]),
            milestone_id=str(task["milestone_id"]) if task["milestone_id"] else None,
            user_id=task["user_id"],
            title=task["title"],
            description=task["description"],
            estimated_minutes=task["estimated_minutes"],
            status=task["status"],
            due_date=task["due_date"],
            order=task["order"],
            priority=task["priority"],
            depends_on_task=str(task["depends_on_task"]) if task["depends_on_task"] else None,
            created_at=task["created_at"],
        )
        for task in tasks
    ]


@router.get(
    "/{project_id}/milestones/{milestone_id}/tasks", response_model=List[TaskResponse]
)
async def list_milestone_tasks(
    project_id: str,
    milestone_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks for a milestone."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify milestone belongs to project
    if not await verify_milestone_ownership(milestone_id, project_id, db):
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    query = text("""
        SELECT id, project_id, milestone_id, user_id, title, description,
               estimated_minutes, status, due_date, "order", priority,
               depends_on_task, created_at
        FROM tasks
        WHERE milestone_id = :milestone_id
        ORDER BY "order" ASC
    """)
    
    result = await db.execute(query, {"milestone_id": milestone_id})
    tasks = result.mappings().all()
    
    return [
        TaskResponse(
            id=str(task["id"]),
            project_id=str(task["project_id"]),
            milestone_id=str(task["milestone_id"]),
            user_id=task["user_id"],
            title=task["title"],
            description=task["description"],
            estimated_minutes=task["estimated_minutes"],
            status=task["status"],
            due_date=task["due_date"],
            order=task["order"],
            priority=task["priority"],
            depends_on_task=str(task["depends_on_task"]) if task["depends_on_task"] else None,
            created_at=task["created_at"],
        )
        for task in tasks
    ]
