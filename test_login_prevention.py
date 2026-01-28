"""
Test the updated single session security feature
This version PREVENTS login when account is already active on another device
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib.auth.models import User

print("\n" + "=" * 70)
print("SINGLE SESSION SECURITY - UPDATED BEHAVIOR TEST")
print("=" * 70)
print("\nNEW BEHAVIOR: Login is BLOCKED if account is already active")
print("   Message shown: 'Your account is open on another device'")
print("\n" + "=" * 70)

# Display current sessions
total_sessions = Session.objects.filter(expire_date__gte=timezone.now()).count()
print(f"\nCurrent System Status:")
print(f"   Total active sessions: {total_sessions}")

# Count users with multiple sessions
user_sessions = {}
active_sessions = Session.objects.filter(expire_date__gte=timezone.now())

for session in active_sessions:
    try:
        session_data = session.get_decoded()
        user_id = session_data.get('_auth_user_id')
        if user_id:
            user_sessions[user_id] = user_sessions.get(user_id, 0) + 1
    except:
        pass

users_with_multiple = sum(1 for count in user_sessions.values() if count > 1)
print(f"   Users with multiple sessions: {users_with_multiple}")

if users_with_multiple > 0:
    print(f"\n[!] {users_with_multiple} user(s) currently have multiple sessions")
    print("   These users will NOT be able to login again until they logout")
    print("   from their existing sessions.")
    
    print("\n   Users affected:")
    for user_id, count in user_sessions.items():
        if count > 1:
            try:
                user = User.objects.get(id=user_id)
                print(f"   - {user.username}: {count} active session(s)")
            except User.DoesNotExist:
                pass

print("\n" + "=" * 70)
print("HOW IT WORKS NOW:")
print("=" * 70)
print("""
1. User logs in on Computer A
   -> Login succeeds (OK)
   -> Session created

2. Same user tries to login on Computer B
   -> Login is BLOCKED (DENIED)
   -> Message: "Your account is open on another device"
   -> User must logout from Computer A first

3. User logs out from Computer A
   -> Session ended

4. User tries to login on Computer B again
   -> Login succeeds (OK)
   -> New session created
""")

print("=" * 70)
print("TESTING INSTRUCTIONS:")
print("=" * 70)
print("""
To test this feature:

1. Open Chrome browser
   - Go to the login page
   - Login with any account
   - You should see "Welcome [name]!" message

2. Open Firefox browser (or another Chrome window)
   - Go to the login page
   - Try to login with the SAME account
   - You should see: "Your account is open on another device"
   - Login should be prevented

3. Return to Chrome
   - Logout from the account

4. Return to Firefox
   - Try to login again
   - Login should now succeed

This confirms the security feature is working correctly!
""")
print("=" * 70 + "\n")
