"""
Simple demonstration of the single session security feature

This script simulates two login attempts from the same user and shows
how the first session is automatically invalidated.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import RequestFactory
from django.contrib.auth import login
from django.utils import timezone


def simulate_single_session_security():
    """
    Simulate the single session security feature
    """
    print("\n" + "=" * 70)
    print("SINGLE SESSION SECURITY - DEMONSTRATION")
    print("=" * 70)
    
    # Get or create a test user
    user, created = User.objects.get_or_create(
        username='demo_user',
        defaults={
            'email': 'demo@example.com',
            'first_name': 'Demo',
            'last_name': 'User'
        }
    )
    
    if created:
        user.set_password('demo_password')
        user.save()
        print(f"\n✓ Created demo user: {user.username}")
    else:
        print(f"\n✓ Using existing demo user: {user.username}")
    
    # Count initial sessions for this user
    def count_user_sessions(user):
        active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
        count = 0
        for session in active_sessions:
            try:
                session_data = session.get_decoded()
                if session_data.get('_auth_user_id') == str(user.id):
                    count += 1
            except:
                pass
        return count
    
    initial_count = count_user_sessions(user)
    print(f"  Initial active sessions for {user.username}: {initial_count}")
    
    # Simulate first login (e.g., from Computer 1)
    print("\n1. Simulating login from Computer 1...")
    factory = RequestFactory()
    request1 = factory.post('/login/')
    request1.session = {}
    
    # This would normally be done by Django's SessionMiddleware
    from django.contrib.sessions.backends.db import SessionStore
    session1 = SessionStore()
    session1.create()
    request1.session = session1
    
    # Login the user (this triggers our signal)
    from django.contrib.auth.signals import user_logged_in
    user_logged_in.send(sender=User, request=request1, user=user)
    
    # Save the session
    request1.session.save()
    session1_key = request1.session.session_key
    
    sessions_after_first = count_user_sessions(user)
    print(f"   ✓ Login successful")
    print(f"   Session ID: {session1_key}")
    print(f"   Active sessions for {user.username}: {sessions_after_first}")
    
    # Simulate second login (e.g., from Computer 2)
    print("\n2. Simulating login from Computer 2...")
    request2 = factory.post('/login/')
    session2 = SessionStore()
    session2.create()
    request2.session = session2
    
    # Login the user again (this should invalidate the first session)
    user_logged_in.send(sender=User, request=request2, user=user)
    
    # Save the second session
    request2.session.save()
    session2_key = request2.session.session_key
    
    sessions_after_second = count_user_sessions(user)
    print(f"   ✓ Login successful")
    print(f"   Session ID: {session2_key}")
    print(f"   Active sessions for {user.username}: {sessions_after_second}")
    
    # Check if first session was invalidated
    try:
        old_session = Session.objects.get(session_key=session1_key)
        print(f"\n   ⚠ WARNING: First session still exists (this shouldn't happen)")
    except Session.DoesNotExist:
        print(f"\n   ✓ First session was successfully invalidated")
    
    # Verify only one session exists
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    if sessions_after_second == 1:
        print("✓ SUCCESS: Only 1 active session exists for the user")
        print("✓ The security feature is working correctly!")
    else:
        print(f"⚠ UNEXPECTED: {sessions_after_second} sessions exist")
        print("  Expected only 1 session")
    
    print("\nWhat this means:")
    print("- When user logs in on Computer 2, Computer 1 is logged out")
    print("- User can only have one active session at a time")
    print("- This prevents account sharing and improves security")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        simulate_single_session_security()
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        import traceback
        traceback.print_exc()
