# Rodrigo Radio TUI Monitor - Project Plan

## Overview

A Text User Interface (TUI) application to remotely monitor and interact with the Rodrigo Radio music player service running on a Raspberry Pi. The TUI will provide real-time visibility into what grandfather is listening to, system health, and historical listening patterns.**Target User**: Family members monitoring the radio remotely (via SSH or local terminal)**Primary Goals**:

1. Real-time visibility into playback status
2. Historical listening activity and patterns
3. System health monitoring
4. Optional remote control capabilities

---

## Technology Stack

### Recommended: Textual Framework

**Why Textual?**

- Modern Python TUI framework built on Rich
- Beautiful default styling with CSS-like customization
- Built-in async support (perfect for polling Supabase)
- Rich widget library (DataTable, ProgressBar, Tabs, etc.)
- Works over SSH (important for remote monitoring)
- Active development and good documentation

**Dependencies**:

```javascript
textual>=0.45.0
rich>=13.0.0
supabase>=2.0.0  # Already in project
python-dotenv>=1.0.0  # Already in project
```



### Alternative Options (if needed)

- **Rich only**: Simpler, good for basic live displays
- **urwid**: More mature, steeper learning curve
- **blessed/curses**: Lower level, more control

---

## Project Structure

```javascript
rodrigo_radio/
├── tui/
│   ├── __init__.py
│   ├── app.py              # Main Textual application
│   ├── config.py           # TUI configuration
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── dashboard.py    # Main dashboard screen
│   │   ├── history.py      # History browser screen
│   │   ├── stats.py        # Statistics screen
│   │   └── settings.py     # Settings/config viewer
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── now_playing.py  # Now playing panel
│   │   ├── activity_feed.py # Live event feed
│   │   ├── source_list.py  # Source browser
│   │   ├── volume_bar.py   # Volume indicator
│   │   ├── stats_panel.py  # Statistics widgets
│   │   └── health_panel.py # System health indicators
│   ├── services/
│   │   ├── __init__.py
│   │   ├── supabase_client.py  # Supabase data fetching
│   │   ├── player_status.py    # Local player status
│   │   └── stats_calculator.py # Statistics aggregation
│   └── styles/
│       └── app.tcss        # Textual CSS styles
├── tui_monitor.py          # Entry point script
└── requirements-tui.txt    # TUI-specific dependencies
```

---

## Phase 1: Foundation & Core Infrastructure

**Estimated Effort**: 2-3 sessions**Priority**: 🔴 Critical

### 1.1 Project Setup

- [ ] Create `tui/` directory structure
- [ ] Create `requirements-tui.txt` with Textual dependencies
- [ ] Create `tui_monitor.py` entry point script
- [ ] Create basic `tui/app.py` with empty Textual app
- [ ] Verify Textual installation and basic app runs

### 1.2 Supabase Service Layer

- [ ] Create `tui/services/supabase_client.py`
- [ ] Implement `get_recent_events(limit)` - fetch recent event_logs
- [ ] Implement `get_events_since(timestamp)` - for real-time polling
- [ ] Implement `get_events_by_type(event_type, limit)` - filtered queries
- [ ] Implement `get_events_in_range(start, end)` - date range queries
- [ ] Add connection error handling and retry logic
- [ ] Add caching layer to reduce API calls

### 1.3 Local Player Status Service

- [ ] Create `tui/services/player_status.py`
- [ ] Implement `get_current_source()` - read from state.json
- [ ] Implement `get_sources_list()` - read from sources.json
- [ ] Implement `get_playback_status()` - check backend status (if accessible)
- [ ] Handle cases where player is not running

### 1.4 Configuration

- [ ] Create `tui/config.py`
- [ ] Define refresh intervals (events, status, stats)
- [ ] Define color schemes for event types
- [ ] Define keyboard shortcuts
- [ ] Load from environment or config file

**Deliverable**: Basic TUI app that can connect to Supabase and fetch events---

## Phase 2: Main Dashboard - Status Display

**Estimated Effort**: 2-3 sessions**Priority**: 🔴 Critical**Depends on**: Phase 1

### 2.1 Now Playing Widget

- [ ] Create `tui/widgets/now_playing.py`
- [ ] Display current source name and type (Spotify/YouTube icon)
- [ ] Display current track name
- [ ] Display artist (if available)
- [ ] Display playback state (Playing/Paused/Stopped indicator)
- [ ] Add progress bar with position/duration (for Spotify)
- [ ] Handle missing/unavailable data gracefully

### 2.2 Volume Display Widget

- [ ] Create `tui/widgets/volume_bar.py`
- [ ] Display current volume percentage as visual bar
- [ ] Display time-based limit mode (Day/Evening/Night)
- [ ] Show effective dB offset
- [ ] Color code based on volume level

### 2.3 Source List Widget

- [ ] Create `tui/widgets/source_list.py`
- [ ] Display all configured sources
- [ ] Highlight current source
- [ ] Show source type icons (🎵 Spotify, 📺 YouTube)
- [ ] Make sources selectable (for future remote control)

