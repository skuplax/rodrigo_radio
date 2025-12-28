# Suggested Logs to Remove

Based on database analysis and code review, here are logs that should be removed to keep only:
- **ERROR and WARNING logs from the system**
- **All user input logs**

## High Priority - Remove These Logs (Most Verbose)

### 1. Volume Change Logs (INFO) - ~42,000+ entries
These are routine volume adjustments that aren't user input or errors:
- `volume_set` (INFO) - 14,663 entries
- `core.player_controller._on_volume_change` (INFO) - 14,026 entries  
- `hardware.rotary_encoder.set_volume` (INFO) - 14,024 entries
- `root.increment` (WARNING) - 22,536 entries (rotary encoder volume changes)

**Action**: Remove all INFO-level volume logs. Keep only:
- Volume mute/unmute events (user input)
- Volume errors (ERROR level)

### 2. HTTP Request Logs (INFO) - ~14,000 entries
- `httpx._send_single_request` (INFO) - 14,298 entries

**Action**: Remove all httpx internal request logs. These are routine API calls, not errors.

### 3. Routine System Operation Logs (INFO) - ~20,000+ entries
These are normal successful operations, not errors or user input:
- `backends.spotify_backend.stop` (INFO) - 4,031 entries
- `backends.spotify_backend.play` (INFO) - 3,966 entries
- `backends.spotify_backend._find_raspotify_device` (INFO) - 3,405 entries
- `backends.youtube_backend.play` (INFO) - 3,340 entries
- `hardware.buttons.wrapped_callback` (INFO) - 3,330 entries
- `backends.youtube_backend.stop` (INFO) - 3,028 entries
- `backends.youtube_backend._get_video_list_from_rss` (INFO) - 2,619 entries
- `core.player_controller._play_source_with_retry` (INFO) - 5,263 entries
- `core.player_controller._on_cycle_source` (INFO) - 6,119 entries
- `core.sources.cycle_source` (INFO) - 2,121 entries
- `core.player_controller._switch_source` (INFO) - 1,051 entries
- `backends.spotify_backend._ensure_device_active` (INFO) - 1,307 entries
- `backends.spotify_backend._start_monitoring` (INFO) - 807 entries
- `backends.spotify_backend._stop_monitoring` (INFO) - 794 entries
- `backends.youtube_backend._play_next_video` (INFO) - 663 entries
- `backends.spotify_backend._start_raspotify_service` (INFO) - 563 entries
- `core.player_controller.monitor_state` (INFO) - 531 entries
- `backends.spotify_backend._restart_raspotify_service` (INFO) - 497 entries
- `backends.spotify_backend._ensure_device` (INFO) - 320 entries
- `hardware.buttons._setup_buttons` (INFO) - 272 entries
- `core.player_controller._on_next` (INFO) - 268 entries

**Action**: Remove all INFO-level logs for routine successful operations. Keep only:
- Errors (ERROR level)
- Warnings (WARNING level)
- User input events (button presses, source changes initiated by user)

### 4. Playback History/State Logs (INFO) - ~3,000+ entries
- `playback_start` (INFO) - 2,202 entries
- `source_change` (INFO) - 1,807 entries
- `connection_success` (INFO) - 1,807 entries
- `utils.announcements.announce_source` (INFO) - 2,186 entries

**Action**: Remove INFO-level playback state logs. Keep only errors/warnings.

### 5. Sound Feedback Logs (INFO) - ~2,700 entries
- `utils.sound_feedback.start` (INFO) - 1,392 entries
- `utils.sound_feedback._force_stop` (INFO) - 1,376 entries

**Action**: Remove sound feedback INFO logs. These are routine audio feedback operations.

### 6. Retry/Background Operation Logs (INFO) - ~800 entries
- `core.player_controller.retry_in_background` (INFO) - 812 entries
- `backends.spotify_backend._restart_raspotify_service` (network INFO) - 385 entries

**Action**: Remove routine retry INFO logs. Keep only WARNING/ERROR logs for retries.

## Keep These Logs (User Input & Errors/Warnings)

### User Input Logs (KEEP ALL)
- `button_cycle_source` (INFO) - 2,211 entries ✅ KEEP
- Button press logs (user-initiated actions) ✅ KEEP
- Rotary encoder switch press (mute toggle) ✅ KEEP

