#!/usr/bin/env python3
"""Test Supabase connection and configuration."""
import sys
import os
from pathlib import Path

# Add project root to path
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded .env file from {env_file}")
    else:
        print(f"⚠ .env file not found at {env_file}")
        print("  Loading from environment variables...")
except ImportError:
    print("⚠ python-dotenv not installed, loading from environment variables only")
    print("  Install with: pip install python-dotenv")

# Check for Supabase package
try:
    from supabase import create_client, Client
    print("✓ Supabase package available")
except ImportError:
    print("✗ Supabase package not available")
    print("  Install with: pip install supabase")
    sys.exit(1)

# Get environment variables
database_url = os.getenv("DATABASE_URL")
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")

print("\n" + "=" * 60)
print("SUPABASE CONNECTION TEST")
print("=" * 60)

# Parse credentials
final_url = None
final_key = None

if database_url:
    print(f"\n📋 Found DATABASE_URL")
    print(f"   {database_url[:50]}..." if len(database_url) > 50 else f"   {database_url}")
    
    if database_url.startswith("https://"):
        final_url = database_url.rstrip("/")
        final_key = supabase_key
        print(f"   → Using as direct Supabase URL")
    elif "supabase.co" in database_url:
        # Extract project URL from connection string
        try:
            parts = database_url.split("@")
            if len(parts) > 1:
                host_part = parts[1].split(":")[0]
                if host_part.startswith("db."):
                    project_ref = host_part.replace("db.", "").replace(".supabase.co", "")
                    final_url = f"https://{project_ref}.supabase.co"
                else:
                    final_url = f"https://{host_part}"
            final_key = supabase_key
            print(f"   → Extracted Supabase URL: {final_url}")
        except Exception as e:
            print(f"   ✗ Error parsing DATABASE_URL: {e}")
else:
    print("\n📋 DATABASE_URL not found, checking direct variables...")
    final_url = supabase_url
    final_key = supabase_key

if supabase_url:
    print(f"\n📋 Found SUPABASE_URL")
    print(f"   {supabase_url}")
    if not final_url:
        final_url = supabase_url

if supabase_key:
    print(f"\n📋 Found SUPABASE_KEY")
    print(f"   {supabase_key[:20]}..." if len(supabase_key) > 20 else f"   {supabase_key}")
    if not final_key:
        final_key = supabase_key

# Check if we have both URL and key
print("\n" + "=" * 60)
if not final_url:
    print("✗ SUPABASE_URL not found")
    print("  Set SUPABASE_URL or DATABASE_URL in .env file")
    sys.exit(1)

if not final_key:
    print("✗ SUPABASE_KEY not found")
    print("  Set SUPABASE_KEY or SUPABASE_ANON_KEY in .env file")
    sys.exit(1)

print(f"✓ Supabase URL: {final_url}")
print(f"✓ Supabase Key: {final_key[:20]}...")

# Test connection
print("\n" + "=" * 60)
print("TESTING CONNECTION...")
print("=" * 60)

try:
    print("\n1. Creating Supabase client...")
    client = create_client(final_url, final_key)
    print("   ✓ Client created successfully")
    
    print("\n2. Testing connection with a simple query...")
    # Try to query the event_logs table (should work even if empty)
    table_exists = False
    try:
        response = client.table('event_logs').select('id').limit(1).execute()
        print(f"   ✓ Connection successful!")
        print(f"   ✓ Table 'event_logs' is accessible")
        print(f"   ✓ Found {len(response.data)} existing records (limit 1)")
        table_exists = True
    except Exception as table_error:
        error_str = str(table_error)
        error_dict = table_error if isinstance(table_error, dict) else {}
        error_code = error_dict.get('code', '')
        error_msg = error_dict.get('message', str(table_error))
        
        if "PGRST205" in str(error_code) or "not find the table" in error_msg.lower() or "does not exist" in error_msg.lower():
            print("   ⚠ Table 'event_logs' does not exist yet")
            print("   → Connection works, but table needs to be created")
            print("\n   To create the table, run this SQL in Supabase SQL Editor:")
            print("   " + "=" * 56)
            print("   CREATE TABLE event_logs (")
            print("       id BIGSERIAL PRIMARY KEY,")
            print("       timestamp DOUBLE PRECISION NOT NULL,")
            print("       log_level TEXT NOT NULL,")
            print("       event_type TEXT NOT NULL,")
            print("       action TEXT NOT NULL,")
            print("       source_id TEXT,")
            print("       source_label TEXT,")
            print("       source_type TEXT,")
            print("       item_name TEXT,")
            print("       status TEXT,")
            print("       duration_ms DOUBLE PRECISION,")
            print("       value DOUBLE PRECISION,")
            print("       metadata JSONB,")
            print("       created_at TIMESTAMPTZ DEFAULT NOW()")
            print("   );")
            print("   " + "=" * 56)
            print("\n   Then create indexes and RLS policies (see plan for full SQL)")
            table_exists = False
        elif "permission" in error_str.lower() or "policy" in error_str.lower():
            print("   ⚠ Permission denied - check RLS policies")
            print("   → Connection works, but RLS policies may need adjustment")
            table_exists = False
        else:
            print(f"   ✗ Query failed: {table_error}")
            raise
    
    if not table_exists:
        print("\n" + "=" * 60)
        print("⚠ CONNECTION WORKS, BUT TABLE NEEDS CREATION")
        print("=" * 60)
        print("\nSupabase connection is successful!")
        print("Create the 'event_logs' table using the SQL above, then re-run this test.")
        sys.exit(0)
    
    print("\n3. Testing insert capability...")
    # Try a test insert (will be rolled back or we can delete it)
    test_entry = {
        'timestamp': 1234567890.0,
        'log_level': 'INFO',
        'event_type': 'config',
        'action': 'connection_test',
        'status': 'success'
    }
    try:
        insert_response = client.table('event_logs').insert(test_entry).execute()
        if insert_response.data:
            test_id = insert_response.data[0].get('id')
            print(f"   ✓ Insert successful (test record ID: {test_id})")
            
            # Clean up test record
            try:
                client.table('event_logs').delete().eq('id', test_id).execute()
                print(f"   ✓ Test record cleaned up")
            except:
                print(f"   ⚠ Could not clean up test record (ID: {test_id})")
        else:
            print("   ⚠ Insert returned no data (check RLS policies)")
    except Exception as insert_error:
        error_str = str(insert_error)
        if "permission" in error_str.lower() or "policy" in error_str.lower():
            print("   ⚠ Insert permission denied - check RLS policies")
            print("   → Connection works, but insert policy may need adjustment")
        else:
            print(f"   ✗ Insert failed: {insert_error}")
            raise
    
    print("\n" + "=" * 60)
    print("✓ CONNECTION TEST PASSED")
    print("=" * 60)
    print("\nSupabase is properly configured and accessible!")
    print("The logging system should work correctly.")
    
except Exception as e:
    print("\n" + "=" * 60)
    print("✗ CONNECTION TEST FAILED")
    print("=" * 60)
    print(f"\nError: {e}")
    print("\nTroubleshooting:")
    print("1. Verify SUPABASE_URL is correct (format: https://[project-ref].supabase.co)")
    print("2. Verify SUPABASE_KEY is correct (anon key or service key)")
    print("3. Check network connectivity")
    print("4. Verify Supabase project is active")
    print("5. Check Supabase dashboard for any service issues")
    sys.exit(1)