### 2.4 Dashboard Layout

- [ ] Create `tui/screens/dashboard.py`
- [ ] Implement responsive grid layout
- [ ] Arrange: Now Playing (top-left), Sources (bottom-left)
- [ ] Reserve space for Activity Feed (right side)
- [ ] Add header with app title and connection status
- [ ] Add footer with keyboard shortcuts

### 2.5 Styles

- [ ] Create `tui/styles/app.tcss`
- [ ] Define color palette (consider dark terminal themes)
- [ ] Style each widget container
- [ ] Add hover/focus states for interactive elements

**Deliverable**: Dashboard showing current playback status from state files---

## Phase 3: Real-Time Activity Feed

**Estimated Effort**: 2 sessions**Priority**: 🔴 Critical**Depends on**: Phase 1, Phase 2

### 3.1 Activity Feed Widget

- [ ] Create `tui/widgets/activity_feed.py`
- [ ] Display scrollable list of recent events
- [ ] Auto-scroll to newest events
- [ ] Format timestamps in human-readable format
- [ ] Color-code by event type:
- 🟢 Green: playback_start, source_change
- 🟡 Yellow: user_input (button presses)
- 🔵 Blue: audio (volume changes)
- 🔴 Red: network errors, failures
- ⚪ Gray: system events

### 3.2 Event Formatting

- [ ] Create event type to display text mapping
- [ ] Format playback_start: "▶ Track: {item_name}"
- [ ] Format source_change: "🔄 Source → {source_label}"
- [ ] Format user_input: "🎛 {action}" (button_play_pause → ⏯)
- [ ] Format volume: "🔊 Volume: {value}%"
- [ ] Format errors: "❌ {error_message}"

### 3.3 Real-Time Polling

- [ ] Implement async polling loop in dashboard
- [ ] Poll Supabase every 2-5 seconds for new events
- [ ] Use `get_events_since(last_timestamp)` to fetch only new events
- [ ] Append new events to feed widget
- [ ] Limit feed to last N events (e.g., 100) for performance

### 3.4 Connection Status Indicator

- [ ] Add connection status to header
- [ ] Show 🟢 Connected / 🔴 Disconnected / 🟡 Reconnecting
- [ ] Update based on Supabase poll success/failure
- [ ] Show last successful update timestamp

**Deliverable**: Live-updating activity feed showing events as they happen---

## Phase 4: Statistics & Analytics

**Estimated Effort**: 2-3 sessions**Priority**: 🟡 Medium**Depends on**: Phase 1, Phase 3

### 4.1 Statistics Calculator Service

- [ ] Create `tui/services/stats_calculator.py`
- [ ] Implement `get_listening_time_today()` - calculate from playback events
- [ ] Implement `get_source_distribution(period)` - percentage per source
- [ ] Implement `get_track_count(period)` - unique tracks played
- [ ] Implement `get_interaction_count(period)` - button presses
- [ ] Implement `get_activity_by_hour()` - for activity heatmap
- [ ] Implement `get_most_played_sources(limit)` - top sources
- [ ] Cache results with TTL to avoid excessive queries

### 4.2 Stats Panel Widget

- [ ] Create `tui/widgets/stats_panel.py`
- [ ] Display "Today's Stats" summary
- [ ] Show total listening time
- [ ] Show tracks played count
- [ ] Show source distribution (mini bar chart or percentages)
- [ ] Show interaction count

### 4.3 Statistics Screen

- [ ] Create `tui/screens/stats.py`
- [ ] Full-screen statistics view
- [ ] Period selector: Today / This Week / This Month / All Time
- [ ] Detailed source breakdown with time per source
- [ ] Activity heatmap by hour (text-based)
- [ ] Top tracks/sources list

### 4.4 Integrate Stats into Dashboard

- [ ] Add mini stats panel to dashboard layout
- [ ] Show key metrics: listening time, tracks played
- [ ] Link to full stats screen (keyboard shortcut)

**Deliverable**: Statistics view with listening patterns and analytics---

## Phase 5: History Browser

**Estimated Effort**: 1-2 sessions**Priority**: 🟡 Medium**Depends on**: Phase 1, Phase 3

### 5.1 History Screen

- [ ] Create `tui/screens/history.py`
- [ ] Full-screen history browser
- [ ] DataTable widget with columns: Time, Event, Source, Details
- [ ] Sortable columns
- [ ] Pagination for large datasets

### 5.2 Filtering

- [ ] Add filter by event type (dropdown/toggle)
- [ ] Add filter by source
- [ ] Add filter by date range
- [ ] Add search/filter input for text search

### 5.3 Event Detail View

- [ ] Show detailed event info on selection
- [ ] Display all event fields (timestamp, action, source, item, etc.)
- [ ] Show raw JSON for debugging

**Deliverable**: Searchable, filterable history browser---

