# Improved Logging System Plan with Timestamp Migration

## Current Issues Identified

From analyzing the Supabase logs, we have:

- **145,752 total log entries** with many redundant/unnecessary logs:
  - 15,373 logs for `root.increment` (rotary encoder volume changes - too verbose)
  - 14,631 logs for `volume_set` (every volume change)
  - 14,272 logs for `httpx._send_single_request` (HTTP requests - not useful)
  - 37 logs about logging to Supabase (meta-logging - redundant)
  - Many INFO logs for normal successful operations
- **Timestamp column is float (double precision)** - needs to be datetime with local time

## Solution Overview

1. **Create centralized logger** (`utils/logger.py`) with:

   - Smart filtering to prevent redundant logs
   - Volume change throttling (only log significant changes)
   - Event type categorization (user_input, system_error, system_state, etc.)
   - Integration with existing Supabase handler
   - Uses datetime objects instead of float timestamps

2. **Migrate timestamp column** from float to datetime:

   - **Keep `timestamp` column** - convert from float to timestamptz (UTC)
   - **Add `timestamp_local` column** (timestamptz) for local time
   - Migrate existing float timestamps to both columns (UTC and local time)
   - Data migration converts all existing records

3. **Remove/reduce unnecessary logs:**

   - Remove meta-logging (logs about logging)
   - Reduce volume logging to significant changes only (every 5% or mute/unmute)
   - Filter out HTTP request logs
   - Remove DEBUG logs from production
   - Reduce INFO logs for routine successful operations

4. **Keep important logs:**

   - All ERROR and CRITICAL logs
   - User interactions (button presses, source cycling)
   - System state changes (playback start/stop, source changes)
   - Warnings about retries and connection issues
   - Significant volume changes (every 5% or mute/unmute events)

## Implementation Steps

### Step 1: Create Database Migration for Timestamp Column

**Migration: `convert_timestamp_to_datetime`**

The migration will:

1. Add `timestamp_local` column (timestamptz)
2. Convert existing `timestamp` column from float to timestamptz (UTC)
3. Migrate all existing data to populate both columns
```sql
-- Step 1: Add timestamp_local column for local time
ALTER TABLE event_logs 
  ADD COLUMN timestamp_local TIMESTAMPTZ;

-- Step 2: Convert existing timestamp column from float to timestamptz (UTC)
-- First, create a temporary column
ALTER TABLE event_logs 
  ADD COLUMN timestamp_utc_temp TIMESTAMPTZ;

-- Step 3: Migrate existing float timestamps to UTC datetime
UPDATE event_logs 
SET timestamp_utc_temp = to_timestamp(timestamp) AT TIME ZONE 'UTC'
WHERE timestamp IS NOT NULL;

-- Step 4: Migrate to local time (infer from UTC)
-- Note: Adjust timezone based on system timezone (e.g., 'America/New_York', 'Europe/London', etc.)
-- For now, using system's local timezone - may need to be configurable
UPDATE event_logs 
SET timestamp_local = timestamp_utc_temp AT TIME ZONE 'UTC' AT TIME ZONE current_setting('timezone')
WHERE timestamp_utc_temp IS NOT NULL;

-- Step 5: Drop old float column and rename temp column
ALTER TABLE event_logs 
  DROP COLUMN timestamp;

ALTER TABLE event_logs 
  RENAME COLUMN timestamp_utc_temp TO timestamp;

-- Step 6: Make columns NOT NULL after migration
ALTER TABLE event_logs 
  ALTER COLUMN timestamp SET NOT NULL,
  ALTER COLUMN timestamp_local SET NOT NULL;
```


**Alternative approach (safer, preserves old column temporarily):**

```sql
-- Step 1: Add new columns
ALTER TABLE event_logs 
  ADD COLUMN timestamp_utc_new TIMESTAMPTZ,
  ADD COLUMN timestamp_local TIMESTAMPTZ;

-- Step 2: Migrate existing data
UPDATE event_logs 
SET 
  timestamp_utc_new = to_timestamp(timestamp) AT TIME ZONE 'UTC',
  timestamp_local = (to_timestamp(timestamp) AT TIME ZONE 'UTC') AT TIME ZONE current_setting('timezone')
WHERE timestamp IS NOT NULL;

-- Step 3: After code is updated and tested, drop old column
-- ALTER TABLE event_logs DROP COLUMN timestamp;
-- ALTER TABLE event_logs RENAME COLUMN timestamp_utc_new TO timestamp;
```

**Note:** The timezone for `timestamp_local` should match the system's timezone. We'll use Python's `datetime.now().astimezone()` to get the local timezone automatically.

### Step 2: Create Centralized Logger (`utils/logger.py`)

Create a new logger module with:

- `get_logger(name)` function that returns configured logger
- Volume change throttling helper
- Smart filtering for redundant logs
- Event type helpers (log_user_action, log_error, log_state_change)
- **Uses datetime objects instead of float timestamps**

