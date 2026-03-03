from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from uuid import UUID

from models.db import User
from models.schemas import UserCreate, UserUpdate, UserResponse

async def create_or_update_user(
    db: AsyncSession,
    user_data: UserCreate
) -> User:
    """Create a new user or update existing one based on clerk_id."""
    # Check if user already exists
    stmt = select(User).where(User.clerk_id == user_data.clerk_id)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        # Update existing user
        existing_user.email = user_data.email
        existing_user.first_name = user_data.first_name
        existing_user.last_name = user_data.last_name
        await db.flush()
        return existing_user
    else:
        # Create new user
        new_user = User(
            clerk_id=user_data.clerk_id,
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name
        )
        db.add(new_user)
        await db.flush()
        return new_user

async def get_user_by_clerk_id(
    db: AsyncSession,
    clerk_id: str
) -> Optional[User]:
    """Get user by Clerk ID."""
    async with db.begin():
        stmt = select(User).where(User.clerk_id == clerk_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

async def get_user_by_id(
    db: AsyncSession,
    user_id: str
) -> Optional[User]:
    """Get user by clerk_id."""
    async with db.begin():
        stmt = select(User).where(User.clerk_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

async def update_user(
    db: AsyncSession,
    user_id: str,
    user_update: UserUpdate
) -> Optional[User]:
    """Update user profile."""
    async with db.begin():
        stmt = select(User).where(User.clerk_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        # Update only provided fields
        if user_update.email is not None:
            user.email = user_update.email
        if user_update.first_name is not None:
            user.first_name = user_update.first_name
        if user_update.last_name is not None:
            user.last_name = user_update.last_name
        
        await db.flush()
        return user