## Phase 6: System Health Monitoring

**Estimated Effort**: 1-2 sessions**Priority**: 🟡 Medium**Depends on**: Phase 1, Phase 2

### 6.1 Health Panel Widget

- [ ] Create `tui/widgets/health_panel.py`
- [ ] Display network connectivity status
- [ ] Display Supabase buffer status (pending events)
- [ ] Display last successful sync timestamp
- [ ] Display error count in last hour

### 6.2 Service Status (Local Only)

- [ ] Check if rodrigo_radio.service is running (systemctl)
- [ ] Check if raspotify.service is running
- [ ] Display service uptime
- [ ] Note: Only works when TUI runs on same machine

### 6.3 Alerts/Warnings

- [ ] Highlight if no events in last X minutes (configurable)
- [ ] Highlight network connectivity issues
- [ ] Highlight if Spotify token might need refresh
- [ ] Show count of errors in activity feed

**Deliverable**: Health monitoring panel showing system status---

## Phase 7: Remote Control (Optional)

**Estimated Effort**: 2-3 sessions**Priority**: 🟢 Low (Nice to Have)**Depends on**: Phase 2

### 7.1 Control Service

- [ ] Create `tui/services/remote_control.py`
- [ ] Implement source change via state.json modification
- [ ] Consider: Direct backend control vs state file approach
- [ ] Add confirmation dialogs for destructive actions

### 7.2 Control Widgets

- [ ] Add play/pause button (if controllable)
- [ ] Add next/previous buttons
- [ ] Add volume adjustment (if safe to implement)
- [ ] Add source selector with change action

### 7.3 Safety Considerations

- [ ] Add confirmation before source changes
- [ ] Rate limit control actions
- [ ] Log all remote control actions
- [ ] Consider read-only mode by default

**Deliverable**: Optional remote control capabilities---

## Phase 8: Polish & Enhancements

**Estimated Effort**: 1-2 sessions**Priority**: 🟢 Low**Depends on**: All previous phases

### 8.1 User Experience

- [ ] Add loading spinners during data fetch
- [ ] Add error messages/toasts for failures
- [ ] Add keyboard shortcut help screen
- [ ] Add smooth transitions between screens

### 8.2 Configuration Screen

- [ ] Create `tui/screens/settings.py`
- [ ] View current configuration
- [ ] View source list details
- [ ] View volume limit schedule

### 8.3 Performance Optimization

- [ ] Profile and optimize Supabase queries
- [ ] Implement smarter caching
- [ ] Reduce unnecessary re-renders
- [ ] Optimize for low-power devices (Pi Zero, etc.)

### 8.4 Documentation

- [ ] Add README for TUI usage
- [ ] Document keyboard shortcuts
- [ ] Document configuration options
- [ ] Add troubleshooting guide

**Deliverable**: Polished, production-ready TUI---

## Keyboard Shortcuts Reference

| Key | Action ||-----|--------|| `q` | Quit application || `r` | Force refresh || `d` | Dashboard screen || `h` | History screen || `s` | Statistics screen || `?` | Help/shortcuts || `↑/↓` | Navigate lists || `Enter` | Select/activate || `Esc` | Back/cancel |---

## Data Flow Architecture

```javascript
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Supabase      │     │  Local Files    │     │  TUI App        │
│   (event_logs)  │────▶│  (state.json,   │────▶│  (Textual)      │
│                 │     │   sources.json) │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        │   Poll every 2-5s     │   Watch for changes   │
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Services Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ supabase_    │  │ player_      │  │ stats_       │          │
│  │ client.py    │  │ status.py    │  │ calculator.py│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Widgets Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ now_playing  │  │ activity_    │  │ stats_panel  │          │
│  │              │  │ feed         │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Screens Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ dashboard    │  │ history      │  │ stats        │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Milestones & Checkpoints

### Milestone 1: "It Works" ✅

- Basic TUI launches
- Can fetch events from Supabase
- Shows something on screen

### Milestone 2: "Useful Dashboard" ✅

- Now playing shows current track
- Activity feed shows recent events
- Real-time updates working

### Milestone 3: "Full Monitor" ✅

- Statistics available
- History browsable
- Health monitoring works

### Milestone 4: "Production Ready" ✅

- Polished UI
- Error handling complete
- Documentation written

---

## Notes & Considerations

### Running Locally vs Remotely

- **Local (on Pi)**: Can access state files, check services, potential control
- **Remote (SSH)**: Supabase data only, no local file access, read-only

### Performance on Raspberry Pi

- Textual is relatively lightweight but test on target hardware
- Consider reduced refresh rates for Pi Zero
- Cache aggressively to reduce CPU/network usage

### Timezone Handling

- Events stored with UTC + local timestamp (Asia/Manila)
- Display in local time for the user
- Consider making timezone configurable

### Future Enhancements

- Web-based dashboard (could reuse services layer)
- Mobile notifications for alerts
- Integration with Home Assistant
- Voice status announcements