"""Playback history logging and retrieval using Supabase."""
import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    def load_dotenv(*args, **kwargs):
        pass  # No-op if not available

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    create_client = None
    Client = None

logger = logging.getLogger(__name__)

# Default paths - use current working directory if script is in rodrigo_radio directory
# Otherwise fall back to /home/pi/rodrigo_radio for backwards compatibility
_SCRIPT_DIR = Path(__file__).parent.absolute()
# If we're in a subdirectory (core/, hardware/, etc.), go up to project root
if _SCRIPT_DIR.name in ("core", "hardware", "utils", "scripts", "backends"):
    _BASE_DIR = _SCRIPT_DIR.parent
elif _SCRIPT_DIR.name == "rodrigo_radio" or (_SCRIPT_DIR / "config" / "sources.json.example").exists():
    _BASE_DIR = _SCRIPT_DIR
else:
    _BASE_DIR = Path("/home/pi/rodrigo_radio")

# Batch write configuration
BATCH_SIZE = 50  # Write when buffer reaches this many entries
SYNC_INTERVAL = 60  # Sync every 60 seconds as safety net
NETWORK_CHECK_INTERVAL = 30  # Check network connectivity every 30 seconds


class SupabaseBatchLogger:
    """Supabase logger with batch writes and offline buffering - zero SD card writes."""
    
    def __init__(self):
        """Initialize Supabase batch logger."""
        self._buffer: List[Dict] = []
        self._buffer_lock = threading.Lock()
        self._sync_thread: Optional[threading.Thread] = None
        self._connection_monitor_thread: Optional[threading.Thread] = None
        self._stop_sync = threading.Event()
        self._stop_monitor = threading.Event()
        self._client: Optional[Client] = None
        self._is_online = False
        self._last_online_state = False
        
        if not SUPABASE_AVAILABLE:
            logger.warning("Supabase packages not available. Install with: pip install supabase python-dotenv")
            return
        
        # Load environment variables
        self._load_env()
        
        # Initialize Supabase client
        if self.supabase_url and self.supabase_key:
            try:
                self._client = create_client(self.supabase_url, self.supabase_key)
                logger.info("Supabase client initialized")
                self._is_online = self._check_network()
            except Exception as e:
                logger.error(f"Error initializing Supabase client: {e}")
        else:
            logger.warning("Supabase credentials not found - logging will be buffered in memory only")
        
        # Start background threads
        self._start_sync_thread()
        self._start_connection_monitor()
    
    def _load_env(self):
        """Load environment variables from .env file or environment."""
        # Try to load .env file from project root
        if DOTENV_AVAILABLE and load_dotenv:
            env_file = _BASE_DIR / ".env"
            if env_file.exists():
                try:
                    load_dotenv(env_file)
                    logger.debug(f"Loaded .env file from {env_file}")
                except Exception as e:
                    logger.debug(f"Error loading .env file: {e}")
        
        # Try DATABASE_URL first (Supabase connection string format)
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            # Parse Supabase connection string
            # Format: postgresql://postgres:[password]@[host]:[port]/postgres
            # Or: https://[project-ref].supabase.co
            try:
                if database_url.startswith("https://"):
                    # Direct Supabase URL
                    self.supabase_url = database_url.rstrip("/")
                    # Try to get key from SUPABASE_KEY env var
                    self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
                elif "supabase.co" in database_url:
                    # Extract project URL from connection string
                    # postgresql://postgres:...@db.xxxxx.supabase.co:5432/postgres
                    parts = database_url.split("@")
                    if len(parts) > 1:
                        host_part = parts[1].split(":")[0]
                        if host_part.startswith("db."):
                            project_ref = host_part.replace("db.", "").replace(".supabase.co", "")
                            self.supabase_url = f"https://{project_ref}.supabase.co"
                        else:
                            self.supabase_url = f"https://{host_part}"
                    else:
                        self.supabase_url = None
                    self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
                else:
                    self.supabase_url = None
                    self.supabase_key = None
            except Exception as e:
                logger.warning(f"Error parsing DATABASE_URL: {e}")
                self.supabase_url = None
                self.supabase_key = None
        else:
            # Try direct environment variables
            self.supabase_url = os.getenv("SUPABASE_URL")
            self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase credentials not found in environment. Set SUPABASE_URL and SUPABASE_KEY (or DATABASE_URL)")
    
    def _check_network(self) -> bool:
        """Check if network connectivity is available."""
        try:
            # Try to resolve a well-known domain name (tests DNS resolution)
            socket.gethostbyname('google.com')
            return True
        except (socket.gaierror, OSError):
            return False
    
    def log(self, timestamp: float, log_level: str, event_type: str, action: str,
             source_id: Optional[str] = None, source_label: Optional[str] = None,
             source_type: Optional[str] = None, item_name: Optional[str] = None,
             status: Optional[str] = None, duration_ms: Optional[float] = None,
             value: Optional[float] = None, metadata: Optional[str] = None):
        """
        Add log entry to buffer (thread-safe).
        
        Args:
            timestamp: Unix timestamp with milliseconds
            log_level: DEBUG, INFO, WARNING, ERROR, CRITICAL
            event_type: user_input, system, performance, network, audio, config
            action: Specific action name
            source_id: Source identifier
            source_label: Human-readable source name
            source_type: youtube, spotify, etc.
            item_name: Track/playlist name
            status: success, failure, error, retry, etc.
            duration_ms: Duration in milliseconds
            value: Numeric value (volume %, dB, etc.)
            metadata: JSON string for additional data
        """
        entry = {
            'timestamp': timestamp,
            'log_level': log_level,
            'event_type': event_type,
            'action': action,
            'source_id': source_id,
            'source_label': source_label,
            'source_type': source_type,
            'item_name': item_name,
            'status': status,
            'duration_ms': duration_ms,
            'value': value,
            'metadata': metadata
        }
        
        with self._buffer_lock:
            self._buffer.append(entry)
            buffer_size = len(self._buffer)
        
        # Sync if buffer reaches threshold and we're online
        if buffer_size >= BATCH_SIZE and self._is_online:
            self._sync_async()
    
    def _sync_async(self):
        """Trigger async sync to Supabase (non-blocking)."""
        if not self._client or not self._is_online:
            return
        
        # Start sync in background thread if not already running
        if self._sync_thread is None or not self._sync_thread.is_alive():
            self._sync_thread = threading.Thread(target=self._sync_to_supabase, daemon=True)
            self._sync_thread.start()
    
    def _sync_to_supabase(self):
        """Sync buffered entries to Supabase."""
        if not self._client:
            return
        
        with self._buffer_lock:
            if not self._buffer:
                return
            
            entries = self._buffer.copy()
            self._buffer.clear()
        
        if not entries:
            return
        
        try:
            # Batch insert to Supabase
            response = self._client.table('event_logs').insert(entries).execute()
            logger.debug(f"Synced {len(entries)} log entries to Supabase")
            
        except Exception as e:
            logger.error(f"Error syncing to Supabase: {e}")
            # Re-add entries to buffer on error (prevent data loss)
            with self._buffer_lock:
                self._buffer.extend(entries)
    
    def _start_sync_thread(self):
        """Start background thread for periodic syncing."""
        def sync_worker():
            while not self._stop_sync.wait(SYNC_INTERVAL):
                try:
                    if self._is_online:
                        self._sync_to_supabase()
                except Exception as e:
                    logger.error(f"Error in sync thread: {e}")
        
        self._sync_thread = threading.Thread(target=sync_worker, daemon=True)
        self._sync_thread.start()
        logger.debug("Background sync thread started")
    
    def _start_connection_monitor(self):
        """Start background thread for connection monitoring."""
        def monitor_worker():
            while not self._stop_monitor.wait(NETWORK_CHECK_INTERVAL):
                try:
                    was_online = self._is_online
                    self._is_online = self._check_network()
                    
                    # If connection restored, trigger sync
                    if not was_online and self._is_online:
                        logger.info("Network connection restored - syncing buffered logs")
                        self._sync_async()
                    elif was_online and not self._is_online:
                        logger.warning("Network connection lost - buffering logs in memory")
                    
                    self._last_online_state = self._is_online
                except Exception as e:
                    logger.error(f"Error in connection monitor thread: {e}")
        
        self._connection_monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        self._connection_monitor_thread.start()
        logger.debug("Connection monitor thread started")
    
    def close(self):
        """Close logger and sync remaining entries."""
        logger.debug("Closing Supabase batch logger...")
        self._stop_sync.set()
        self._stop_monitor.set()
        
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        if self._connection_monitor_thread and self._connection_monitor_thread.is_alive():
            self._connection_monitor_thread.join(timeout=5.0)
        
        # Final sync if online
        if self._is_online:
            self._sync_to_supabase()
        
        logger.debug("Supabase batch logger closed")


