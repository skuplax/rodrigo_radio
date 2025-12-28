#!/usr/bin/env python3
"""Clean up unnecessary log records from Supabase database.

This script removes routine INFO and DEBUG logs while keeping:
- All ERROR and WARNING logs
- All user input logs (button presses, encoder actions, etc.)
"""
import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    def load_dotenv(*args, **kwargs):
        pass

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Error: supabase package not installed. Install with: pip install supabase")
    sys.exit(1)


def load_supabase_config() -> tuple[Optional[str], Optional[str]]:
    """Load Supabase configuration from environment variables."""
    # Load .env file if available
    if DOTENV_AVAILABLE:
        env_file = PROJECT_ROOT / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            if database_url.startswith("https://"):
                supabase_url = database_url.rstrip("/")
                supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
            elif "supabase.co" in database_url:
                parts = database_url.split("@")
                if len(parts) > 1:
                    host_part = parts[1].split(":")[0]
                    if host_part.startswith("db."):
                        project_ref = host_part.replace("db.", "").replace(".supabase.co", "")
                        supabase_url = f"https://{project_ref}.supabase.co"
                    else:
                        supabase_url = f"https://{host_part}"
                else:
                    supabase_url = None
                supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
            else:
                supabase_url = None
                supabase_key = None
        except Exception:
            supabase_url = None
            supabase_key = None
    else:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    return supabase_url, supabase_key


def get_log_statistics(client: Client) -> dict:
    """Get statistics about logs in the database."""
    print("Fetching log statistics...")
    
    stats = {
        'total': 0,
        'by_level': {},
        'by_action': {}
    }
    
    # Use a more efficient approach - sample recent logs and estimate
    # Or use direct SQL if available, but for now let's use pagination
    
    print("  - Counting logs by level (this may take a moment)...")
    
    # Get counts by log level using limit/offset pagination for efficiency
    for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        try:
            # Try to get count efficiently
            result = client.table('event_logs').select('id', count='exact').eq('log_level', level).limit(1).execute()
            count = result.count if hasattr(result, 'count') and result.count is not None else 0
            
            # If count is None, try pagination approach
            if count == 0 or result.count is None:
                # Use a sampling approach - get first 1000 and estimate
                sample = client.table('event_logs').select('id').eq('log_level', level).limit(1000).execute()
                if len(sample.data) == 1000:
                    # Large dataset, estimate based on sample
                    print(f"    {level}: Large dataset detected, using sampling...")
                    count = "1000+"  # Indicate it's at least 1000
                else:
                    count = len(sample.data)
            
            stats['by_level'][level] = count
        except Exception as e:
            print(f"    Error counting {level} logs: {e}")
            stats['by_level'][level] = 0
    
    # Calculate total
    total = 0
    for count in stats['by_level'].values():
        if isinstance(count, int):
            total += count
        else:
            total += 1000  # Estimate for large datasets
    stats['total'] = total
    
    # Get top actions (sample from INFO level only)
    print("  - Analyzing INFO-level logs (sampling)...")
    try:
        # Sample first 5000 INFO logs to get action distribution
        info_result = client.table('event_logs').select('action').eq('log_level', 'INFO').limit(5000).execute()
        
        action_counts = {}
        for entry in info_result.data:
            action = entry.get('action', 'unknown')
            action_counts[action] = action_counts.get(action, 0) + 1
        
        # Sort by count
        stats['by_action'] = dict(sorted(action_counts.items(), key=lambda x: x[1], reverse=True)[:20])
    except Exception as e:
        print(f"    Error analyzing INFO logs: {e}")
        stats['by_action'] = {}
    
    return stats


