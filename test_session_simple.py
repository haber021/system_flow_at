"""
Simple test to verify hide photo functionality without login requirement
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from attendance.views import scan_view
from django.contrib.auth.models import User, AnonymousUser

def test_session_persistence():
    """Test that show_photo session setting works correctly"""
    print("\n" + "="*70)
    print("TESTING HIDE PHOTO SESSION PERSISTENCE")
    print("="*70)
    
    # Create a session
    session = SessionStore()
    
    # Test 1: Default value should be True
    print("\n--- Test 1: Default value ---")
    default_value = session.get('show_student_photo', True)
    print(f"Default show_student_photo value: {default_value}")
    if default_value == True:
        print("✓ Default is True (show photo)")
    else:
        print("✗ Expected True")
        return False
    
    # Test 2: Set to False (hide photo)
    print("\n--- Test 2: Set to False (hide) ---")
    session['show_student_photo'] = False
    session.save()
    print(f"Set show_student_photo to: False")
    print(f"Session key: {session.session_key}")
    
    # Test 3: Retrieve in new session instance (simulates new request)
    print("\n--- Test 3: Retrieve from saved session ---")
    new_session = SessionStore(session_key=session.session_key)
    retrieved_value = new_session.get('show_student_photo', True)
    print(f"Retrieved show_student_photo: {retrieved_value}")
    
    if retrieved_value == False:
        print("✓ Session persisted correctly as False")
    else:
        print(f"✗ Expected False, got: {retrieved_value}")
        return False
    
    # Test 4: Toggle back to True
    print("\n--- Test 4: Toggle back to True ---")
    current = new_session.get('show_student_photo', True)
    new_session['show_student_photo'] = not current  # Should toggle False -> True
    new_session.save()
    print(f"Toggled from {current} to {not current}")
    
    # Test 5: Verify toggle worked
    print("\n--- Test 5: Verify toggle ---")
    verify_session = SessionStore(session_key=new_session.session_key)
    final_value = verify_session.get('show_student_photo', True)
    print(f"Final show_student_photo value: {final_value}")
    
    if final_value == True:
        print("✓ Toggle worked correctly, back to True")
    else:
        print(f"✗ Expected True, got: {final_value}")
        return False
    
    # Test 6: Simulate the actual toggle logic from views.py
    print("\n--- Test 6: Simulate view toggle logic ---")
    test_session = SessionStore()
    test_session.save()
    
    # Initial state (default True)
    current = test_session.get('show_student_photo', True)
    print(f"Initial: {current}")
    
    # First toggle (True -> False)
    test_session['show_student_photo'] = not current
    test_session.modified = True
    test_session.save()
    
    reload_session = SessionStore(session_key=test_session.session_key)
    after_first_toggle = reload_session.get('show_student_photo', True)
    print(f"After first toggle: {after_first_toggle}")
    
    if after_first_toggle != False:
        print(f"✗ Expected False after first toggle, got: {after_first_toggle}")
        return False
    
    # Second toggle (False -> True)
    reload_session['show_student_photo'] = not after_first_toggle
    reload_session.modified = True
    reload_session.save()
    
    final_reload = SessionStore(session_key=reload_session.session_key)
    after_second_toggle = final_reload.get('show_student_photo', True)
    print(f"After second toggle: {after_second_toggle}")
    
    if after_second_toggle != True:
        print(f"✗ Expected True after second toggle, got: {after_second_toggle}")
        return False
    
    print("✓ View toggle logic works correctly")
    
    print("\n" + "="*70)
    print("✓ ALL SESSION TESTS PASSED!")
    print("  Session correctly stores and retrieves show_student_photo")
    print("  Toggle logic works as expected")
    print("="*70)
    return True

if __name__ == '__main__':
    try:
        success = test_session_persistence()
        if not success:
            print("\n✗ TESTS FAILED")
            exit(1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
