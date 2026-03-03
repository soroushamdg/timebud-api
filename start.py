#!/usr/bin/env python3
"""
Startup script that validates environment variables before starting the server.
This provides clearer error messages during Railway deployment.
"""

import os
import sys
from dotenv import load_dotenv

def validate_environment():
    """Validate that all required environment variables are set."""
    load_dotenv()
    
    required_vars = [
        "DATABASE_URL",
        "CLERK_JWKS_URL"
    ]
    
    optional_vars = [
        "CLERK_SECRET_KEY"
    ]
    
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease set these variables in your Railway dashboard.")
        print("\nFor DATABASE_URL, use the PostgreSQL connection string provided by Railway.")
        print("For CLERK_JWKS_URL, use: https://your-clerk-domain.clerk.accounts.dev/.well-known/jwks.json")
        sys.exit(1)
    
    # Check optional variables
    missing_optional = []
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
    
    if missing_optional:
        print("⚠️  Missing optional environment variables:")
        for var in missing_optional:
            print(f"   - {var}")
        print("   (These are optional but may limit functionality)")
    
    print("✅ Environment validation passed")
    
    # Validate DATABASE_URL format
    db_url = os.getenv("DATABASE_URL")
    if not db_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        print("❌ DATABASE_URL must be a PostgreSQL connection string")
        print(f"   Current format: {db_url[:50]}...")
        sys.exit(1)
    
    print("✅ DATABASE_URL format validated")

if __name__ == "__main__":
    validate_environment()
    
    # Import and run the main application
    import uvicorn
    from main import app
    
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting TimeBud API on port {port}")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
