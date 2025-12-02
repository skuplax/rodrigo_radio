#!/usr/bin/env python3
"""CLI tool for monitoring player status and history."""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
from core.sources import SourceManager, DEFAULT_STATE_FILE
from core.playback_history import PlaybackHistory

# Try to import player controller for live status
try:
    from core.player_controller import PlayerController
    CONTROLLER_AVAILABLE = True
except ImportError:
    CONTROLLER_AVAILABLE = False


def format_timestamp(iso_string: str) -> str:
    """Format ISO timestamp to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return iso_string


def show_status():
    """Show current player status."""
    print("=" * 60)
    print("MUSIC PLAYER STATUS")
    print("=" * 60)
    
    # Load state
    state_file = DEFAULT_STATE_FILE
    if not state_file.exists():
        print("\nNo state file found. Player may not be running.")
        return
    
    try:
        with open(state_file, 'r') as f:
            state = json.load(f)
        
        source_index = state.get('current_source_index', 0)
        last_updated = state.get('last_updated', 'Unknown')
        
        print(f"\nCurrent Source Index: {source_index}")
        print(f"Last Updated: {format_timestamp(last_updated)}")
        
    except Exception as e:
        print(f"\nError reading state: {e}")
    
    # Try to get live status from controller
    if CONTROLLER_AVAILABLE:
        try:
            # This would require the controller to be running and accessible
            # For now, we'll just show what we can from files
            pass
        except Exception:
            pass
    
    # Load sources to show current source name
    try:
        source_manager = SourceManager()
        current_source = source_manager.get_current_source()
        
        if current_source:
            print(f"\nCurrent Source: {current_source.get('label', 'Unknown')}")
            print(f"Source Type: {current_source.get('type', 'Unknown')}")
            print(f"Source ID: {current_source.get('id', 'Unknown')}")
        else:
            print("\nNo current source configured")
        
        sources = source_manager.get_sources()
        print(f"\nTotal Sources: {len(sources)}")
        
        if sources:
            print("\nAll Sources:")
            for i, source in enumerate(sources):
                marker = " <-- CURRENT" if i == source_index else ""
                print(f"  {i}. {source.get('label', 'Unknown')} ({source.get('type', 'Unknown')}){marker}")
    
    except Exception as e:
        print(f"\nError loading sources: {e}")
    
    print("\n" + "=" * 60)


def show_dashboard():
    """Show interactive dashboard (refreshes every 2 seconds)."""
    import time
    
    try:
        while True:
            # Clear screen (ANSI escape code)
            print("\033[2J\033[H", end='')
            
            show_status()
            
            # Show recent history
            print("\nRECENT PLAYBACK HISTORY")
            print("=" * 60)
            
            try:
                history = PlaybackHistory()
                recent = history.get_recent(limit=10)
                
                if recent:
                    for entry in recent:
                        timestamp = format_timestamp(entry.get('timestamp', ''))
                        action = entry.get('action', 'unknown')
                        event_type = entry.get('event_type', '')
                        source_label = entry.get('source_label') or 'Unknown'
                        item_name = entry.get('item_name') or ''
                        
                        if action == 'playback_start':
                            item_str = f" - {item_name}" if item_name else ""
                            print(f"{timestamp} | PLAY | {source_label}{item_str}")
                        elif action == 'source_change':
                            print(f"{timestamp} | SOURCE CHANGE | {source_label}")
                        elif event_type == 'user_input':
                            action_display = action.replace('_', ' ').upper()
                            if source_label and source_label != 'Unknown':
                                print(f"{timestamp} | {action_display} | {source_label}")
                            else:
                                print(f"{timestamp} | {action_display}")
                        elif action in ('pause', 'resume', 'next', 'previous'):
                            print(f"{timestamp} | {action.upper()} | {source_label}")
                        else:
                            event_prefix = f"[{event_type.upper()}] " if event_type else ""
                            print(f"{timestamp} | {event_prefix}{action.replace('_', ' ').upper()}")
                else:
                    print("No history available")
            
            except Exception as e:
                print(f"Error loading history: {e}")
            
            print("\n" + "=" * 60)
            print("Press Ctrl+C to exit")
            print("Refreshing in 2 seconds...")
            
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\n\nDashboard closed.")


def show_history(limit: int = 50):
    """Show playback history."""
    print("=" * 60)
    print(f"PLAYBACK HISTORY (Last {limit} entries)")
    print("=" * 60)
    
    try:
        history = PlaybackHistory()
        entries = history.get_recent(limit=limit)
        
        if not entries:
            print("\nNo history available.")
            return
        
        print()
        for entry in entries:
            timestamp = format_timestamp(entry.get('timestamp', ''))
            action = entry.get('action', 'unknown')
            event_type = entry.get('event_type', '')
            source_label = entry.get('source_label') or 'Unknown'
            item_name = entry.get('item_name') or ''
            value = entry.get('value')
            duration_ms = entry.get('duration_ms')
            
            # Format based on event type and action
            if action == 'playback_start':
                item_str = f" - {item_name}" if item_name else ""
                print(f"{timestamp} | PLAY | {source_label}{item_str}")
            elif action == 'source_change':
                print(f"{timestamp} | SOURCE CHANGE | {source_label}")
            elif event_type == 'user_input':
                # User input events
                action_display = action.replace('_', ' ').upper()
                if source_label and source_label != 'Unknown':
                    print(f"{timestamp} | {action_display} | {source_label}")
                else:
                    print(f"{timestamp} | {action_display}")
            elif event_type == 'audio':
                # Audio events
                if value is not None:
                    if action in ('volume_set', 'volume_adjust'):
                        print(f"{timestamp} | {action.replace('_', ' ').upper()} | {value:.0f}%")
                    else:
                        print(f"{timestamp} | {action.replace('_', ' ').upper()}")
                else:
                    print(f"{timestamp} | {action.replace('_', ' ').upper()}")
            elif event_type == 'performance' and duration_ms:
                print(f"{timestamp} | {action.replace('_', ' ').upper()} | {duration_ms:.2f}ms")
            elif event_type == 'network':
                status = entry.get('status', '')
                print(f"{timestamp} | {action.replace('_', ' ').upper()} | {status}")
            elif action in ('pause', 'resume', 'next', 'previous'):
                print(f"{timestamp} | {action.upper()} | {source_label}")
            else:
                # Generic display
                event_prefix = f"[{event_type.upper()}] " if event_type else ""
                print(f"{timestamp} | {event_prefix}{action.replace('_', ' ').upper()}")
        
        print("\n" + "=" * 60)
    
    except Exception as e:
        print(f"Error loading history: {e}")


def cache_sources(force: bool = False):
    """Manually trigger Piper TTS cache generation for all sources."""
    from utils.announcements import generate_cached_audio, ensure_cache_directory, get_cache_path
    
    print("=" * 60)
    print("GENERATING PIPER TTS CACHE FOR SOURCES")
    print("=" * 60)
    
    try:
        source_manager = SourceManager()
        sources = source_manager.get_sources()
        
        if not sources:
            print("\nNo sources configured.")
            return
        
        print(f"\nFound {len(sources)} sources")
        print("Generating cache files...\n")
        
        ensure_cache_directory()
        missing_count = 0
        cached_count = 0
        failed_count = 0
        
        for i, source in enumerate(sources, 1):
            source_label = source.get('label', source.get('id', 'Unknown source'))
            cache_path = get_cache_path(source_label)
            
            # Check if already cached
            if not force and cache_path.exists() and cache_path.stat().st_size > 0:
                print(f"[{i}/{len(sources)}] ✓ Already cached: {source_label}")
                cached_count += 1
            else:
                # If forcing, delete existing cache file to force regeneration
                if force and cache_path.exists():
                    try:
                        cache_path.unlink()
                        print(f"[{i}/{len(sources)}] Regenerating: {source_label}...", end=' ', flush=True)
                    except Exception as e:
                        print(f"[{i}/{len(sources)}] Warning: Could not delete existing cache for {source_label}: {e}")
                        print(f"[{i}/{len(sources)}] Generating: {source_label}...", end=' ', flush=True)
                else:
                    print(f"[{i}/{len(sources)}] Generating: {source_label}...", end=' ', flush=True)
                
                if generate_cached_audio(source_label):
                    print("✓")
                    cached_count += 1
                else:
                    print("✗ Failed")
                    failed_count += 1
                    missing_count += 1
        
        print("\n" + "=" * 60)
        print(f"Cache generation complete:")
        print(f"  ✓ Cached: {cached_count}")
        if missing_count > 0:
            print(f"  ✗ Failed: {failed_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError generating cache: {e}")
        import traceback
        traceback.print_exc()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Music Player CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status          Show current status
  %(prog)s dashboard       Show live dashboard (refreshes every 2s)
  %(prog)s history         Show last 50 history entries
  %(prog)s history -n 100  Show last 100 history entries
  %(prog)s cache           Generate Piper TTS cache for all sources
  %(prog)s cache -f        Force regenerate all cache files
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    subparsers.add_parser('status', help='Show current player status')
    
    # Dashboard command
    subparsers.add_parser('dashboard', help='Show live dashboard (Ctrl+C to exit)')
    
    # History command
    history_parser = subparsers.add_parser('history', help='Show playback history')
    history_parser.add_argument(
        '-n', '--limit',
        type=int,
        default=50,
        help='Number of entries to show (default: 50)'
    )
    
    # Cache command
    cache_parser = subparsers.add_parser('cache', help='Generate Piper TTS cache for all sources')
    cache_parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force regeneration of existing cache files'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'status':
        show_status()
    elif args.command == 'dashboard':
        show_dashboard()
    elif args.command == 'history':
        show_history(args.limit)
    elif args.command == 'cache':
        cache_sources(force=args.force)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