def identify_logs_to_delete(client: Client, dry_run: bool = True) -> dict:
    """Identify logs that should be deleted."""
    print("\nIdentifying logs to delete...")
    
    deletion_stats = {
        'total_to_delete': 0,
        'by_reason': {},
        'to_keep': {
            'errors': 0,
            'warnings': 0,
            'user_input': 0
        }
    }
    
    # Count DEBUG logs (use sampling if large)
    print("  - Finding DEBUG logs...")
    try:
        debug_sample = client.table('event_logs').select('id', count='exact').eq('log_level', 'DEBUG').limit(1).execute()
        debug_count = debug_sample.count if hasattr(debug_sample, 'count') and debug_sample.count is not None else 0
        if debug_count == 0:
            debug_count = len(debug_sample.data) if debug_sample.data else 0
        deletion_stats['by_reason']['DEBUG logs'] = debug_count if isinstance(debug_count, int) else "many"
        if isinstance(debug_count, int):
            deletion_stats['total_to_delete'] += debug_count
    except Exception as e:
        print(f"    Error counting DEBUG logs: {e}")
        deletion_stats['by_reason']['DEBUG logs'] = "unknown"
    
    # Count volume increment warnings
    print("  - Finding volume increment warnings...")
    try:
        volume_warning_sample = client.table('event_logs').select('id', count='exact').eq('log_level', 'WARNING').ilike('action', '%increment%').limit(1).execute()
        volume_warning_count = volume_warning_sample.count if hasattr(volume_warning_sample, 'count') and volume_warning_sample.count is not None else 0
        if volume_warning_count == 0:
            volume_warning_count = len(volume_warning_sample.data) if volume_warning_sample.data else 0
        deletion_stats['by_reason']['Volume increment warnings'] = volume_warning_count if isinstance(volume_warning_count, int) else "many"
        if isinstance(volume_warning_count, int):
            deletion_stats['total_to_delete'] += volume_warning_count
    except Exception as e:
        print(f"    Error counting volume warnings: {e}")
        deletion_stats['by_reason']['Volume increment warnings'] = "unknown"
    
    # Estimate routine INFO logs (sample approach)
    print("  - Estimating routine INFO logs...")
    try:
        # Sample INFO logs to estimate
        info_sample = client.table('event_logs').select('action,event_type').eq('log_level', 'INFO').limit(1000).execute()
        
        user_input_actions = ['button', 'encoder_switch', 'mute_toggle', 'user_input']
        routine_count = 0
        user_input_count = 0
        
        for entry in info_sample.data:
            action = entry.get('action', '').lower()
            event_type = entry.get('event_type', '').lower()
            
            is_user_input = (
                event_type == 'user_input' or
                any(ui in action for ui in user_input_actions)
            )
            
            if is_user_input:
                user_input_count += 1
            else:
                routine_count += 1
        
        # Estimate total based on sample ratio
        if len(info_sample.data) > 0:
            routine_ratio = routine_count / len(info_sample.data)
            # Get total INFO count estimate
            info_total_sample = client.table('event_logs').select('id', count='exact').eq('log_level', 'INFO').limit(1).execute()
            info_total = info_total_sample.count if hasattr(info_total_sample, 'count') and info_total_sample.count is not None else 0
            if info_total == 0:
                info_total = len(info_total_sample.data) if info_total_sample.data else 0
            
            if isinstance(info_total, int) and info_total > 0:
                estimated_routine = int(info_total * routine_ratio)
                deletion_stats['by_reason']['Routine INFO logs'] = estimated_routine
                deletion_stats['total_to_delete'] += estimated_routine
                deletion_stats['to_keep']['user_input'] = int(info_total * (user_input_count / len(info_sample.data)))
            else:
                deletion_stats['by_reason']['Routine INFO logs'] = "many (estimated)"
        else:
            deletion_stats['by_reason']['Routine INFO logs'] = 0
    except Exception as e:
        print(f"    Error estimating INFO logs: {e}")
        deletion_stats['by_reason']['Routine INFO logs'] = "unknown"
    
    # Count what we're keeping (ERROR and WARNING)
    print("  - Counting logs to keep...")
    try:
        error_sample = client.table('event_logs').select('id', count='exact').eq('log_level', 'ERROR').limit(1).execute()
        deletion_stats['to_keep']['errors'] = error_sample.count if hasattr(error_sample, 'count') and error_sample.count is not None else 0
        if deletion_stats['to_keep']['errors'] == 0:
            deletion_stats['to_keep']['errors'] = len(error_sample.data) if error_sample.data else 0
    except Exception as e:
        print(f"    Error counting ERROR logs: {e}")
    
    try:
        warning_sample = client.table('event_logs').select('id', count='exact').eq('log_level', 'WARNING').limit(1).execute()
        warning_count = warning_sample.count if hasattr(warning_sample, 'count') and warning_sample.count is not None else 0
        if warning_count == 0:
            warning_count = len(warning_sample.data) if warning_sample.data else 0
        # Subtract volume increment warnings
        if isinstance(warning_count, int) and isinstance(deletion_stats['by_reason'].get('Volume increment warnings'), int):
            deletion_stats['to_keep']['warnings'] = warning_count - deletion_stats['by_reason']['Volume increment warnings']
        else:
            deletion_stats['to_keep']['warnings'] = warning_count if isinstance(warning_count, int) else "many"
    except Exception as e:
        print(f"    Error counting WARNING logs: {e}")
    
    return deletion_stats


