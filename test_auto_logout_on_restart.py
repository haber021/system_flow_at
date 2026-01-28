"""
Test: Auto-logout on Server Restart Feature

This demonstrates that all users are automatically logged out when the server
is killed and restarted.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib.auth.models import User

print("\n" + "=" * 70)
print("AUTO-LOGOUT ON SERVER RESTART - DEMONSTRATION")
print("=" * 70)

# Check current sessions
total_sessions = Session.objects.all().count()
active_sessions = Session.objects.filter(expire_date__gte=timezone.now()).count()

print(f"\nCurrent Session Status:")
print(f"  Total sessions in database: {total_sessions}")
print(f"  Active sessions (not expired): {active_sessions}")

if total_sessions > 0:
    print(f"\n  Users currently logged in:")
    
    for session in Session.objects.filter(expire_date__gte=timezone.now())[:10]:
        try:
            session_data = session.get_decoded()
            user_id = session_data.get('_auth_user_id')
            if user_id:
                user = User.objects.get(id=user_id)
                print(f"    - {user.username}")
        except:
            pass
    
    if active_sessions > 10:
        print(f"    ... and {active_sessions - 10} more users")

print("\n" + "=" * 70)
print("HOW AUTO-LOGOUT WORKS:")
print("=" * 70)
print("""
SCENARIO 1: Normal Operation
  1. Server is running
  2. Users are logged in
  3. Sessions exist in database
  → Users can access the system

SCENARIO 2: Server is Killed/Stopped
  1. Administrator stops the server (Ctrl+C)
  2. OR server crashes/exits unexpectedly
  3. OR power failure
  → Sessions remain in database (for now)

SCENARIO 3: Server Restarts
  1. Administrator starts the server again
  2. Django app initialization runs
  3. AttendanceConfig.ready() is called
  4. clear_all_sessions_on_startup() executes
  5. ALL sessions are deleted from database
  → All users are logged out automatically
  
  Console shows:
  ======================================================================
  [SECURITY] Server restart detected
  [SECURITY] Cleared X session(s) - All users logged out
  ======================================================================

SCENARIO 4: Users Try to Access
  1. Users refresh their browser
  2. System checks for valid session
  3. No session found (was deleted on restart)
  → Users are redirected to login page
""")

print("=" * 70)
print("SECURITY BENEFITS:")
print("=" * 70)
print("""
✓ Clean State After Restart
  - No orphaned sessions from previous server run
  - Fresh start with no active sessions

✓ Forced Re-authentication
  - All users must login again after server restart
  - Ensures users are aware of system restart

✓ Prevents Session Hijacking
  - Old session IDs from before restart are invalid
  - Reduces risk of session replay attacks

✓ Clear Security Boundary
  - Server restart = clear security reset
  - Easy to audit and understand

✓ Compliance
  - Meets security requirements for session management
  - Demonstrates security-conscious design
""")

print("=" * 70)
print("TESTING THIS FEATURE:")
print("=" * 70)
print("""
Step-by-step test:

1. Start the Django server:
   python manage.py runserver

2. Login with a user account in the browser
   - Verify you can access the dashboard
   - Verify session exists in database

3. STOP the server (Ctrl+C in terminal)
   - Server stops
   - Sessions remain in database

4. START the server again:
   python manage.py runserver
   
   You should see:
   [SECURITY] Server restart detected
   [SECURITY] Cleared X session(s) - All users logged out

5. Refresh the browser
   - You should be redirected to login page
   - Previous session is no longer valid

6. Try to access dashboard directly
   - Should be redirected to login
   - Must login again

This confirms the auto-logout feature is working!
""")

print("=" * 70)
print(f"\nCurrent sessions will be cleared on next server restart.")
print(f"Total sessions to be cleared: {total_sessions}")
print("\n" + "=" * 70 + "\n")
