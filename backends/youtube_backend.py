"""YouTube playback backend using RSS feeds and mpv with auto-advance."""
import subprocess
import signal
import logging
import re
import time
import json
import threading
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from backends.base import BaseBackend, BackendError
from utils.sound_feedback import (
    play_not_found_beep,
    play_network_error_beep,
    play_connection_error_beep,
    PulsingBeep
)

logger = logging.getLogger(__name__)


class YouTubeBackend(BaseBackend):
    """YouTube playback backend with RSS feeds and auto-advance."""
    
    def __init__(self):
        super().__init__()
        self._mpv_process: Optional[subprocess.Popen] = None
        self._current_url: Optional[str] = None
        self._current_channel_id: Optional[str] = None
        self._current_playlist_id: Optional[str] = None
        self._is_paused = False
        
        # Video queue management for auto-advance
        self._video_queue: List[Dict] = []
        self._current_video_index: int = 0
        self._monitoring_thread: Optional[threading.Thread] = None
        self._monitoring_active: bool = False
        self._last_rss_refresh: float = 0.0
        self._rss_refresh_interval: float = 300.0  # 5 minutes
        
        # Pulsing beep for loading feedback
        self._pulsing_beep: Optional[PulsingBeep] = None
    
    def _get_video_list_from_rss(self, channel_id: str, limit: int = 20) -> List[Dict]:
        """
        Get list of recent videos from YouTube channel RSS feed.
        
        Args:
            channel_id: YouTube channel ID
            limit: Maximum number of videos to return
            
        Returns:
            List of dicts with 'video_id', 'title', 'published', 'url' for each video
        """
        op_start = time.perf_counter()
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            
            fetch_start = time.perf_counter()
            # Fetch RSS feed with timeout
            req = urllib.request.Request(rss_url)
            req.add_header('User-Agent', 'Mozilla/5.0 (compatible; RodrigoRadio/1.0)')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                rss_data = response.read()
            
            fetch_time = time.perf_counter() - fetch_start
            
            # Parse XML
            parse_start = time.perf_counter()
            root = ET.fromstring(rss_data)
            
            # YouTube RSS uses Atom format with namespaces
            # Register namespaces to handle them properly
            namespaces = {
                'atom': 'http://www.w3.org/2005/Atom',
                'yt': 'http://www.youtube.com/xml/schemas/2015',
                'media': 'http://search.yahoo.com/mrss/'
            }
            
            # Also try without namespace prefix (some parsers handle it differently)
            videos = []
            
            # Find all entry elements (try with and without namespace)
            entries = root.findall('.//{http://www.w3.org/2005/Atom}entry') or root.findall('entry')
            
            for entry in entries[:limit]:
                # Try to find videoId with namespace
                video_id_elem = (entry.find('{http://www.youtube.com/xml/schemas/2015}videoId') or 
                                entry.find('yt:videoId', namespaces))
                title_elem = (entry.find('{http://www.w3.org/2005/Atom}title') or 
                             entry.find('title'))
                published_elem = (entry.find('{http://www.w3.org/2005/Atom}published') or 
                                 entry.find('published'))
                link_elem = (entry.find('{http://www.w3.org/2005/Atom}link') or 
                            entry.find('link'))
                
                if video_id_elem is not None and video_id_elem.text:
                    video_id = video_id_elem.text
                    title = title_elem.text if title_elem is not None and title_elem.text else "Unknown"
                    published = published_elem.text if published_elem is not None and published_elem.text else ""
                    
                    # Construct YouTube URL
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    if link_elem is not None:
                        href = link_elem.get('href')
                        if href:
                            video_url = href
                    
                    videos.append({
                        'video_id': video_id,
                        'title': title,
                        'published': published,
                        'url': video_url
                    })
            
            parse_time = time.perf_counter() - parse_start
            total_time = time.perf_counter() - op_start
            
            log_start = time.perf_counter()
            logger.info(f"Fetched {len(videos)} videos from RSS for channel {channel_id}")
            log_time = time.perf_counter() - log_start
            
            logger.info(f"[BENCHMARK] _get_video_list_from_rss: total={total_time*1000:.2f}ms | "
                       f"fetch={fetch_time*1000:.2f}ms | parse={parse_time*1000:.2f}ms | log={log_time*1000:.2f}ms")
            
            return videos
            
        except urllib.error.URLError as e:
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['network', 'connection', 'timeout', 'dns', 'socket']):
                play_network_error_beep()
            logger.error(f"Error fetching RSS feed for channel {channel_id}: {e}")
            return []
        except ET.ParseError as e:
            logger.error(f"Error parsing RSS feed for channel {channel_id}: {e}")
            return []
        except Exception as e:
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['network', 'connection', 'timeout', 'dns', 'socket']):
                play_network_error_beep()
            logger.error(f"Unexpected error fetching RSS feed for channel {channel_id}: {e}")
            return []
    
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
            play_network_error_beep()
            return None
        except Exception as e:
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['network', 'connection', 'timeout', 'dns', 'socket']):
                play_network_error_beep()
            logger.error(f"Error getting playlist: {e}")
            return None
    
    def _start_playback(self, url: str, title: Optional[str] = None):
        """Start mpv playback with the given URL."""
        try:
            # Stop any existing playback
            self.stop()
            
            # Start mpv in subprocess
            # For HLS streams, add options for better compatibility
            # Use ALSA directly to bypass PipeWire and reduce latency
            cmd = [
                'mpv',
                '--no-video',
                '--no-terminal',
                '--quiet',
                '--ao=alsa',  # Use ALSA directly, bypass PipeWire for lower latency
                '--stream-lavf-o=timeout=10000000',  # Increase timeout for HLS
                '--cache=yes',  # Enable caching for better stream handling
                url
            ]
            
            # Log stderr to a file for debugging
            log_file = Path("/home/skayflakes/rodrigo_radio/logs/mpv.log")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            
            self._mpv_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=open(log_file, 'a')  # Log stderr for debugging
            )
            
            # Give mpv a moment to start
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
                
                # Force stop pulsing beep on error
                if self._pulsing_beep:
                    self._pulsing_beep._force_stop()
                    self._pulsing_beep = None
                
                play_connection_error_beep()
                raise BackendError(f"Failed to start playback: {error_msg}")
            
            self.set_playing_state(True)
            self._is_paused = False
            self._current_url = url
            self.set_current_item(title or "YouTube Audio")
            
            # Start monitoring thread to detect when playback truly starts
            def detect_playback_start():
                """Monitor mpv to detect when playback actually starts."""
                max_wait = 10.0  # Maximum time to wait for playback to start
                check_interval = 0.5  # Check every 0.5 seconds
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    if not self._mpv_process:
                        break
                    
                    # Check if process is still running
                    if self._mpv_process.poll() is not None:
                        # Process died, stop beep immediately
                        if self._pulsing_beep:
                            self._pulsing_beep._force_stop()
                            self._pulsing_beep = None
                        break
                    
                    # Check if mpv has been running for a bit (indicates successful start)
                    # After 2 seconds of mpv running, we assume playback has started
                    elapsed = time.time() - start_time
                    if elapsed >= 2.0:
                        # mpv has been running for 2+ seconds, likely playing
                        # Request stop (will continue for tail_duration)
                        if self._pulsing_beep:
                            self._pulsing_beep.stop()  # This starts the 3s tail
                        break
                    
                    time.sleep(check_interval)
                
                # If we've waited the max time, stop beep anyway
                if self._pulsing_beep:
                    self._pulsing_beep.stop()  # Start tail
        
            # Start detection in background
            threading.Thread(target=detect_playback_start, daemon=True).start()
            
            logger.info(f"Started YouTube playback: {title or url}")
            
        except Exception as e:
            # Force stop pulsing beep on error
            if self._pulsing_beep:
                self._pulsing_beep._force_stop()
                self._pulsing_beep = None
            logger.error(f"Error starting playback: {e}")
            raise BackendError(f"Failed to start playback: {e}")
    
    def _check_live_stream_async(self, channel_id: str) -> Optional[str]:
        """
        Check for live stream in background (non-blocking).
        Uses lightweight RSS check or HTTP check.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            Live stream URL if found, None otherwise
        """
        try:
            # Quick check: try to access /live endpoint
            live_url = f"https://www.youtube.com/channel/{channel_id}/live"
            req = urllib.request.Request(live_url)
            req.add_header('User-Agent', 'Mozilla/5.0 (compatible; RodrigoRadio/1.0)')
            
            with urllib.request.urlopen(req, timeout=5) as response:
                # If we get a response, check if it's actually live
                # For now, we'll use a simple heuristic: if RSS has a very recent video
                # that might be live, or we can check the page content
                # This is a lightweight check - full detection would require more parsing
                pass
            
            # For now, return None (live stream detection can be enhanced later)
            # The main benefit is this runs in background without blocking
            return None
            
        except Exception:
            # Silently fail - this is background check
            return None
    
    def _refresh_video_list(self, channel_id: str) -> bool:
        """
        Periodically update video list from RSS feed.
        
        Args:
            channel_id: YouTube channel ID
            
        Returns:
            True if refresh was successful, False otherwise
        """
        try:
            new_videos = self._get_video_list_from_rss(channel_id, limit=20)
            if new_videos:
                # Check if current video is still in the list
                current_video_id = None
                if self._video_queue and self._current_video_index < len(self._video_queue):
                    current_video_id = self._video_queue[self._current_video_index].get('video_id')
                
                # Update queue
                self._video_queue = new_videos
                self._last_rss_refresh = time.time()
                
                # Reset index if current video no longer in list
                if current_video_id:
                    found_index = next((i for i, v in enumerate(new_videos) 
                                       if v.get('video_id') == current_video_id), None)
                    if found_index is None:
                        # Current video not found, reset to latest
                        self._current_video_index = 0
                        logger.info("Current video no longer in RSS feed, resetting to latest")
                    else:
                        self._current_video_index = found_index
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error refreshing video list: {e}")
            return False
    
    def _play_next_video(self) -> bool:
        """
        Advance to next video in queue when current video ends.
        
        Returns:
            True if next video started successfully, False otherwise
        """
        if not self._current_channel_id:
            return False
        
        try:
            # Check if we need to refresh RSS
            if (time.time() - self._last_rss_refresh) > self._rss_refresh_interval:
                logger.info("Refreshing video list from RSS...")
                self._refresh_video_list(self._current_channel_id)
            
            # Increment to next video
            self._current_video_index += 1
            
            # Check if we've reached end of queue
            if self._current_video_index >= len(self._video_queue):
                # Refresh RSS to get more videos
                logger.info("Reached end of video queue, refreshing...")
                if not self._refresh_video_list(self._current_channel_id):
                    logger.warning("Failed to refresh video list, looping back to start")
                    self._current_video_index = 0
                else:
                    # After refresh, check if we're still past the end
                    if self._current_video_index >= len(self._video_queue):
                        self._current_video_index = 0
            
            # Get next video
            if self._current_video_index < len(self._video_queue):
                next_video = self._video_queue[self._current_video_index]
                video_url = next_video['url']
                video_title = next_video.get('title', 'YouTube Audio')
                
                logger.info(f"Auto-advancing to next video: {video_title}")
                
                # Start pulsing beep to indicate loading next video (50% volume, 3s tail)
                self._pulsing_beep = PulsingBeep(frequency=300.0, pulse_duration=0.3, pause_duration=0.3, volume=0.5, tail_duration=3.0)
                self._pulsing_beep.start()
                logger.info("Started pulsing beep for next video loading")
                
                try:
                    # Check for live stream first (quick check, but don't block too long)
                    # If live stream is found, it will interrupt and switch
                    def check_live():
                        try:
                            live_url = self._check_live_stream_async(self._current_channel_id)
                            if live_url:
                                logger.info("Live stream detected, switching...")
                                # Switch to live stream (this will stop current playback)
                                self._start_playback(live_url, "Live Stream")
                        except Exception as e:
                            logger.debug(f"Live stream check error: {e}")
                    
                    # Start live stream check in background
                    threading.Thread(target=check_live, daemon=True).start()
                    
                    # Start next video (live stream check will interrupt if found)
                    self._start_playback(video_url, video_title)
                    return True
                except Exception as e:
                    # Stop pulsing beep on error
                    if self._pulsing_beep:
                        self._pulsing_beep.stop()
                        self._pulsing_beep = None
                    raise
            else:
                logger.warning("No more videos in queue")
                return False
                
        except Exception as e:
            logger.error(f"Error playing next video: {e}")
            return False
    
    def _monitor_playback(self):
        """
        Background thread to monitor mpv process and detect when video ends.
        When video ends, automatically advance to next video.
        """
        while self._monitoring_active:
            try:
                if self._mpv_process:
                    # Check if process has ended
                    return_code = self._mpv_process.poll()
                    if return_code is not None:
                        # Process has ended (video finished)
                        logger.info(f"Video playback ended (return code: {return_code})")
                        
                        # Only auto-advance if we're playing a channel (not manually stopped)
                        if self._monitoring_active and self._current_channel_id:
                            # Small delay to ensure process is fully cleaned up
                            time.sleep(0.5)
                            
                            # Advance to next video
                            if not self._play_next_video():
                                logger.warning("Failed to advance to next video, stopping monitoring")
                                self._monitoring_active = False
                                break
                        else:
                            # Monitoring was stopped or not a channel source
                            break
                
                # Sleep before next check
                time.sleep(1.5)  # Check every 1.5 seconds
                
            except Exception as e:
                logger.error(f"Error in playback monitoring thread: {e}")
                # Continue monitoring despite errors
                time.sleep(2.0)
    
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
        play_start = time.perf_counter()
        try:
            source_type = kwargs.get('source_type', 'youtube_channel')
            
            if source_type == 'youtube_channel':
                channel_id = kwargs.get('channel_id') or source_id
                self._current_channel_id = channel_id
                
                # Start pulsing beep to indicate loading (50% volume, 3s tail)
                self._pulsing_beep = PulsingBeep(frequency=300.0, pulse_duration=0.3, pause_duration=0.3, volume=0.5, tail_duration=3.0)
                self._pulsing_beep.start()
                logger.info("Started pulsing beep for YouTube channel loading")
                
                try:
                    # Get video list from RSS feed
                    rss_start = time.perf_counter()
                    if not self._video_queue or (time.time() - self._last_rss_refresh) > self._rss_refresh_interval:
                        self._video_queue = self._get_video_list_from_rss(channel_id, limit=20)
                        self._last_rss_refresh = time.time()
                        if not self._video_queue:
                            self._pulsing_beep._force_stop()
                            self._pulsing_beep = None
                            play_not_found_beep()
                            raise BackendError(f"Could not get videos from RSS feed for channel {channel_id}")
                    
                    rss_time = time.perf_counter() - rss_start
                    
                    # Start with latest video (index 0)
                    self._current_video_index = 0
                    if not self._video_queue:
                        self._pulsing_beep._force_stop()
                        self._pulsing_beep = None
                        play_not_found_beep()
                        raise BackendError(f"No videos found for channel {channel_id}")
                    
                    latest_video = self._video_queue[0]
                    video_url = latest_video['url']
                    video_title = latest_video.get('title', 'YouTube Audio')
                    
                    # Start playback monitoring thread for auto-advance
                    self._monitoring_active = True
                    if self._monitoring_thread is None or not self._monitoring_thread.is_alive():
                        self._monitoring_thread = threading.Thread(
                            target=self._monitor_playback,
                            daemon=True
                        )
                        self._monitoring_thread.start()
                        logger.info("Started playback monitoring thread for auto-advance")
                    
                    playback_start = time.perf_counter()
                    self._start_playback(video_url, video_title)
                    playback_time = time.perf_counter() - playback_start
                    
                    # Don't stop beep here - let _start_playback detection thread handle it
                    # The detection thread will stop it after confirming playback started
                    
                    total_time = time.perf_counter() - play_start
                    logger.info(f"[BENCHMARK] YouTubeBackend.play: total={total_time*1000:.2f}ms | "
                               f"rss={rss_time*1000:.2f}ms | playback={playback_time*1000:.2f}ms")
                    return True
                except Exception as e:
                    # Force stop pulsing beep on error
                    if self._pulsing_beep:
                        self._pulsing_beep._force_stop()
                        self._pulsing_beep = None
                    raise
                
            elif source_type == 'youtube_playlist':
                playlist_id = kwargs.get('playlist_id') or source_id
                self._current_playlist_id = playlist_id
                
                # For playlists, still use yt-dlp (playlists don't have easy RSS access)
                playlist_start = time.perf_counter()
                url = self._get_playlist_url(playlist_id)
                playlist_time = time.perf_counter() - playlist_start
                
                if not url:
                    play_not_found_beep()
                    raise BackendError(f"Could not get URL for playlist {playlist_id}")
                
                # Note: yt-dlp is still required for playlists
                # mpv can handle YouTube URLs directly, so we pass the URL as-is
                playback_start = time.perf_counter()
                self._start_playback(url, "YouTube Playlist")
                playback_time = time.perf_counter() - playback_start
                
                total_time = time.perf_counter() - play_start
                logger.info(f"[BENCHMARK] YouTubeBackend.play (playlist): total={total_time*1000:.2f}ms | "
                           f"playlist={playlist_time*1000:.2f}ms | playback={playback_time*1000:.2f}ms")
                return True
            else:
                raise BackendError(f"Unknown source type: {source_type}")
                
        except BackendError:
            # BackendError already has appropriate sound feedback
            self.set_playing_state(False)
            raise
        except Exception as e:
            # Check if it's a network-related error
            error_str = str(e).lower()
            error_type = type(e).__name__.lower()
            
            if any(keyword in error_str or keyword in error_type for keyword in 
                   ['network', 'connection', 'timeout', 'dns', 'socket', 'urlerror']):
                play_network_error_beep()
            else:
                # For other errors, play connection error
                play_connection_error_beep()
            
            logger.error(f"Error in play(): {e}")
            self.set_playing_state(False)
            raise BackendError(f"Failed to start playback: {e}")
    
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
            # Stop monitoring thread
            self._monitoring_active = False
            
            # Force stop pulsing beep if active
            if self._pulsing_beep:
                self._pulsing_beep._force_stop()
                self._pulsing_beep = None
            
            if self._mpv_process:
                if self._mpv_process.poll() is None:
                    self._mpv_process.terminate()
                    try:
                        self._mpv_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._mpv_process.kill()
                        self._mpv_process.wait()
                
                self._mpv_process = None
            
            # Clear video queue and reset index
            self._video_queue = []
            self._current_video_index = 0
            
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