Key features:

- Filters out logs containing "supabase" and "log" in action/message (meta-logging)
- Volume change throttling: only log if change is >= 5% or mute/unmute
- Filters out httpx internal logs
- Categorizes logs by event type automatically
- Converts timestamps to datetime objects (UTC and local time)

### Step 3: Update `core/supabase_log_handler.py`

- Remove meta-logging (lines 61, 73, 75, 225)
- Add filtering to prevent logging about logging operations
- Update emit() to skip redundant logs before buffering
- **Change timestamp from `record.created` (float) to `datetime.fromtimestamp(record.created, tz=timezone.utc)` for UTC**
- **Calculate local time using `datetime.fromtimestamp(record.created).astimezone()`**
- **Send both `timestamp` (UTC) and `timestamp_local` to Supabase**

### Step 4: Update `core/playback_history.py`

- **Change `log()` method signature: `timestamp: float` → accept `datetime` objects**
- **Update all `time.time()` calls to use `datetime.now(timezone.utc)` for UTC and `.astimezone()` for local**
- Update `_sync_to_supabase()` to send both `timestamp` (UTC) and `timestamp_local`
- Remove debug logs about syncing (line 219)

### Step 5: Update Volume Logging

**Files to update:**

- `hardware/rotary_encoder.py`: Add volume change throttling
- `core/player_controller.py`: Update `_on_volume_change()` to use throttled logging

Changes:

- Track last logged volume percentage
- Only log if change >= 5% or mute/unmute state changed
- Use new logger from utils/logger.py
- Use datetime objects for timestamps

### Step 6: Remove Redundant Logs

**Files to clean up:**

- `main.py`: Remove line 55 (logging about Supabase initialization)
- `core/supabase_log_handler.py`: Remove all meta-logging statements
- `core/playback_history.py`: Remove debug logs about syncing (line 219)
- Filter out httpx logs in supabase_log_handler

### Step 7: Update Logging Throughout Codebase

Replace standard logging with new logger where appropriate:

- `hardware/buttons.py`: Keep user interaction logs, remove debug logs
- `core/player_controller.py`: Keep errors and state changes, reduce routine INFO logs
- `backends/spotify_backend.py`: Keep errors, reduce routine operation logs
- `backends/youtube_backend.py`: Keep errors, reduce routine operation logs

### Step 8: Update Existing Code to Use New Logger

Replace `logging.getLogger(__name__)` with `from utils.logger import get_logger; logger = get_logger(__name__)` in:

- `main.py`
- `core/player_controller.py`
- `hardware/buttons.py`
- `hardware/rotary_encoder.py`
- `core/sources.py`
- Backend files (as needed)

### Step 9: Update Query Code

Update any code that queries event_logs to use `timestamp_local` for display and `timestamp` for UTC:

- `core/playback_history.py`: Update queries to use `timestamp_local` for display
- `cli.py`: Update dashboard queries to use `timestamp_local` for display

## Log Categories to Keep

1. **User Interactions** (event_type: `user_input`):

   - Button presses (play_pause, next, previous, cycle_source)
   - Rotary encoder rotations (significant volume changes only)
   - Mute/unmute toggles

2. **System Errors** (event_type: `system`, log_level: `ERROR`/`CRITICAL`):

   - Spotify API errors
   - Backend failures
   - Network connection failures
   - Hardware initialization errors

3. **System State Changes** (event_type: `system`, log_level: `INFO`):

   - Playback start/stop
   - Source changes
   - Backend switches

4. **Warnings** (log_level: `WARNING`):

   - Retry attempts
   - Connection issues
   - Fallback operations

## Log Categories to Remove/Reduce

1. **Meta-logging**: All logs about logging operations
2. **Volume changes**: Only significant changes (>= 5% or mute/unmute)
3. **HTTP requests**: Internal httpx logs
4. **Routine operations**: Successful operations that happen frequently and work normally
5. **DEBUG logs**: Remove from production (keep for development)

## Database Schema Changes

**Before:**

- `timestamp` (double precision) - Unix timestamp as float

**After:**

- `timestamp` (timestamptz) - UTC datetime (converted from float)
- `timestamp_local` (timestamptz) - Local timezone datetime (new column)

## Database Impact

The new logging system will significantly reduce log volume:

- Current: ~145k logs
- Expected: ~10-20k logs (focusing on important events)
- Reduction: ~85-90% fewer logs

This will make monitoring much easier and reduce Supabase storage/query costs.

## Migration Strategy

1. Create migration to:

   - Add `timestamp_local` column
   - Convert `timestamp` from float to timestamptz (UTC)
   - Migrate all existing data to populate both columns

2. Update code to use datetime objects and send both UTC and local timestamps
3. Test thoroughly
4. Optional: Clean up any temporary columns if used