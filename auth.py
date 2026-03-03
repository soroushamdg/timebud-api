import os
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import urllib.request
import ssl
import certifi

security = HTTPBearer()

# Cache for JWKS client
_jwks_client: Optional[PyJWKClient] = None

async def init_jwks_client():
    """Initialize JWKS client on startup."""
    global _jwks_client
    jwks_url = os.getenv("CLERK_JWKS_URL")
    if not jwks_url:
        raise ValueError("CLERK_JWKS_URL environment variable is required")
    
    # Set up SSL context with certifi certificates for macOS
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    
    # Configure urllib to use our SSL context globally
    handler = urllib.request.HTTPSHandler(context=ssl_context)
    opener = urllib.request.build_opener(handler)
    urllib.request.install_opener(opener)
    
    # Initialize PyJWKClient - it will now use our SSL context
    _jwks_client = PyJWKClient(jwks_url, lifespan=60)
    
    print(f"Initialized JWKS client from {jwks_url} with SSL context")

def get_jwks_client() -> PyJWKClient:
    """Get the initialized JWKS client."""
    if _jwks_client is None:
        raise RuntimeError("JWKS client not initialized. Call init_jwks_client() first.")
    return _jwks_client

async def verify_clerk_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify Clerk JWT and extract user information."""
    token = credentials.credentials
    
    try:
        # Get JWKS client
        jwks_client = get_jwks_client()
        
        # Get the signing key from JWT
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify the JWT
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={
                "verify_aud": False  # Clerk doesn't always set audience
            },
            leeway=300  # Allow 5 minutes clock skew
        )
        
        # Extract clerk_user_id from the token
        clerk_user_id = payload.get("sub")
        if not clerk_user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        # Return the full payload with clerk_user_id highlighted
        return {
            "clerk_user_id": clerk_user_id,
            "email": payload.get("email"),
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
            **payload
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}"
        )

# Dependency to get current user from JWT
async def get_current_user(token_payload: Dict[str, Any] = Depends(verify_clerk_jwt)) -> Dict[str, Any]:
    """Get current user from verified JWT token."""
    return token_payload
