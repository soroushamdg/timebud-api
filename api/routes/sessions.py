from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import get_current_user
from database import get_db
from schemas import SessionPlanRequest, SessionUpdateRequest, SessionResponse, SessionTaskItem, SuccessResponse
from planner import plan_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def load_user_data(
    user_id: str, db: AsyncSession
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load user's projects, milestones, and tasks as plain dicts with UUIDs as strings."""
    
    # Load active projects
    projects_query = text("""
        SELECT id, name, deadline, priority, status
        FROM projects
        WHERE user_id = :user_id AND status = 'active'
    """)
    projects_result = await db.execute(projects_query, {"user_id": user_id})
    projects = []
    for row in projects_result.mappings():
        projects.append({
            "id": str(row["id"]),
            "name": row["name"],
            "deadline": row["deadline"].strftime("%Y-%m-%d") if row["deadline"] else None,
            "priority": row["priority"],
            "status": row["status"]
        })
    
    # Load milestones for active projects
    milestones_query = text("""
        SELECT m.id, m.project_id, m.title, m.order
        FROM milestones m
        JOIN projects p ON p.id = m.project_id
        WHERE p.user_id = :user_id AND p.status = 'active'
    """)
    milestones_result = await db.execute(milestones_query, {"user_id": user_id})
    milestones = []
    for row in milestones_result.mappings():
        milestones.append({
            "id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "title": row["title"],
            "order": row["order"]
        })
    
    # Load pending tasks
    tasks_query = text("""
        SELECT id, project_id, milestone_id, title, estimated_minutes, 
               status, due_date, "order", priority, depends_on_task
        FROM tasks
        WHERE user_id = :user_id AND status = 'pending'
    """)
    tasks_result = await db.execute(tasks_query, {"user_id": user_id})
    tasks = []
    for row in tasks_result.mappings():
        tasks.append({
            "id": str(row["id"]),
            "project_id": str(row["project_id"]) if row["project_id"] else None,
            "milestone_id": str(row["milestone_id"]) if row["milestone_id"] else None,
            "title": row["title"],
            "estimated_minutes": row["estimated_minutes"],
            "status": row["status"],
            "due_date": row["due_date"].strftime("%Y-%m-%d") if row["due_date"] else None,
            "order": row["order"],
            "priority": row["priority"],
            "depends_on_task": str(row["depends_on_task"]) if row["depends_on_task"] else None
        })
    
    return projects, milestones, tasks


@router.post("/plan", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def plan_and_create_session(
    request: SessionPlanRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run planning algorithm and create session."""
    if request.budget_minutes < 15:
        raise HTTPException(
            status_code=422,
            detail="Budget must be at least 15 minutes"
        )
    
    user_id = current_user["clerk_user_id"]
    
    # Load user data
    projects, milestones, tasks = await load_user_data(user_id, db)
    
    # Filter out excluded projects
    if request.excluded_project_ids:
        excluded_ids = [str(pid) for pid in request.excluded_project_ids]
        projects = [p for p in projects if p["id"] not in excluded_ids]
    
    # Run planner
    plan = plan_session(projects, milestones, tasks, request.budget_minutes)
    
    if plan["task_count"] == 0:
        raise HTTPException(
            status_code=422,
            detail="No tasks could be scheduled with the given budget. Try increasing the budget or excluding fewer projects."
        )
    
    # Extract task IDs from plan
    task_ids = [task["task_id"] for task in plan["tasks"]]
    
    # Create session
    session_id = str(uuid4())
    insert_query = text("""
        INSERT INTO sessions (id, user_id, budget_minutes, tasks_list)
        VALUES (:id, :user_id, :budget_minutes, :tasks_list)
        RETURNING id, user_id, budget_minutes, start_time, end_time, tasks_list, created_at
    """)
    
    result = await db.execute(
        insert_query,
        {
            "id": session_id,
            "user_id": user_id,
            "budget_minutes": request.budget_minutes,
            "tasks_list": task_ids
        }
    )
    await db.commit()
    
    session_row = result.mappings().first()
    
    # Convert plan tasks to SessionTaskItem format
    planned_tasks = [
        SessionTaskItem(
            position=task["position"],
            task_id=task["task_id"],
            project_id=task["project_id"],
            is_solo=task["is_solo"],
            tier1=task["tier1"],
            milestone_title=task["milestone_title"],
            title=task["title"],
            priority=task["priority"],
            scheduled_minutes=task["scheduled_minutes"],
            partial=task["partial"],
            carry_over_minutes=task["carry_over_minutes"]
        )
        for task in plan["tasks"]
    ]
    
    return SessionResponse(
        id=str(session_row["id"]),
        user_id=session_row["user_id"],
        budget_minutes=session_row["budget_minutes"],
        start_time=session_row["start_time"],
        end_time=session_row["end_time"],
        tasks_list=session_row["tasks_list"],
        planned_tasks=planned_tasks,
        created_at=session_row["created_at"]
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a session by ID."""
    query = text("""
        SELECT id, user_id, budget_minutes, start_time, end_time, tasks_list, created_at
        FROM sessions
        WHERE id = :id AND user_id = :user_id
    """)
    
    result = await db.execute(
        query, 
        {"id": session_id, "user_id": current_user["clerk_user_id"]}
    )
    session_row = result.mappings().first()
    
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Reconstruct planned_tasks from tasks_list
    planned_tasks = []
    if session_row["tasks_list"]:
        # Query task details
        tasks_query = text("""
            SELECT t.id, t.project_id, t.milestone_id, t.title, t.priority,
                   t.estimated_minutes, p.name as project_name, m.title as milestone_title
            FROM tasks t
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN milestones m ON t.milestone_id = m.id
            WHERE t.id = ANY(:task_ids)
        """)
        
        tasks_result = await db.execute(
            tasks_query, 
            {"task_ids": session_row["tasks_list"]}
        )
        tasks_map = {
            str(row["id"]): row 
            for row in tasks_result.mappings()
        }
        
        # Preserve order from tasks_list
        for position, task_id in enumerate(session_row["tasks_list"]):
            if task_id in tasks_map:
                task = tasks_map[task_id]
                planned_tasks.append(SessionTaskItem(
                    position=position,
                    task_id=task_id,
                    project_id=str(task["project_id"]) if task["project_id"] else None,
                    is_solo=task["project_id"] is None,
                    tier1=False,  # We don't have this info, default to False
                    milestone_title=task["milestone_title"],
                    title=task["title"],
                    priority=task["priority"],
                    scheduled_minutes=task["estimated_minutes"] or 25,
                    partial=False,  # We don't have this info
                    carry_over_minutes=0  # We don't have this info
                ))
    
    return SessionResponse(
        id=str(session_row["id"]),
        user_id=session_row["user_id"],
        budget_minutes=session_row["budget_minutes"],
        start_time=session_row["start_time"],
        end_time=session_row["end_time"],
        tasks_list=session_row["tasks_list"],
        planned_tasks=planned_tasks,
        created_at=session_row["created_at"]
    )


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update or submit a session."""
    user_id = current_user["clerk_user_id"]
    
    # Check which fields were provided
    update_data = request.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided for update")
    
    # Get current session
    current_query = text("""
        SELECT id, budget_minutes, tasks_list
        FROM sessions
        WHERE id = :id AND user_id = :user_id
    """)
    
    current_result = await db.execute(
        current_query,
        {"id": session_id, "user_id": user_id}
    )
    current_session = current_result.mappings().first()
    
    if not current_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Handle budget_minutes change (re-plan)
    if "budget_minutes" in update_data and update_data["budget_minutes"] != current_session["budget_minutes"]:
        # Load user data and re-run planner
        projects, milestones, tasks = await load_user_data(user_id, db)
        
        # Run planner with new budget
        plan = plan_session(projects, milestones, tasks, update_data["budget_minutes"])
        
        if plan["task_count"] == 0:
            raise HTTPException(
                status_code=422,
                detail="No tasks could be scheduled with the new budget."
            )
        
        # Update tasks_list with new plan
        update_data["tasks_list"] = [task["task_id"] for task in plan["tasks"]]
    
    # Build update query
    set_clauses = []
    params = {"id": session_id, "user_id": user_id}
    
    for field, value in update_data.items():
        set_clauses.append(f"{field} = :{field}")
        params[field] = value
    
    update_query = text(f"""
        UPDATE sessions
        SET {', '.join(set_clauses)}
        WHERE id = :id AND user_id = :user_id
        RETURNING id, user_id, budget_minutes, start_time, end_time, tasks_list, created_at
    """)
    
    result = await db.execute(update_query, params)
    await db.commit()
    
    updated_session = result.mappings().first()
    
    if not updated_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Reconstruct planned_tasks
    planned_tasks = []
    if updated_session["tasks_list"]:
        # If we just re-planned, use the plan data
        if "budget_minutes" in update_data and update_data["budget_minutes"] != current_session["budget_minutes"]:
            planned_tasks = [
                SessionTaskItem(
                    position=task["position"],
                    task_id=task["task_id"],
                    project_id=task["project_id"],
                    is_solo=task["is_solo"],
                    tier1=task["tier1"],
                    milestone_title=task["milestone_title"],
                    title=task["title"],
                    priority=task["priority"],
                    scheduled_minutes=task["scheduled_minutes"],
                    partial=task["partial"],
                    carry_over_minutes=task["carry_over_minutes"]
                )
                for task in plan["tasks"]
            ]
        else:
            # Query task details for manual edits
            tasks_query = text("""
                SELECT t.id, t.project_id, t.milestone_id, t.title, t.priority,
                       t.estimated_minutes, p.name as project_name, m.title as milestone_title
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                LEFT JOIN milestones m ON t.milestone_id = m.id
                WHERE t.id = ANY(:task_ids)
            """)
            
            tasks_result = await db.execute(
                tasks_query,
                {"task_ids": updated_session["tasks_list"]}
            )
            tasks_map = {
                str(row["id"]): row
                for row in tasks_result.mappings()
            }
            
            for position, task_id in enumerate(updated_session["tasks_list"]):
                if task_id in tasks_map:
                    task = tasks_map[task_id]
                    planned_tasks.append(SessionTaskItem(
                        position=position,
                        task_id=task_id,
                        project_id=str(task["project_id"]) if task["project_id"] else None,
                        is_solo=task["project_id"] is None,
                        tier1=False,
                        milestone_title=task["milestone_title"],
                        title=task["title"],
                        priority=task["priority"],
                        scheduled_minutes=task["estimated_minutes"] or 25,
                        partial=False,
                        carry_over_minutes=0
                    ))
    
    return SessionResponse(
        id=str(updated_session["id"]),
        user_id=updated_session["user_id"],
        budget_minutes=updated_session["budget_minutes"],
        start_time=updated_session["start_time"],
        end_time=updated_session["end_time"],
        tasks_list=updated_session["tasks_list"],
        planned_tasks=planned_tasks,
        created_at=updated_session["created_at"]
    )


@router.delete("/{session_id}", response_model=SuccessResponse)
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session."""
    query = text("""
        DELETE FROM sessions
        WHERE id = :id AND user_id = :user_id
        RETURNING id
    """)
    
    result = await db.execute(
        query,
        {"id": session_id, "user_id": current_user["clerk_user_id"]}
    )
    await db.commit()
    
    deleted_row = result.mappings().first()
    
    if not deleted_row:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SuccessResponse(
        success=True,
        data={"id": session_id, "message": "Session deleted successfully"}
    )
