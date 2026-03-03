#!/usr/bin/env python3
"""Check and fix database schema"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from database import DATABASE_URL

async def check_and_fix_schema():
    """Check current schema and add missing columns"""
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # Check if users table exists
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            )
        """))
        users_exists = result.scalar()
        
        if not users_exists:
            print("Creating users table...")
            await conn.execute(text("""
                CREATE TABLE users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    clerk_id VARCHAR UNIQUE NOT NULL,
                    email VARCHAR NOT NULL,
                    first_name VARCHAR,
                    last_name VARCHAR,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """))
        else:
            print("Users table exists, checking columns...")
            
            # Check existing columns
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users'
            """))
            existing_columns = {row[0] for row in result.fetchall()}
            
            print(f"Existing columns: {existing_columns}")
            
            # Add missing columns
            if 'clerk_id' not in existing_columns:
                print("Adding clerk_id column...")
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN clerk_id VARCHAR UNIQUE NOT NULL
                """))
            
            if 'email' not in existing_columns:
                print("Adding email column...")
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN email VARCHAR NOT NULL
                """))
            
            if 'first_name' not in existing_columns:
                print("Adding first_name column...")
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN first_name VARCHAR
                """))
            
            if 'last_name' not in existing_columns:
                print("Adding last_name column...")
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN last_name VARCHAR
                """))
            
            if 'created_at' not in existing_columns:
                print("Adding created_at column...")
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                """))
            
            if 'updated_at' not in existing_columns:
                print("Adding updated_at column...")
                await conn.execute(text("""
                    ALTER TABLE users ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE
                """))
        
        print("Schema check complete!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_and_fix_schema())
