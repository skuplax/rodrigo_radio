"""YouTube playback backend using yt-dlp and mpv."""
import subprocess
import signal
import logging
import re
from pathlib import Path
from typing import Optional
from backends.base import BaseBackend, BackendError

logger = logging.getLogger(__name__)


class YouTubeBackend(BaseBackend):
    """YouTube playback backend."""
    
    def __init__(self):
        super().__init__()
        self._mpv_process: Optional[subprocess.Popen] = None
        self._current_url: Optional[str] = None
        self._current_channel_id: Optional[str] = None
        self._current_playlist_id: Optional[str] = None
        self._is_paused = False
    
    def _get_live_stream_url(self, channel_id: str) -> Optional[str]:
        """
        Get the URL of a live stream from a channel if available.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Stream URL if live, None otherwise
        """
        try:
            # Use yt-dlp to check for live streams
            channel_url = f"https://www.youtube.com/channel/{channel_id}/live"
            cmd = [
                'yt-dlp',
                '--get-url',
                '--format', 'bestaudio',
                '--no-playlist',
                channel_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip()
                logger.info(f"Found live stream URL for channel {channel_id}")
                return url
            else:
                error_msg = result.stderr.strip() if result.stderr else "No error message"
                logger.debug(f"No live stream found for channel {channel_id}: {error_msg}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout checking for live stream: {channel_id}")
            return None
        except Exception as e:
            logger.error(f"Error checking for live stream: {e}")
            return None
    
    def _get_latest_video_url(self, channel_id: str) -> Optional[str]:
        """
        Get the URL of the latest video from a channel.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Stream URL of latest video
        """
        try:
            channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
            cmd = [
                'yt-dlp',
                '--get-url',
                '--format', 'bestaudio',
                '--playlist-end', '1',
                channel_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip()
                logger.info(f"Found latest video URL for channel {channel_id}")
                return url
            else:
                error_msg = result.stderr.strip() if result.stderr else "No error message"
                logger.error(f"Failed to get latest video for channel {channel_id}: {error_msg}")
                logger.debug(f"yt-dlp stdout: {result.stdout.strip()}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout getting latest video: {channel_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting latest video: {e}")
            return None
    
    def _get_playlist_url(self, playlist_id: str) -> Optional[str]:
        """
        Get the URL for a playlist (plays first item).
        
        Args:
            playlist_id: YouTube playlist ID
            
        Returns:
            Stream URL of first playlist item
        """
        try:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            cmd = [
                'yt-dlp',
                '--get-url',
                '--format', 'bestaudio',
                '--playlist-start', '1',
                '--playlist-end', '1',
                playlist_url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0 and result.stdout.strip():
                url = result.stdout.strip()
                logger.info(f"Found playlist URL for {playlist_id}")
                return url
            else:
                error_msg = result.stderr.strip() if result.stderr else "No error message"
                logger.error(f"Failed to get playlist URL: {playlist_id}: {error_msg}")
                logger.debug(f"yt-dlp stdout: {result.stdout.strip()}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout getting playlist: {playlist_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting playlist: {e}")
            return None
    
    def _get_video_title(self, url: str) -> Optional[str]:
        """Get the title of a video from its URL."""
        try:
            cmd = ['yt-dlp', '--get-title', '--no-playlist', url]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None
    
    def _start_playback(self, url: str, title: Optional[str] = None):
        """Start mpv playback with the given URL."""
        try:
            # Stop any existing playback
            self.stop()
            
            # Start mpv in subprocess
            # For HLS streams, add options for better compatibility
            cmd = [
                'mpv',
                '--no-video',
                '--no-terminal',
                '--quiet',
                '--stream-lavf-o=timeout=10000000',  # Increase timeout for HLS
                '--cache=yes',  # Enable caching for better stream handling
                url
            ]
            
            # Log stderr to a file for debugging
            log_file = Path("/home/skayflakes/music-player/logs/mpv.log")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            self._mpv_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=open(log_file, 'a')  # Log stderr for debugging
            )
            
            # Give mpv a moment to start
            import time
            time.sleep(0.5)
            
            # Check if process is still running
            if self._mpv_process.poll() is not None:
                # Process died immediately
                error_msg = "mpv process exited immediately"
                logger.error(f"Error starting playback: {error_msg}")
                # Try to read error from log
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        error_log = f.read()
                        if error_log:
                            logger.error(f"mpv error log: {error_log[-500:]}")  # Last 500 chars
                raise BackendError(f"Failed to start playback: {error_msg}")
            
            self.set_playing_state(True)
            self._is_paused = False
            self._current_url = url
            self.set_current_item(title or "YouTube Audio")
            
            logger.info(f"Started YouTube playback: {title or url}")
            
        except Exception as e:
            logger.error(f"Error starting playback: {e}")
            raise BackendError(f"Failed to start playback: {e}")
    
    def play(self, source_id: str, **kwargs) -> bool:
        """
        Start playing from a YouTube source.
        
        Args:
            source_id: Channel ID or playlist ID
            **kwargs: 
                - source_type: 'youtube_channel' or 'youtube_playlist'
                - channel_id: Channel ID (for channel sources)
                - playlist_id: Playlist ID (for playlist sources)
        """
        try:
            source_type = kwargs.get('source_type', 'youtube_channel')
            
            if source_type == 'youtube_channel':
                channel_id = kwargs.get('channel_id') or source_id
                self._current_channel_id = channel_id
                
                # Try live stream first
                url = self._get_live_stream_url(channel_id)
                
                if not url:
                    # Fall back to latest video
                    url = self._get_latest_video_url(channel_id)
                
                if not url:
                    raise BackendError(f"Could not get URL for channel {channel_id}")
                
                title = self._get_video_title(url)
                self._start_playback(url, title)
                return True
                
            elif source_type == 'youtube_playlist':
                playlist_id = kwargs.get('playlist_id') or source_id
                self._current_playlist_id = playlist_id
                
                url = self._get_playlist_url(playlist_id)
                
                if not url:
                    raise BackendError(f"Could not get URL for playlist {playlist_id}")
                
                title = self._get_video_title(url)
                self._start_playback(url, title)
                return True
            else:
                raise BackendError(f"Unknown source type: {source_type}")
                
        except Exception as e:
            logger.error(f"Error in play(): {e}")
            self.set_playing_state(False)
            return False
    
    def pause(self) -> bool:
        """Pause playback by sending SIGSTOP to mpv."""
        try:
            if self._mpv_process and self._mpv_process.poll() is None:
                self._mpv_process.send_signal(signal.SIGSTOP)
                self._is_paused = True
                logger.info("Paused YouTube playback")
                return True
            return False
        except Exception as e:
            logger.error(f"Error pausing: {e}")
            return False
    
    def resume(self) -> bool:
        """Resume playback by sending SIGCONT to mpv."""
        try:
            if self._mpv_process and self._mpv_process.poll() is None and self._is_paused:
                self._mpv_process.send_signal(signal.SIGCONT)
                self._is_paused = False
                self.set_playing_state(True)
                logger.info("Resumed YouTube playback")
                return True
            return False
        except Exception as e:
            logger.error(f"Error resuming: {e}")
            return False
    
    def stop(self) -> bool:
        """Stop playback completely."""
        try:
            if self._mpv_process:
                if self._mpv_process.poll() is None:
                    self._mpv_process.terminate()
                    try:
                        self._mpv_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._mpv_process.kill()
                        self._mpv_process.wait()
                
                self._mpv_process = None
            
            self.set_playing_state(False)
            self._is_paused = False
            self._current_url = None
            self.set_current_item(None)
            logger.info("Stopped YouTube playback")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping: {e}")
            return False
    
    def next(self) -> bool:
        """
        Skip to next item.
        For channels: get latest video again (or next in playlist if playing playlist)
        For playlists: advance to next item (not fully implemented, would need playlist tracking)
        """
        # For now, restart current source
        if self._current_channel_id:
            return self.play(self._current_channel_id, source_type='youtube_channel', channel_id=self._current_channel_id)
        elif self._current_playlist_id:
            # Playlist next would require tracking position
            logger.warning("Next track in playlist not fully implemented")
            return False
        return False
    
    def previous(self) -> bool:
        """Go to previous item (not fully supported for YouTube)."""
        logger.warning("Previous track not supported for YouTube")
        return False
    
    def is_playing(self) -> bool:
        """Check if currently playing (and not paused)."""
        if self._mpv_process:
            if self._mpv_process.poll() is not None:
                # Process has ended
                self.set_playing_state(False)
                return False
            return self._is_playing and not self._is_paused
        return False

