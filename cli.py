#!/usr/bin/env python3
"""CLI tool for monitoring player status and history."""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
from sources import SourceManager, DEFAULT_STATE_FILE
from playback_history import PlaybackHistory, DEFAULT_HISTORY_FILE

# Try to import player controller for live status
try:
    from player_controller import PlayerController
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
                        source_label = entry.get('source_label', 'Unknown')
                        item_name = entry.get('item_name', '')
                        
                        if action == 'play':
                            item_str = f" - {item_name}" if item_name else ""
                            print(f"{timestamp} | PLAY | {source_label}{item_str}")
                        elif action == 'source_change':
                            print(f"{timestamp} | SOURCE CHANGE | {source_label}")
                        elif action in ('pause', 'resume', 'next', 'previous'):
                            print(f"{timestamp} | {action.upper()} | {source_label}")
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
            source_label = entry.get('source_label', 'Unknown')
            item_name = entry.get('item_name', '')
            
            if action == 'play':
                item_str = f" - {item_name}" if item_name else ""
                print(f"{timestamp} | PLAY | {source_label}{item_str}")
            elif action == 'source_change':
                print(f"{timestamp} | SOURCE CHANGE | {source_label}")
            elif action in ('pause', 'resume', 'next', 'previous'):
                print(f"{timestamp} | {action.upper()} | {source_label}")
            else:
                print(f"{timestamp} | {action.upper()} | {source_label}")
        
        print("\n" + "=" * 60)
    
    except Exception as e:
        print(f"Error loading history: {e}")


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
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()

