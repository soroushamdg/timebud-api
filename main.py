from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from database import get_db, engine
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import auth
from auth import init_jwks_client

# Import routers
from api.routes import users, projects, tasks, sessions

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up TimeBud API...")
    # Initialize JWKS client for Clerk JWT verification
    await init_jwks_client()
    yield
    # Shutdown
    print("Shutting down TimeBud API...")

app = FastAPI(
    title="TimeBud API",
    description="API for students with ADHD to manage time and tasks",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "https://timebud-web.vercel.app",  # Production frontend on Vercel
        "https://timebud.vercel.app",  # Alternative production domain
        "https://*.vercel.app"  # Allow Vercel preview deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(tasks.router)  # For milestone/task endpoints
app.include_router(tasks.task_router)  # For task-specific endpoints
app.include_router(sessions.router)

@app.post("/debug/jwt")
async def debug_jwt(request: dict):
    """Debug endpoint to check JWT token format (no auth required)"""
    import base64
    import json
    from datetime import datetime, timezone
    
    try:
        token = request.get("token", "")
        # Remove Bearer prefix if present
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Split and decode header
        parts = token.split('.')
        header_padding = 4 - len(parts[0]) % 4
        header = base64.urlsafe_b64decode(parts[0] + '=' * header_padding)
        
        payload_padding = 4 - len(parts[1]) % 4
        payload = base64.urlsafe_b64decode(parts[1] + '=' * payload_padding)
        
        payload_data = json.loads(payload)
        
        # Check expiration
        exp = payload_data.get('exp')
        server_time = datetime.now(timezone.utc)
        token_exp_time = datetime.fromtimestamp(exp, timezone.utc) if exp else None
        
        return {
            "header": json.loads(header),
            "payload": payload_data,
            "parts_count": len(parts),
            "server_utc_time": server_time.isoformat(),
            "token_expires_utc": token_exp_time.isoformat() if token_exp_time else None,
            "time_until_expiry": str(token_exp_time - server_time) if token_exp_time else None,
            "is_expired": server_time > token_exp_time if token_exp_time else None
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Comprehensive health check endpoint."""
    from datetime import datetime
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "service": "timebud-api",
        "checks": {}
    }
    
    # Database connectivity check
    try:
        result = await db.execute(text("SELECT 1"))
        await result.fetchone()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "connection": "successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Clerk JWKS availability check
    try:
        from auth import get_jwks_client
        jwks_client = get_jwks_client()
        # Test JWKS retrieval
        signing_keys = jwks_client.get_signing_keys()
        health_status["checks"]["clerk_jwks"] = {
            "status": "healthy",
            "keys_available": len(signing_keys)
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["checks"]["clerk_jwks"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Environment variables check
    required_env_vars = ["DATABASE_URL", "CLERK_JWKS_URL"]
    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        health_status["status"] = "degraded"
        health_status["checks"]["environment"] = {
            "status": "unhealthy",
            "missing_variables": missing_vars
        }
    else:
        health_status["checks"]["environment"] = {
            "status": "healthy",
            "required_vars_set": len(required_env_vars)
        }
    
    # Database schema check (basic)
    try:
        schema_check = await db.execute(text("""
            SELECT COUNT(*) as table_count 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('users', 'projects')
        """))
        table_count = schema_check.scalar()
        
        if table_count >= 2:
            health_status["checks"]["database_schema"] = {
                "status": "healthy",
                "core_tables": table_count
            }
        else:
            health_status["status"] = "degraded"
            health_status["checks"]["database_schema"] = {
                "status": "unhealthy",
                "core_tables": table_count,
                "expected": 2
            }
    except Exception as e:
        health_status["checks"]["database_schema"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # User count check (optional performance indicator)
    try:
        user_count = await db.execute(text("SELECT COUNT(*) FROM users"))
        count = user_count.scalar()
        health_status["checks"]["user_metrics"] = {
            "status": "healthy",
            "total_users": count
        }
    except Exception as e:
        health_status["checks"]["user_metrics"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    return health_status