### Error Logs (KEEP ALL)
- `spotipy.client._internal_call` (ERROR) - 6,237 entries ✅ KEEP
- `backends.spotify_backend.stop` (ERROR) - 1,374 entries ✅ KEEP
- `backends.spotify_backend._api_call_with_retry` (ERROR) - 1,288 entries ✅ KEEP
- `core.player_controller._on_play_pause` (ERROR) - 476 entries ✅ KEEP
- `core.player_controller._play_source_with_retry` (ERROR) - 301 entries ✅ KEEP
- `connection_failure` (ERROR) - 301 entries ✅ KEEP
- All other ERROR level logs ✅ KEEP

### Warning Logs (KEEP ALL)
- `backends.spotify_backend._find_raspotify_device` (WARNING) - 3,053 entries ✅ KEEP
- `backends.spotify_backend.stop` (WARNING) - 1,403 entries ✅ KEEP
- `backends.spotify_backend._ensure_device_active` (WARNING) - 1,270 entries ✅ KEEP
- `backends.spotify_backend.play` (WARNING) - 1,201 entries ✅ KEEP
- `core.player_controller._play_source_with_retry` (WARNING) - 769 entries ✅ KEEP
- `retry_attempt` (WARNING) - 471 entries ✅ KEEP
- `backends.spotify_backend._start_raspotify_service` (WARNING) - 267 entries ✅ KEEP
- All other WARNING level logs ✅ KEEP

## Summary

**Remove:**
- All INFO-level logs except user input
- All DEBUG-level logs
- Volume change logs (unless mute/unmute user action)
- HTTP request logs (httpx)
- Routine successful operation logs
- Playback state change logs (unless errors)
- Sound feedback logs

**Keep:**
- All ERROR logs
- All WARNING logs  
- All user input logs (button presses, source changes, mute toggles)
- User-initiated volume changes (if we can distinguish them from automatic ones)

## Implementation Notes

1. **Volume Logging**: Currently all volume changes are logged. We should:
   - Remove automatic volume adjustment logs
   - Keep mute/unmute toggle logs (user input via rotary encoder switch)
   - Keep volume errors

2. **Button Logs**: 
   - Keep `button_cycle_source` and other user button press logs
   - Remove `hardware.buttons.wrapped_callback` INFO logs (internal callback wrapper)
   - Keep button callback errors

3. **Backend Operation Logs**:
   - Remove all INFO logs for play/stop operations
   - Keep ERROR and WARNING logs for failed operations
   - Keep user-initiated source changes

4. **Network Logs**:
   - Remove `connection_success` INFO logs
   - Keep `connection_failure` ERROR logs
   - Keep retry WARNING logs

5. **Filter in `_should_filter_log` method**:
   - Add filtering for volume change logs (INFO level)
   - Add filtering for httpx logs
   - Add filtering for routine operation logs based on action/logger name
   - Ensure user input logs are never filtered

## Implementation Status

✅ **COMPLETED**: Updated `core/supabase_log_handler.py` with comprehensive filtering:

### What Was Implemented:

1. **Filter Logic** (in `_should_filter_log` method):
   - ✅ Filters all DEBUG logs
   - ✅ Filters all INFO logs except user input
   - ✅ Keeps all ERROR logs
   - ✅ Keeps all WARNING logs (except routine volume increments)
   - ✅ Filters httpx internal request logs
   - ✅ Filters volume change logs (INFO level, except mute toggles)
   - ✅ Filters routine system operation logs (play/stop/monitoring/etc.)
   - ✅ Filters sound feedback logs
   - ✅ Filters initialization/setup logs
   - ✅ Filters routine status logs
   - ✅ Identifies and keeps user input logs (button presses, encoder actions)

2. **User Input Detection**:
   - Detects button press logs by message content
   - Detects encoder switch presses (mute toggle)
   - Detects button callback invocations
   - Excludes setup/configuration messages from user input

3. **Volume Logging**:
   - Filters routine volume change logs (INFO level)
   - Keeps mute/unmute toggle logs (user input)
   - Keeps volume-related errors and warnings

### Expected Results:

After this implementation, the logging system will:
- **Reduce log volume by ~90%** (from ~100,000+ entries to ~10,000-15,000 entries)
- **Keep all error and warning logs** for debugging
- **Keep all user input logs** for tracking user interactions
- **Remove routine operation logs** that don't provide value

### Next Steps:

1. Monitor the logs after deployment to verify filtering is working correctly
2. Adjust filter rules if any important logs are being filtered out
3. Consider cleaning up existing historical logs in the database (optional)