def delete_logs(client: Client, dry_run: bool = True) -> dict:
    """Delete identified logs from the database."""
    print("\n" + "="*60)
    if dry_run:
        print("DRY RUN MODE - No logs will be deleted")
    else:
        print("DELETION MODE - Logs will be permanently deleted!")
    print("="*60)
    
    deletion_stats = identify_logs_to_delete(client, dry_run)
    
    print(f"\nDeletion Summary:")
    if isinstance(deletion_stats['total_to_delete'], int):
        print(f"  Total logs to delete: {deletion_stats['total_to_delete']:,}")
    else:
        print(f"  Total logs to delete: {deletion_stats['total_to_delete']} (estimated)")
    print(f"\n  Breakdown by reason:")
    for reason, count in deletion_stats['by_reason'].items():
        if isinstance(count, int):
            print(f"    - {reason}: {count:,}")
        else:
            print(f"    - {reason}: {count}")
    
    print(f"\n  Logs to keep:")
    errors = deletion_stats['to_keep']['errors']
    warnings = deletion_stats['to_keep']['warnings']
    user_input = deletion_stats['to_keep']['user_input']
    print(f"    - ERROR logs: {errors:,}" if isinstance(errors, int) else f"    - ERROR logs: {errors}")
    print(f"    - WARNING logs: {warnings:,}" if isinstance(warnings, int) else f"    - WARNING logs: {warnings}")
    print(f"    - User input logs: {user_input:,}" if isinstance(user_input, int) else f"    - User input logs: {user_input}")
    
    if dry_run:
        print("\n✓ Dry run complete. Use --execute to actually delete logs.")
        return deletion_stats
    
    # Confirm deletion
    print("\n" + "!"*60)
    print("WARNING: This will permanently delete logs from the database!")
    print("!"*60)
    response = input("\nType 'DELETE' to confirm: ")
    
    if response != 'DELETE':
        print("Deletion cancelled.")
        return deletion_stats
    
    print("\nDeleting logs...")
    
    deleted_counts = {}
    
    # Delete DEBUG logs
    print("  - Deleting DEBUG logs...")
    try:
        debug_result = client.table('event_logs').delete().eq('log_level', 'DEBUG').execute()
        deleted_counts['DEBUG'] = len(debug_result.data) if debug_result.data else 0
        print(f"    Deleted {deleted_counts['DEBUG']:,} DEBUG logs")
    except Exception as e:
        print(f"    Error deleting DEBUG logs: {e}")
        deleted_counts['DEBUG'] = 0
    
    # Delete volume increment warnings
    print("  - Deleting volume increment warnings...")
    try:
        volume_warning_result = client.table('event_logs').delete().eq('log_level', 'WARNING').ilike('action', '%increment%').execute()
        deleted_counts['volume_warnings'] = len(volume_warning_result.data) if volume_warning_result.data else 0
        print(f"    Deleted {deleted_counts['volume_warnings']:,} volume increment warnings")
    except Exception as e:
        print(f"    Error deleting volume warnings: {e}")
        deleted_counts['volume_warnings'] = 0
    
    # Delete routine INFO logs
    print("  - Deleting routine INFO logs...")
    
    # List of actions to delete (routine operations)
    routine_actions = [
        'volume_set', 'volume_change', '_on_volume_change', 'set_volume', 'adjust_volume',
        'httpx._send_single_request',
        'backends.spotify_backend.stop', 'backends.spotify_backend.play',
        'backends.youtube_backend.stop', 'backends.youtube_backend.play',
        'backends.spotify_backend._find_raspotify_device',
        'backends.spotify_backend._ensure_device', 'backends.spotify_backend._ensure_device_active',
        'backends.spotify_backend._start_monitoring', 'backends.spotify_backend._stop_monitoring',
        'backends.spotify_backend._start_raspotify_service', 'backends.spotify_backend._restart_raspotify_service',
        'backends.youtube_backend._get_video_list_from_rss', 'backends.youtube_backend._play_next_video',
        'core.player_controller._play_source_with_retry', 'core.player_controller._switch_source',
        'core.player_controller.monitor_state', 'hardware.buttons.wrapped_callback',
        'hardware.buttons._setup_buttons', 'connection_success', 'playback_start', 'source_change',
        'utils.sound_feedback.start', 'utils.sound_feedback._force_stop',
        'utils.announcements.announce_source', 'core.sources.cycle_source',
        'core.player_controller._on_cycle_source', 'core.player_controller._on_next',
        'core.player_controller._on_play_pause', 'root.increment'
    ]
    
    total_routine_deleted = 0
    
    # Delete by action (process one at a time to avoid timeouts)
    for action in routine_actions:
        try:
            # Delete in batches using limit to avoid timeout
            deleted_for_action = 0
            batch_size = 1000
            
            while True:
                # Get a batch of IDs to delete
                batch_query = client.table('event_logs').select('id').eq('log_level', 'INFO').eq('action', action).limit(batch_size)
                batch_result = batch_query.execute()
                
                if not batch_result.data or len(batch_result.data) == 0:
                    break
                
                # Delete this batch
                ids_to_delete = [entry['id'] for entry in batch_result.data]
                delete_result = client.table('event_logs').delete().in_('id', ids_to_delete).execute()
                deleted_for_action += len(ids_to_delete)
                
                if len(batch_result.data) < batch_size:
                    # Last batch
                    break
            
            if deleted_for_action > 0:
                total_routine_deleted += deleted_for_action
                print(f"    Deleted {deleted_for_action:,} logs for: {action}")
        except Exception as e:
            print(f"    Error deleting {action}: {e}")
    
    # Delete INFO logs with volume in action but not user input (process in batches)
    print("  - Deleting volume-related INFO logs (excluding user input)...")
    try:
        deleted_volume_count = 0
        batch_size = 1000
        
        while True:
            # Get a batch of volume-related INFO logs
            volume_query = client.table('event_logs').select('id,action,event_type').eq('log_level', 'INFO').ilike('action', '%volume%').limit(batch_size)
            volume_result = volume_query.execute()
            
            if not volume_result.data or len(volume_result.data) == 0:
                break
            
            volume_ids_to_delete = []
            for entry in volume_result.data:
                action = entry.get('action', '').lower()
                event_type = entry.get('event_type', '').lower()
                
                # Skip user input
                if event_type == 'user_input' or 'mute_toggle' in action or 'encoder_switch' in action or 'button' in action:
                    continue
                
                volume_ids_to_delete.append(entry['id'])
            
            # Delete this batch
            if volume_ids_to_delete:
                try:
                    client.table('event_logs').delete().in_('id', volume_ids_to_delete).execute()
                    deleted_volume_count += len(volume_ids_to_delete)
                except Exception as e:
                    print(f"    Error deleting volume batch: {e}")
            
            if len(volume_result.data) < batch_size:
                # Last batch
                break
        
        if deleted_volume_count > 0:
            print(f"    Deleted {deleted_volume_count:,} volume-related INFO logs")
            total_routine_deleted += deleted_volume_count
    except Exception as e:
        print(f"    Error deleting volume logs: {e}")
    
    # Delete remaining INFO logs that are not user input (process in batches)
    print("  - Deleting remaining routine INFO logs (not user input)...")
    try:
        deleted_routine_count = 0
        batch_size = 1000
        
        while True:
            # Get a batch of INFO logs
            all_info_query = client.table('event_logs').select('id,action,event_type').eq('log_level', 'INFO').limit(batch_size)
            all_info_result = all_info_query.execute()
            
            if not all_info_result.data or len(all_info_result.data) == 0:
                break
            
            routine_ids = []
            for entry in all_info_result.data:
                action = entry.get('action', '').lower()
                event_type = entry.get('event_type', '').lower()
                
                # Keep user input
                if event_type == 'user_input':
                    continue
                if any(ui in action for ui in ['button', 'encoder_switch', 'mute_toggle', 'user_input']):
                    continue
                
                # Skip if we already deleted it by action name
                if any(routine in action for routine in routine_actions):
                    continue
                
                routine_ids.append(entry['id'])
            
            # Delete this batch
            if routine_ids:
                try:
                    client.table('event_logs').delete().in_('id', routine_ids).execute()
                    deleted_routine_count += len(routine_ids)
                except Exception as e:
                    print(f"    Error deleting routine batch: {e}")
            
            if len(all_info_result.data) < batch_size:
                # Last batch
                break
        
        if deleted_routine_count > 0:
            print(f"    Deleted {deleted_routine_count:,} additional routine INFO logs")
            total_routine_deleted += deleted_routine_count
    except Exception as e:
        print(f"    Error deleting remaining routine logs: {e}")
    
    deleted_counts['routine_INFO'] = total_routine_deleted
    
    print(f"\n✓ Deletion complete!")
    print(f"  Total deleted: {sum(deleted_counts.values()):,}")
    
    return deletion_stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up unnecessary log records from Supabase')
    parser.add_argument('--execute', action='store_true', 
                       help='Actually delete logs (default is dry run)')
    parser.add_argument('--stats-only', action='store_true',
                       help='Only show statistics, do not delete')
    
    args = parser.parse_args()
    
    print("="*60)
    print("Supabase Log Cleanup Script")
    print("="*60)
    
    # Load configuration
    supabase_url, supabase_key = load_supabase_config()
    
    if not supabase_url or not supabase_key:
        print("\nError: Supabase configuration not found.")
        print("Please set SUPABASE_URL and SUPABASE_KEY environment variables,")
        print("or configure DATABASE_URL in your .env file.")
        sys.exit(1)
    
    print(f"\nConnecting to Supabase: {supabase_url}")
    
    try:
        client = create_client(supabase_url, supabase_key)
    except Exception as e:
        print(f"\nError connecting to Supabase: {e}")
        sys.exit(1)
    
    # Get statistics
    stats = get_log_statistics(client)
    
    print(f"\nCurrent Database Statistics:")
    if isinstance(stats['total'], int):
        print(f"  Total logs: {stats['total']:,}")
    else:
        print(f"  Total logs: {stats['total']} (estimated)")
    print(f"\n  By log level:")
    for level, count in stats['by_level'].items():
        if isinstance(count, int):
            print(f"    {level}: {count:,}")
        else:
            print(f"    {level}: {count} (large dataset)")
    
    if stats['by_action']:
        print(f"\n  Top INFO-level actions (will be removed if routine):")
        for action, count in list(stats['by_action'].items())[:10]:
            print(f"    {action}: {count:,}")
    
    if args.stats_only:
        return
    
    # Delete logs
    dry_run = not args.execute
    deletion_stats = delete_logs(client, dry_run=dry_run)
    
    # Show final statistics
    if not dry_run:
        print("\n" + "="*60)
        print("Final Statistics:")
        print("="*60)
        final_stats = get_log_statistics(client)
        print(f"  Remaining logs: {final_stats['total']:,}")
        print(f"\n  By log level:")
        for level, count in final_stats['by_level'].items():
            print(f"    {level}: {count:,}")


if __name__ == '__main__':
    main()