class PlaybackHistory:
    """Manages playback history logging using Supabase (zero SD card writes)."""
    
    def __init__(self):
        """Initialize playback history logger."""
        self._logger = SupabaseBatchLogger()
    
    def log_playback_start(self, source: Dict, item_name: Optional[str] = None):
        """
        Log the start of playback.
        
        Args:
            source: Source dictionary (from sources.json)
            item_name: Optional name of the current track/item
        """
        timestamp = time.time()
        self._logger.log(
            timestamp=timestamp,
            log_level='INFO',
            event_type='system',
            action='playback_start',
            source_id=source.get('id'),
            source_label=source.get('label'),
            source_type=source.get('type'),
            item_name=item_name,
            status='success'
        )
        logger.debug(f"Logged playback start: {source.get('label')}")
    
    def log_source_change(self, source: Dict):
        """Log a source change."""
        timestamp = time.time()
        self._logger.log(
            timestamp=timestamp,
            log_level='INFO',
            event_type='system',
            action='source_change',
            source_id=source.get('id'),
            source_label=source.get('label'),
            source_type=source.get('type'),
            status='success'
        )
        logger.debug(f"Logged source change: {source.get('label')}")
    
    def log_action(self, action: str, **kwargs):
        """
        Log a custom action (backward compatibility method).
        
        Args:
            action: Action name (e.g., 'pause', 'resume', 'next', 'previous')
            **kwargs: Additional data to log
        """
        # Map old action names to new event types
        event_type = 'system'
        if action in ('pause', 'resume', 'next', 'previous'):
            event_type = 'user_input'
        
        timestamp = time.time()
        metadata = json.dumps(kwargs) if kwargs else None
        
        self._logger.log(
            timestamp=timestamp,
            log_level='INFO',
            event_type=event_type,
            action=action,
            metadata=metadata,
            status='success'
        )
    
    def log_user_input(self, action: str, source: Optional[Dict] = None, **kwargs):
        """
        Log user input event (button press, encoder rotation, etc.).
        
        Args:
            action: Action name (e.g., 'button_play_pause', 'encoder_rotate_cw')
            source: Optional source dictionary
            **kwargs: Additional data
        """
        timestamp = time.time()
        metadata = json.dumps(kwargs) if kwargs else None
        
        self._logger.log(
            timestamp=timestamp,
            log_level='INFO',
            event_type='user_input',
            action=action,
            source_id=source.get('id') if source else None,
            source_label=source.get('label') if source else None,
            source_type=source.get('type') if source else None,
            metadata=metadata,
            status='success'
        )
    
    def log_audio_event(self, action: str, value: Optional[float] = None, **kwargs):
        """
        Log audio-related event (volume change, mute, etc.).
        
        Args:
            action: Action name (e.g., 'volume_set', 'volume_adjust', 'mute', 'unmute')
            value: Numeric value (volume %, dB, etc.)
            **kwargs: Additional data
        """
        timestamp = time.time()
        metadata = json.dumps(kwargs) if kwargs else None
        
        self._logger.log(
            timestamp=timestamp,
            log_level='INFO',
            event_type='audio',
            action=action,
            value=value,
            metadata=metadata,
            status='success'
        )
    
    def log_performance(self, action: str, duration_ms: float, **kwargs):
        """
        Log performance metric (loading time, duration, etc.).
        
        Args:
            action: Action name (e.g., 'source_load_time', 'cache_generation')
            duration_ms: Duration in milliseconds
            **kwargs: Additional data
        """
        timestamp = time.time()
        metadata = json.dumps(kwargs) if kwargs else None
        
        self._logger.log(
            timestamp=timestamp,
            log_level='DEBUG',
            event_type='performance',
            action=action,
            duration_ms=duration_ms,
            metadata=metadata,
            status='success'
        )
    
    def log_network_event(self, action: str, status: str, **kwargs):
        """
        Log network-related event (connection, retry, etc.).
        
        Args:
            action: Action name (e.g., 'connection_success', 'connection_failure', 'retry_attempt')
            status: Status (success, failure, error, retry, etc.)
            **kwargs: Additional data
        """
        timestamp = time.time()
        metadata = json.dumps(kwargs) if kwargs else None
        
        log_level = 'ERROR' if status in ('failure', 'error') else 'WARNING' if status == 'retry' else 'INFO'
        
        self._logger.log(
            timestamp=timestamp,
            log_level=log_level,
            event_type='network',
            action=action,
            status=status,
            metadata=metadata
        )
    
    def log_config_event(self, action: str, **kwargs):
        """
        Log configuration-related event.
        
        Args:
            action: Action name (e.g., 'sources_reloaded', 'config_changed')
            **kwargs: Additional data
        """
        timestamp = time.time()
        metadata = json.dumps(kwargs) if kwargs else None
        
        self._logger.log(
            timestamp=timestamp,
            log_level='INFO',
            event_type='config',
            action=action,
            metadata=metadata,
            status='success'
        )
    
    def get_recent(self, limit: int = 50) -> List[Dict]:
        """
        Get recent history entries from Supabase.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of history entries, most recent first
        """
        if not self._logger._client:
            logger.warning("Supabase client not available - cannot retrieve history")
            return []
        
        try:
            response = self._logger._client.table('event_logs')\
                .select('*')\
                .order('timestamp', desc=True)\
                .limit(limit)\
                .execute()
            
            entries = []
            for row in response.data:
                entry = {
                    'timestamp': datetime.fromtimestamp(row['timestamp']).isoformat() if row.get('timestamp') else '',
                    'action': row.get('action', 'unknown'),
                    'source_id': row.get('source_id'),
                    'source_label': row.get('source_label'),
                    'source_type': row.get('source_type'),
                    'item_name': row.get('item_name'),
                    'log_level': row.get('log_level'),
                    'event_type': row.get('event_type'),
                    'status': row.get('status'),
                    'duration_ms': row.get('duration_ms'),
                    'value': row.get('value')
                }
                
                # Parse metadata if present
                if row.get('metadata'):
                    try:
                        if isinstance(row['metadata'], str):
                            entry['metadata'] = json.loads(row['metadata'])
                        else:
                            entry['metadata'] = row['metadata']
                    except:
                        entry['metadata'] = row['metadata']
                
                entries.append(entry)
            
            return entries
            
        except Exception as e:
            logger.error(f"Error querying history from Supabase: {e}")
            return []
    
    def get_all(self) -> List[Dict]:
        """Get all history entries from Supabase (most recent first)."""
        if not self._logger._client:
            logger.warning("Supabase client not available - cannot retrieve history")
            return []
        
        try:
            response = self._logger._client.table('event_logs')\
                .select('*')\
                .order('timestamp', desc=True)\
                .execute()
            
            entries = []
            for row in response.data:
                entry = {
                    'timestamp': datetime.fromtimestamp(row['timestamp']).isoformat() if row.get('timestamp') else '',
                    'action': row.get('action', 'unknown'),
                    'source_id': row.get('source_id'),
                    'source_label': row.get('source_label'),
                    'source_type': row.get('source_type'),
                    'item_name': row.get('item_name'),
                    'log_level': row.get('log_level'),
                    'event_type': row.get('event_type'),
                    'status': row.get('status'),
                    'duration_ms': row.get('duration_ms'),
                    'value': row.get('value')
                }
                
                if row.get('metadata'):
                    try:
                        if isinstance(row['metadata'], str):
                            entry['metadata'] = json.loads(row['metadata'])
                        else:
                            entry['metadata'] = row['metadata']
                    except:
                        entry['metadata'] = row['metadata']
                
                entries.append(entry)
            
            return entries
            
        except Exception as e:
            logger.error(f"Error querying history from Supabase: {e}")
            return []
    
    def close(self):
        """Close the logger and sync remaining entries."""
        if self._logger:
            self._logger.close()
