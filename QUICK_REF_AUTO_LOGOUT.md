# Quick Reference: Auto-Logout on Server Restart

## What It Does
✅ Automatically logs out ALL users when server restarts  
✅ Clears all sessions from database on startup  
✅ Shows security message in console  

## When It Activates
- Server restart (manual: python manage.py runserver)
- Server crash recovery
- System reboot
- Deployment/updates
- Any time Django app initializes

## What Users See
1. Server restarts
2. User refreshes browser
3. → Redirected to login page
4. → Must login again

## Console Message
```
======================================================================
[SECURITY] Server restart detected
[SECURITY] Cleared X session(s) - All users logged out
======================================================================
```

## Files Modified
- `attendance/apps.py` - Added session cleanup logic

## Testing
```bash
# Start server
python manage.py runserver

# Login in browser
# Stop server (Ctrl+C)
# Start server again
# → See security message in console

# Refresh browser
# → Should be at login page
```

## Disable (if needed)
Edit `attendance/apps.py`:
```python
def ready(self):
    import attendance.signals
    # Comment out this line to disable:
    # self.clear_all_sessions_on_startup()
```

## Combined Security Features
1. ✅ Single session per account (login blocked if already logged in)
2. ✅ Auto-logout on server restart (this feature)
3. ✅ 24-hour session expiry

## Status
✅ ACTIVE and OPERATIONAL
