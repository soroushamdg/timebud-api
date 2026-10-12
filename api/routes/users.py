from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from auth import get_current_user
from database import get_db
from schemas import SuccessResponse

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/me", response_model=SuccessResponse)
async def upsert_current_user(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upsert current user on first login."""
    query = text("""
        INSERT INTO users (id, email, first_name, last_name)
        VALUES (:id, :email, :first_name, :last_name)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name
        RETURNING id, email, first_name, last_name, created_at
    """)
    
    result = await db.execute(
        query,
        {
            "id": current_user["clerk_user_id"],
            "email": current_user["email"],
            "first_name": current_user["first_name"],
            "last_name": current_user["last_name"],
        },
    )
    await db.commit()
    
    user_row = result.mappings().first()
    
    return SuccessResponse(
        success=True,
        data={
            "id": user_row["id"],
            "email": user_row["email"],
            "first_name": user_row["first_name"],
            "last_name": user_row["last_name"],
            "created_at": user_row["created_at"].isoformat(),
        },
    )


@router.get("/me", response_model=SuccessResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile."""
    query = text("""
        SELECT id, email, first_name, last_name, created_at
        FROM users
        WHERE id = :id
    """)
    
    result = await db.execute(query, {"id": current_user["clerk_user_id"]})
    user_row = result.mappings().first()
    
    if not user_row:
        raise HTTPException(
            status_code=404,
            detail="User not found. Call POST /users/me to register.",
        )
    
    return SuccessResponse(
        success=True,
        data={
            "id": user_row["id"],
            "email": user_row["email"],
            "first_name": user_row["first_name"],
            "last_name": user_row["last_name"],
            "created_at": user_row["created_at"].isoformat(),
        },
    )
