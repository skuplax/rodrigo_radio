# Breakdown Metadata Column Migration

## Current State

The `event_logs` table has a `metadata` JSONB column containing:
- **Logging metadata** (140,104 rows): `logger`, `module`, `function`, `line`, `message`, `pathname`, `exc_info`
- **Event metadata** (4,701 rows): `source_id`, `source_label` (already exist as columns)
- **Error tracking** (3,857 rows): `attempt`, `error`

Total: 164,458 rows, 142,744 with metadata.

**Note:** The `message` field in metadata currently contains formatted log messages with timestamp and log level prefixes (e.g., "2025-12-03 00:31:31.306 - INFO - Volume changed to 92%"). Since we already have `log_level` and `timestamp` columns, we'll extract just the actual message content.

**Issue:** `timestamp_local` is currently showing +00 (UTC) instead of +08 (Asia/Manila). This needs to be fixed in both existing data and future writes.

## Migration Strategy

### Step 1: Add New Columns

Add columns for all metadata fields that don't already exist:

```sql
ALTER TABLE event_logs
  ADD COLUMN logger TEXT,
  ADD COLUMN module TEXT,
  ADD COLUMN function_name TEXT,  -- 'function' is a reserved word
  ADD COLUMN line_number INTEGER,
  ADD COLUMN message TEXT,        -- Just the message content, no timestamp/log_level prefix
  ADD COLUMN pathname TEXT,
  ADD COLUMN exc_info TEXT,
  ADD COLUMN attempt INTEGER,
  ADD COLUMN error_message TEXT;  -- 'error' might conflict
```

**Note:** `source_id` and `source_label` already exist as columns, so we'll backfill them from metadata if they're NULL.

### Step 2: Fix timestamp_local Timezone

Fix existing `timestamp_local` values to use Asia/Manila timezone (+08) instead of UTC:

```sql
-- Convert timestamp_local from UTC to Asia/Manila timezone
UPDATE event_logs
SET timestamp_local = timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Manila'
WHERE timestamp_local IS NOT NULL;
```

### Step 3: Data Migration for Metadata Breakdown

Extract data from the JSONB metadata column and populate the new columns. For the `message` field, we'll extract it as-is (the application code will be updated to not include timestamp/log_level in future logs):

```sql
-- Extract all metadata fields using JSONB operators
UPDATE event_logs
SET
  logger = metadata->>'logger',
  module = metadata->>'module',
  function_name = metadata->>'function',
  line_number = CASE 
    WHEN metadata->>'line' IS NOT NULL 
    THEN (metadata->>'line')::integer 
    ELSE NULL 
  END,
  message = metadata->>'message',  -- Extract as-is (contains timestamp/log_level in existing data)
  pathname = metadata->>'pathname',
  exc_info = metadata->>'exc_info',
  attempt = CASE 
    WHEN metadata->>'attempt' IS NOT NULL 
    THEN (metadata->>'attempt')::integer 
    ELSE NULL 
  END,
  error_message = metadata->>'error',
  source_id = COALESCE(source_id, metadata->>'source_id'),
  source_label = COALESCE(source_label, metadata->>'source_label')
WHERE metadata IS NOT NULL;
```

**Optional:** If we want to clean existing messages to remove timestamp/log_level prefixes, we could use a regex, but it's safer to just extract as-is and let the application code handle clean messages going forward.

### Step 4: Update Application Code

Update code that writes to `event_logs` to use the new columns instead of metadata, ensure `message` contains only the message content (no timestamp/log_level), and fix timezone handling for `timestamp_local`:

**Files to update:**

1. **[core/supabase_log_handler.py](core/supabase_log_handler.py)** (lines 204-211):
   - Fix timezone: Change `local_timestamp = utc_timestamp.astimezone()` to explicitly use Asia/Manila timezone: `local_timestamp = utc_timestamp.astimezone(timezone(timedelta(hours=8)))` or use `zoneinfo.ZoneInfo('Asia/Manila')`
   - Remove `metadata` JSON construction (lines 216-224)
   - Add individual fields: `logger`, `module`, `function_name`, `line_number`, `message` (just the message content, not formatted with timestamp/log_level), `pathname`, `exc_info`
   - Extract clean message from `record.getMessage()` instead of the formatted message

2. **[core/playback_history.py](core/playback_history.py)** (lines 166-180):
   - Fix timezone: Change `local_dt = utc_dt.astimezone()` to explicitly use Asia/Manila timezone in all three places (lines 169, 176, 180)
   - Update `log()` method to accept individual parameters instead of `metadata` string (line 195)
   - Add parameters: `logger`, `module`, `function_name`, `line_number`, `message`, `pathname`, `exc_info`, `attempt`, `error_message`
   - Remove `metadata` parameter

3. **Any other code** that writes to `event_logs`:
   - Search for `metadata` usage and update accordingly

### Step 5: Remove Metadata Column

After verifying data migration and updating code:

```sql
ALTER TABLE event_logs DROP COLUMN metadata;
```

## Migration Execution Order

1. **Create migration**: `fix_timestamp_local_timezone`
   - Fix existing `timestamp_local` values to use Asia/Manila timezone (+08)

2. **Create migration**: `breakdown_metadata_column`
   - Add all new columns
   - Migrate data from metadata JSONB to new columns
   - Keep metadata column temporarily

3. **Update application code** to use new columns and fix timezone
   - Fix `timestamp_local` timezone handling to use Asia/Manila (+08)
   - Ensure `message` field contains only message content (no timestamp/log_level prefix)
   - Test thoroughly
   - Verify new logs are written correctly with correct timezone

4. **Create migration**: `remove_metadata_column`
   - Drop the metadata column
   - Only after confirming all code is updated

## Data Types

- `logger`: TEXT (nullable)
- `module`: TEXT (nullable)
- `function_name`: TEXT (nullable)
- `line_number`: INTEGER (nullable)
- `message`: TEXT (nullable) - **Just the message content, no timestamp/log_level prefix**
- `pathname`: TEXT (nullable)
- `exc_info`: TEXT (nullable)
- `attempt`: INTEGER (nullable)
- `error_message`: TEXT (nullable)

## Notes

- `source_id` and `source_label` already exist as columns - we'll backfill from metadata if needed
- The migration handles NULL values gracefully
- All new columns are nullable to handle cases where metadata doesn't contain those fields
- Column names avoid reserved words: `function` → `function_name`, `error` → `error_message`
- **Important:** The `message` column should contain only the actual message content. Since `log_level` and `timestamp`/`timestamp_local` are already separate columns, we don't need to duplicate that information in the message field.
- **Timezone Fix:** `timestamp_local` should use Asia/Manila timezone (+08). The code currently uses `astimezone()` without arguments, which defaults to system timezone (often UTC in containers). We'll explicitly use `Asia/Manila` timezone using `zoneinfo.ZoneInfo('Asia/Manila')` or `timezone(timedelta(hours=8))`.

