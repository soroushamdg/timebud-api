#!/usr/bin/env python3
"""Debug JWT token and JWKS endpoint"""

import jwt
import json
import base64
import sys
import os

from dotenv import load_dotenv
from jwt import PyJWKClient
import urllib.request
import ssl
import certifi
from datetime import datetime
load_dotenv()
def decode_jwt_parts(token):
    """Decode JWT without verification to inspect its contents"""
    try:
        parts = token.split('.')
        
        # Decode header
        header_padding = 4 - len(parts[0]) % 4
        header = base64.urlsafe_b64decode(parts[0] + '=' * header_padding)
        
        # Decode payload
        payload_padding = 4 - len(parts[1]) % 4
        payload = base64.urlsafe_b64decode(parts[1] + '=' * payload_padding)
        
        return {
            'header': json.loads(header),
            'payload': json.loads(payload),
            'signature': parts[2]
        }
    except Exception as e:
        return f"Error decoding JWT: {e}"

def check_jwks_endpoint(jwks_url):
    """Fetch and display JWKS from endpoint"""
    try:
        # Set up SSL context
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        handler = urllib.request.HTTPSHandler(context=ssl_context)
        opener = urllib.request.build_opener(handler)
        urllib.request.install_opener(opener)
        
        # Fetch JWKS
        response = urllib.request.urlopen(jwks_url)
        jwks = json.loads(response.read())
        
        return jwks
    except Exception as e:
        return f"Error fetching JWKS: {e}"

def validate_token_with_jwks(token, jwks_url):
    """Try to validate token with JWKS"""
    try:
        # Set up SSL context
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        handler = urllib.request.HTTPSHandler(context=ssl_context)
        opener = urllib.request.build_opener(handler)
        urllib.request.install_opener(opener)
        
        # Create JWKS client
        jwks_client = PyJWKClient(jwks_url)
        
        # Get signing key
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )
        
        return {"status": "valid", "payload": payload}
    except Exception as e:
        return {"status": "invalid", "error": str(e)}

def main():
    # Get token from command line or environment
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        print("Usage: python debug_jwt.py <JWT_TOKEN>")
        print("Or set TEST_JWT_TOKEN environment variable")
        token = os.getenv('TEST_JWT_TOKEN')
        if not token:
            return
    print("token is : " + token)
    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]
    
    print("=== JWT Token Debug ===\n")
    
    # 1. Decode without verification
    decoded = decode_jwt_parts(token)
    print("1. Decoded JWT (without verification):")
    print(json.dumps(decoded, indent=2))
    
    if isinstance(decoded, dict):
        print(f"\nKey ID (kid) in header: {decoded['header'].get('kid', 'NOT FOUND')}")
        print(f"Algorithm: {decoded['header'].get('alg', 'NOT FOUND')}")
        print(f"Token Type: {decoded['header'].get('typ', 'NOT FOUND')}")
        
        # Check expiration
        exp = decoded['payload'].get('exp')
        if exp:
            exp_date = datetime.fromtimestamp(exp)
            print(f"\nExpiration: {exp_date}")
            print(f"Expired: {datetime.now() > exp_date}")
    
    # 2. Check JWKS endpoint
    jwks_url = os.getenv('CLERK_JWKS_URL')
    if jwks_url:
        print(f"\n\n2. Checking JWKS endpoint: {jwks_url}")
        jwks = check_jwks_endpoint(jwks_url)
        print("JWKS Response:")
        print(json.dumps(jwks, indent=2))
        
        if isinstance(jwks, dict) and 'keys' in jwks:
            print(f"\nNumber of keys: {len(jwks['keys'])}")
            print("Key IDs available:")
            for key in jwks['keys']:
                print(f"  - {key.get('kid', 'NO KID')}")
        
        # 3. Try to validate
        print("\n\n3. Attempting validation:")
        result = validate_token_with_jwks(token, jwks_url)
        print(json.dumps(result, indent=2))
    else:
        print("\n\nCLERK_JWKS_URL not found in environment")

if __name__ == "__main__":
    main()
