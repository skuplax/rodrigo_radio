# Testing GPIO Buttons

## Quick Test (Service Running)

Monitor the service logs to see button presses:

```bash
sudo journalctl -u music-player.service -f
```

Press each button and watch for log entries.

## Standalone Test (Service Stopped)

1. **Stop the service temporarily:**
   ```bash
   sudo systemctl stop music-player.service
   ```

2. **Run the test script:**
   ```bash
   python3 /home/skayflakes/music-player/test_buttons.py
   ```

3. **Press each button** - you should see output like:
   ```
   ✓ play_pause button PRESSED!
   ✓ previous button PRESSED!
   ```

4. **Restart the service when done:**
   ```bash
   sudo systemctl start music-player.service
   ```

## Troubleshooting

If buttons don't work:
- Check wiring (GPIO pin → Button → GND)
- Verify pins: 17, 27, 22, 23
- Check if another process is using GPIO: `sudo lsof | grep gpio`
- Test with multimeter to verify button continuity

