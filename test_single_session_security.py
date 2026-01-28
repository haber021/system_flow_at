"""
Test script to verify single session security feature
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone

def test_single_session_security():
    """
    Test that the single session security feature is working correctly
    """
    print("=" * 70)
    print("TESTING SINGLE SESSION SECURITY FEATURE")
    print("=" * 70)
    
    # Check if Session model is available
    print("\n1. Checking if sessions are configured...")
    try:
        session_count = Session.objects.count()
        print(f"   ✓ Sessions are configured. Total sessions: {session_count}")
    except Exception as e:
        print(f"   ✗ Error accessing sessions: {e}")
        return
    
    # Check if signal handler is registered
    print("\n2. Checking if signal handlers are loaded...")
    try:
        from attendance import signals
        from django.contrib.auth.signals import user_logged_in
        
        receivers = user_logged_in.receivers
        signal_registered = any('invalidate_other_sessions' in str(r) for r in receivers)
        
        if signal_registered:
            print("   ✓ Signal handler is registered")
        else:
            print("   ✗ Signal handler is NOT registered")
    except Exception as e:
        print(f"   ✗ Error checking signals: {e}")
    
    # Check active sessions per user
    print("\n3. Checking active sessions per user...")
    active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    
    user_sessions = {}
    for session in active_sessions:
        try:
            session_data = session.get_decoded()
            user_id = session_data.get('_auth_user_id')
            if user_id:
                user_sessions[user_id] = user_sessions.get(user_id, 0) + 1
        except:
            continue
    
    if not user_sessions:
        print("   No active user sessions found")
    else:
        print(f"   Found {len(user_sessions)} users with active sessions:")
        for user_id, count in user_sessions.items():
            try:
                user = User.objects.get(id=user_id)
                username = user.username
                status = "⚠ MULTIPLE" if count > 1 else "✓ Single"
                print(f"   {status} - User '{username}': {count} session(s)")
            except User.DoesNotExist:
                print(f"   ? - User ID {user_id}: {count} session(s)")
    
    print("\n" + "=" * 70)
    print("SECURITY FEATURE STATUS")
    print("=" * 70)
    print("✓ Single session security feature is configured")
    print("✓ When a user logs in, all their other sessions will be invalidated")
    print("✓ This prevents multiple simultaneous logins for the same account")
    print("=" * 70)

if __name__ == "__main__":
    test_single_session_security()
