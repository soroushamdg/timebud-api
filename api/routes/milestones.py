from typing import List
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import get_current_user
from database import get_db
from schemas import MilestoneCreate, MilestoneUpdate, MilestoneResponse, SuccessResponse

router = APIRouter(prefix="/projects", tags=["milestones"])


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


@router.get("/{project_id}/milestones/", response_model=List[MilestoneResponse])
async def list_milestones(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all milestones for a project."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    query = text("""
        SELECT id, project_id, title, description, target_date, "order", created_at
        FROM milestones
        WHERE project_id = :project_id
        ORDER BY "order" ASC
    """)
    
    result = await db.execute(query, {"project_id": project_id})
    milestones = result.mappings().all()
    
    return [
        MilestoneResponse(
            id=str(milestone["id"]),
            project_id=str(milestone["project_id"]),
            title=milestone["title"],
            description=milestone["description"],
            target_date=milestone["target_date"],
            order=milestone["order"],
            created_at=milestone["created_at"],
        )
        for milestone in milestones
    ]


@router.post(
    "/{project_id}/milestones/",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_milestone(
    project_id: str,
    milestone: MilestoneCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new milestone."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check if order already exists
    check_query = text("""
        SELECT 1 FROM milestones
        WHERE project_id = :project_id AND "order" = :order
    """)
    
    existing = await db.execute(
        check_query, {"project_id": project_id, "order": milestone.order}
    )
    if existing.scalar():
        raise HTTPException(
            status_code=409,
            detail=f"A milestone with order={milestone.order} already exists in this project",
        )
    
    milestone_id = str(uuid4())
    
    query = text("""
        INSERT INTO milestones (id, project_id, title, description, target_date, "order")
        VALUES (:id, :project_id, :title, :description, :target_date, :order)
        RETURNING id, project_id, title, description, target_date, "order", created_at
    """)
    
    result = await db.execute(
        query,
        {
            "id": milestone_id,
            "project_id": project_id,
            "title": milestone.title,
            "description": milestone.description,
            "target_date": milestone.target_date,
            "order": milestone.order,
        },
    )
    await db.commit()
    
    milestone_row = result.mappings().first()
    
    return MilestoneResponse(
        id=str(milestone_row["id"]),
        project_id=str(milestone_row["project_id"]),
        title=milestone_row["title"],
        description=milestone_row["description"],
        target_date=milestone_row["target_date"],
        order=milestone_row["order"],
        created_at=milestone_row["created_at"],
    )


@router.get("/{project_id}/milestones/{milestone_id}", response_model=MilestoneResponse)
async def get_milestone(
    project_id: str,
    milestone_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single milestone."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    query = text("""
        SELECT id, project_id, title, description, target_date, "order", created_at
        FROM milestones
        WHERE id = :id AND project_id = :project_id
    """)
    
    result = await db.execute(
        query, {"id": milestone_id, "project_id": project_id}
    )
    milestone_row = result.mappings().first()
    
    if not milestone_row:
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    return MilestoneResponse(
        id=str(milestone_row["id"]),
        project_id=str(milestone_row["project_id"]),
        title=milestone_row["title"],
        description=milestone_row["description"],
        target_date=milestone_row["target_date"],
        order=milestone_row["order"],
        created_at=milestone_row["created_at"],
    )


@router.patch(
    "/{project_id}/milestones/{milestone_id}", response_model=MilestoneResponse
)
async def update_milestone(
    project_id: str,
    milestone_id: str,
    milestone_update: MilestoneUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partially update a milestone."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get only the fields that were actually provided
    update_data = milestone_update.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided for update")
    
    # If order is being changed, check for conflicts
    if "order" in update_data:
        check_query = text("""
            SELECT 1 FROM milestones
            WHERE project_id = :project_id AND "order" = :order AND id != :id
        """)
        existing = await db.execute(
            check_query,
            {
                "project_id": project_id,
                "order": update_data["order"],
                "id": milestone_id,
            },
        )
        if existing.scalar():
            raise HTTPException(
                status_code=409,
                detail=f"A milestone with order={update_data['order']} already exists in this project",
            )
    
    # Build dynamic SET clause
    set_clauses = []
    params = {"id": milestone_id, "project_id": project_id}
    
    for field, value in update_data.items():
        if field == "order":
            set_clauses.append('"order" = :order')
        else:
            set_clauses.append(f"{field} = :{field}")
        params[field] = value
    
    query = text(f"""
        UPDATE milestones
        SET {', '.join(set_clauses)}
        WHERE id = :id AND project_id = :project_id
        RETURNING id, project_id, title, description, target_date, "order", created_at
    """)
    
    result = await db.execute(query, params)
    await db.commit()
    
    milestone_row = result.mappings().first()
    
    if not milestone_row:
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    return MilestoneResponse(
        id=str(milestone_row["id"]),
        project_id=str(milestone_row["project_id"]),
        title=milestone_row["title"],
        description=milestone_row["description"],
        target_date=milestone_row["target_date"],
        order=milestone_row["order"],
        created_at=milestone_row["created_at"],
    )


@router.delete(
    "/{project_id}/milestones/{milestone_id}", response_model=SuccessResponse
)
async def delete_milestone(
    project_id: str,
    milestone_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a milestone (hard delete)."""
    # Verify project ownership
    if not await verify_project_ownership(
        project_id, current_user["clerk_user_id"], db
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    
    query = text("""
        DELETE FROM milestones
        WHERE id = :id AND project_id = :project_id
        RETURNING id
    """)
    
    result = await db.execute(
        query, {"id": milestone_id, "project_id": project_id}
    )
    await db.commit()
    
    deleted_row = result.mappings().first()
    
    if not deleted_row:
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    return SuccessResponse(
        success=True,
        data={"id": milestone_id, "message": "Milestone deleted successfully"},
    )
