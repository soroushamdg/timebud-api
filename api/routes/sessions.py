from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List
from uuid import UUID

from database import get_db
from auth import get_current_user
from models.schemas import SessionCreate, SessionResponse, SessionTaskResponse
from services import session_service, user_service

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> SessionResponse:
    """
    Create a new session (stub implementation for now).
    Creates a session row but returns an empty task list.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    try:
        # Create session
        session = await session_service.create_session(db, clerk_id, session_data)
        return SessionResponse.model_validate(session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.get("/{session_id}/tasks", response_model=List[SessionTaskResponse])
async def get_session_tasks(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[SessionTaskResponse]:
    """
    Get all tasks for a session.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # Get session tasks
    session_tasks = await session_service.get_session_tasks(db, session_id, clerk_id)
    
    return [SessionTaskResponse.model_validate(task) for task in session_tasks]

@router.post("/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> SessionResponse:
    """
    End a session by setting end_time and calculating duration.
    """
    # Use clerk_id directly since it's now the primary key
    clerk_id = current_user["clerk_user_id"]
    
    # End session
    session = await session_service.end_session(db, session_id, clerk_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied."
        )
    
    return SessionResponse.model_validate(session)
