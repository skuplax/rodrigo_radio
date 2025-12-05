"""Supabase logging handler for Python logging module."""
import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

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
    create_client = None
    Client = None

logger = logging.getLogger(__name__)

# Default paths
_SCRIPT_DIR = Path(__file__).parent.absolute()
if _SCRIPT_DIR.name in ("core", "hardware", "utils", "scripts", "backends"):
    _BASE_DIR = _SCRIPT_DIR.parent
elif _SCRIPT_DIR.name == "rodrigo_radio" or (_SCRIPT_DIR / "config" / "sources.json.example").exists():
    _BASE_DIR = _SCRIPT_DIR
else:
    _BASE_DIR = Path("/home/pi/rodrigo_radio")

# Batch configuration
LOG_BATCH_SIZE = 50
LOG_SYNC_INTERVAL = 60
LOG_NETWORK_CHECK_INTERVAL = 30


class SupabaseLogHandler(logging.Handler):
    """Custom logging handler that sends logs to Supabase."""
    
    def __init__(self, level=logging.NOTSET):
        """Initialize Supabase log handler."""
        super().__init__(level)
        self._buffer: List[Dict] = []
        self._buffer_lock = threading.Lock()
        self._sync_thread: Optional[threading.Thread] = None
        self._connection_monitor_thread: Optional[threading.Thread] = None
        self._stop_sync = threading.Event()
        self._stop_monitor = threading.Event()
        self._client: Optional[Client] = None
        self._is_online = False
        
        if not SUPABASE_AVAILABLE:
            logging.warning("Supabase packages not available. Logs will be buffered in memory only.")
            return
        
        # Load environment variables
        self._load_env()
        
        # Initialize Supabase client
        if self.supabase_url and self.supabase_key:
            try:
                self._client = create_client(self.supabase_url, self.supabase_key)
                self._is_online = self._check_network()
            except Exception as e:
                logging.error(f"Error initializing Supabase client for logging: {e}")
        else:
            logging.warning("Supabase credentials not found - logs will be buffered in memory only")
        
        # Start background threads
        self._start_sync_thread()
        self._start_connection_monitor()
    
    def _load_env(self):
        """Load environment variables from .env file or environment."""
        if DOTENV_AVAILABLE and load_dotenv:
            env_file = _BASE_DIR / ".env"
            if env_file.exists():
                try:
                    load_dotenv(env_file)
                except Exception:
                    pass
        
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            try:
                if database_url.startswith("https://"):
                    self.supabase_url = database_url.rstrip("/")
                    self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
                elif "supabase.co" in database_url:
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
            except Exception:
                self.supabase_url = None
                self.supabase_key = None
        else:
            self.supabase_url = os.getenv("SUPABASE_URL")
            self.supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    def _check_network(self) -> bool:
        """Check if network connectivity is available."""
        try:
            socket.gethostbyname('google.com')
            return True
        except (socket.gaierror, OSError):
            return False
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record to Supabase."""
        try:
            # Format the log message
            msg = self.format(record)
            
            # Determine event type based on logger name
            event_type = 'system'
            if 'network' in record.name.lower() or 'connection' in msg.lower():
                event_type = 'network'
            elif 'audio' in record.name.lower() or 'volume' in msg.lower():
                event_type = 'audio'
            elif 'performance' in record.name.lower():
                event_type = 'performance'
            elif 'config' in record.name.lower():
                event_type = 'config'
            
            # Map log level to our log_level
            log_level_map = {
                logging.DEBUG: 'DEBUG',
                logging.INFO: 'INFO',
                logging.WARNING: 'WARNING',
                logging.ERROR: 'ERROR',
                logging.CRITICAL: 'CRITICAL'
            }
            log_level = log_level_map.get(record.levelno, 'INFO')
            
            # Extract action from message or use logger name
            action = 'log_message'
            if hasattr(record, 'action'):
                action = record.action
            elif record.funcName and record.funcName != '<module>':
                action = f"{record.name}.{record.funcName}"
            else:
                action = record.name.split('.')[-1]
            
            # Create log entry
            entry = {
                'timestamp': record.created,  # Unix timestamp
                'log_level': log_level,
                'event_type': event_type,
                'action': action,
                'status': 'success' if record.levelno < logging.ERROR else 'error',
                'metadata': json.dumps({
                    'logger': record.name,
                    'module': record.module,
                    'function': record.funcName,
                    'line': record.lineno,
                    'message': msg,
                    'pathname': record.pathname,
                    'exc_info': self.format(record) if record.exc_info else None
                })
            }
            
            # Add to buffer
            with self._buffer_lock:
                self._buffer.append(entry)
                buffer_size = len(self._buffer)
            
            # Sync if buffer reaches threshold and we're online
            if buffer_size >= LOG_BATCH_SIZE and self._is_online:
                self._sync_async()
                
        except Exception:
            # Don't let logging errors break the application
            self.handleError(record)
    
    def _sync_async(self):
        """Trigger async sync to Supabase (non-blocking)."""
        if not self._client or not self._is_online:
            return
        
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
            self._client.table('event_logs').insert(entries).execute()
        except Exception as e:
            # Re-add entries to buffer on error
            with self._buffer_lock:
                self._buffer.extend(entries)
            # Log error but don't break
            logging.error(f"Error syncing logs to Supabase: {e}", exc_info=False)
    
    def _start_sync_thread(self):
        """Start background thread for periodic syncing."""
        def sync_worker():
            while not self._stop_sync.wait(LOG_SYNC_INTERVAL):
                try:
                    if self._is_online:
                        self._sync_to_supabase()
                except Exception:
                    pass
        
        self._sync_thread = threading.Thread(target=sync_worker, daemon=True)
        self._sync_thread.start()
    
    def _start_connection_monitor(self):
        """Start background thread for connection monitoring."""
        def monitor_worker():
            while not self._stop_monitor.wait(LOG_NETWORK_CHECK_INTERVAL):
                try:
                    was_online = self._is_online
                    self._is_online = self._check_network()
                    
                    if not was_online and self._is_online:
                        self._sync_async()
                except Exception:
                    pass
        
        self._connection_monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
        self._connection_monitor_thread.start()
    
    def close(self):
        """Close handler and sync remaining entries."""
        self._stop_sync.set()
        self._stop_monitor.set()
        
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        if self._connection_monitor_thread and self._connection_monitor_thread.is_alive():
            self._connection_monitor_thread.join(timeout=5.0)
        
        if self._is_online:
            self._sync_to_supabase()
        
        super().close()






