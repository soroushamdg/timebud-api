from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
import httpx
import os

from database import get_db
from auth import get_current_user
from models.schemas import UserCreate, UserResponse
from services import user_service

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/register", response_model=UserResponse)
async def register_user(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> UserResponse:
    print(f"DEBUG: Environment variables - CLERK_SECRET_KEY: {bool(os.getenv('CLERK_SECRET_KEY'))}")
    print(f"DEBUG: Current user data: {list(current_user.keys())}")
    """
    Register/upsert user on first login.
    Creates a new user or updates existing one based on clerk_id.
    """
    # Extract user data from JWT token
    clerk_user_id = current_user["clerk_user_id"]
    
    # Try to fetch user profile from Clerk API
    email = current_user.get("email")
    first_name = current_user.get("first_name")
    last_name = current_user.get("last_name")
    
    if not email:
        try:
            # Get Clerk secret key from environment
            clerk_secret_key = os.getenv("CLERK_SECRET_KEY")
            print(f"DEBUG: Clerk secret key exists: {bool(clerk_secret_key)}")
            if clerk_secret_key:
                async with httpx.AsyncClient() as client:
                    # Use the standard Clerk API URL
                    clerk_api_url = "https://api.clerk.dev"
                    print(f"DEBUG: Using Clerk API URL: {clerk_api_url}")
                    response = await client.get(
                        f"{clerk_api_url}/v1/users/{clerk_user_id}",
                        headers={"Authorization": f"Bearer {clerk_secret_key}"}
                    )
                    print(f"DEBUG: Clerk API status: {response.status_code}")
                    if response.status_code == 200:
                        clerk_user = response.json()
                        print(f"DEBUG: Got user data, email_addresses count: {len(clerk_user.get('email_addresses', []))}")
                        # Extract email from primary email address
                        email_addresses = clerk_user.get("email_addresses", [])
                        if email_addresses:
                            primary_email = next((ea for ea in email_addresses if ea.get("id") == clerk_user.get("primary_email_address_id")), email_addresses[0])
                            email = primary_email.get("email_address")
                            print(f"DEBUG: Extracted email: {email}")
                        
                        # Get name fields
                        first_name = clerk_user.get("first_name") or first_name
                        last_name = clerk_user.get("last_name") or last_name
                        print(f"DEBUG: Names: {first_name} {last_name}")
                    else:
                        print(f"DEBUG: Clerk API error: {response.text}")
        except Exception as e:
            print(f"DEBUG: Clerk API exception: {e}")
    
    # Use fallback values if still missing
    email = email or f"user_{clerk_user_id}@example.com"
    first_name = first_name or "User"
    last_name = last_name or clerk_user_id[:8]  # Short ID as last name
    
    user_data = UserCreate(
        clerk_id=clerk_user_id,
        email=email,
        first_name=first_name,
        last_name=last_name
    )
    
    # Create or update user
    async with db.begin():
        user = await user_service.create_or_update_user(db, user_data)
        # The transaction will be committed when exiting the context
    
    return UserResponse.model_validate(user)

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> UserResponse:
    """
    Get current user's profile.
    """
    clerk_id = current_user["clerk_user_id"]
    
    # Get user from database
    user = await user_service.get_user_by_clerk_id(db, clerk_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )
    
    return UserResponse.model_validate(user)
