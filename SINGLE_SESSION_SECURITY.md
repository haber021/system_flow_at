# Single Session Security Feature

## Overview
This security feature prevents multiple simultaneous logins for the same user account. When a user tries to log in while already logged in on another device or browser, the login is **blocked** and they receive a message: **"Your account is open on another device. Please logout from the other device first."**

## How It Works

### 1. Login Prevention Mechanism
When a user attempts to log in, the system:
- Checks all active sessions in the database
- Determines if the user already has an active session
- **Blocks the new login** if an active session exists
- Shows error message: "Your account is open on another device"
- Allows login only after the user logs out from the other device

### 2. Implementation Details

**File: `attendance/views.py`**
- Modified `login_view` function to check for existing sessions
- Modified `student_login` function to check for existing sessions
- Authentication succeeds but login is prevented if session exists

**File: `attendance/signals.py`**
- Signal handler disabled (not needed for this approach)
- Kept for reference/future use

### 3. Affected Login Methods
This security feature applies to:
- **Admin/Adviser Login** (`login_view` in views.py)
  - Username/password authentication
  - Employee ID authentication
- **Student Login** (`student_login` in views.py)
  - RFID-based authentication
  - Auto-created user accounts

## User Experience

### What Users Will See:
1. **User A logs in on Computer 1** → ✅ Successfully logged in
2. **User A tries to log in on Computer 2** → ❌ Login blocked with message:
   - "Your account is open on another device. Please logout from the other device first."
3. **User A logs out on Computer 1** → Session ended
4. **User A logs in on Computer 2** → ✅ Successfully logged in

### Benefits:
- ✓ Enhanced security - prevents unauthorized concurrent sessions
- ✓ Prevents account abuse
- ✓ User is notified when account is in use
- ✓ Forces explicit logout from first device
- ✓ No accidental session termination

### Important Notes:
- Users will be logged out from previous devices automatically
- No warning is given when logging out from other devices
- Sessions are stored in the database (`django_session` table)
- Session expiry is set to 24 hours (configurable in settings.py)

## Technical Configuration

### Settings (in `core/settings.py`):
```python
# Session Configuration
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
```

### Database:
- Sessions are stored in the `django_session` table
- Django's built-in session framework is used
- Sessions are automatically cleaned up on expiry

## Testing

### Manual Test:
1. Open Browser 1 (e.g., Chrome)
2. Log in with any account → ✅ Login succeeds
3. Open Browser 2 (e.g., Firefox) 
4. Try to log in with the same account → ❌ Login blocked
5. See message: "Your account is open on another device"
6. Go back to Browser 1 and logout
7. Return to Browser 2 and login → ✅ Login succeeds

### Automated Test:
Run the verification script:
```bash
python test_single_session_security.py
```

This will check:
- Session configuration
- Signal handler registration
- Current active sessions per user

## Security Considerations

### Advantages:
- Prevents session hijacking across multiple devices
- Reduces risk of unauthorized access
- Ensures accountability (only one active location per user)

### Limitations:
- Users cannot be logged in on multiple devices simultaneously
- May inconvenience users who switch devices frequently
- Requires database access for session management

## Troubleshooting

### Issue: Sessions not being invalidated
**Check:**
1. Verify signal handler is registered:
   ```bash
   python manage.py shell -c "from django.contrib.auth.signals import user_logged_in; print([str(r) for r in user_logged_in.receivers])"
   ```
2. Ensure `attendance.signals` is being imported in `attendance/apps.py`
3. Check database has the `django_session` table

### Issue: Users getting logged out unexpectedly
**Possible Causes:**
1. Session expiry (24 hours by default)
2. Database session cleanup
3. Another user logging in with the same credentials

### Issue: Signal not firing
**Solution:**
1. Restart the Django development server
2. Verify `INSTALLED_APPS` includes `'attendance'` in settings.py
3. Check that `attendance.apps.AttendanceConfig` is the correct app config

## Future Enhancements

Potential improvements:
- Add notification when user is logged out from another device
- Allow configurable number of concurrent sessions per user
- Add session management dashboard for admins
- Log session invalidation events for audit trail
- Provide option to view and manually terminate active sessions

## Related Files
- `attendance/signals.py` - Signal handlers
- `attendance/apps.py` - App configuration
- `attendance/views.py` - Login views (login_view, student_login)
- `core/settings.py` - Session configuration
- `core/middleware.py` - Custom session middleware
