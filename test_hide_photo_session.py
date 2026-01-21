"""
Test script to verify that the hide photo session works correctly
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import Client, RequestFactory
from django.contrib.auth.models import User
from attendance.models import Student, Subject
from django.urls import reverse

def test_hide_photo_toggle():
    """Test that hiding photo persists in session"""
    print("\n" + "="*70)
    print("TESTING HIDE PHOTO TOGGLE FUNCTIONALITY")
    print("="*70)
    
    # Create a test client
    client = Client()
    
    # Create or get a test user with admin rights
    try:
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.create_superuser('testadmin', 'test@test.com', 'testpass123')
            print(f"✓ Created test admin user: {user.username}")
        else:
            print(f"✓ Using existing admin user: {user.username}")
    except Exception as e:
        print(f"✗ Error creating/getting user: {e}")
        return False
    
    # Login
    login_success = client.login(username=user.username, password='testpass123' if user.username == 'testadmin' else 'admin')
    if not login_success:
        # Try with default password
        login_success = client.login(username=user.username, password='admin')
    
    if not login_success:
        print(f"✗ Failed to login with user: {user.username}")
        print("   Please update the test script with the correct password")
        return False
    
    print(f"✓ Logged in as: {user.username}")
    
    # Step 1: Access scan page to verify initial state
    print("\n--- Step 1: Check initial state ---")
    response = client.get(reverse('scan'))
    print(f"Status code: {response.status_code}")
    print(f"show_photo in context: {response.context.get('show_photo', 'NOT FOUND')}")
    
    # Check session
    session = client.session
    initial_show = session.get('show_student_photo', 'NOT SET')
    print(f"show_student_photo in session: {initial_show}")
    
    # Step 2: Toggle photo to hide
    print("\n--- Step 2: Toggle to HIDE photo ---")
    response = client.post(reverse('scan'), {'toggle_photo': '1'}, follow=False)
    print(f"Status code: {response.status_code}")
    print(f"Redirect URL: {response.get('Location', 'NO REDIRECT')}")
    
    # Follow redirect
    if response.status_code == 302:
        response = client.get(response.url)
        print(f"After redirect status: {response.status_code}")
        print(f"show_photo in context: {response.context.get('show_photo', 'NOT FOUND')}")
        
        # Check session after toggle
        session = client.session
        after_toggle = session.get('show_student_photo', 'NOT SET')
        print(f"show_student_photo in session after toggle: {after_toggle}")
        
        if after_toggle == False:
            print("✓ Photo successfully hidden in session")
        else:
            print(f"✗ Expected False, got: {after_toggle}")
            return False
    
    # Step 3: Simulate a student scan to verify photo remains hidden
    print("\n--- Step 3: Simulate student scan (with photo hidden) ---")
    
    # Get a test student
    student = Student.objects.filter(profile_picture__isnull=False).first()
    if not student:
        print("! No student with photo found, creating mock student data in session")
        # Manually set last_scanned_student to simulate a scan
        session = client.session
        session['last_scanned_student'] = {
            'id': 1,
            'name': 'Test Student',
            'rfid_id': '12345',
            'profile_picture_url': '/media/test.jpg',
            'action': 'time_out',
            'time_in': '08:00 AM',
            'time_out': '10:00 AM',
            'status': 'PRESENT',
            'subject_code': 'TEST101'
        }
        session.save()
        print("✓ Mock student scan data added to session")
    
    # Access scan page again to see if photo is hidden
    response = client.get(reverse('scan'))
    print(f"Status code: {response.status_code}")
    print(f"show_photo in context: {response.context.get('show_photo', 'NOT FOUND')}")
    print(f"last_scanned_student in context: {response.context.get('last_scanned_student', 'NOT FOUND')}")
    
    # Verify show_photo is False
    show_photo_value = response.context.get('show_photo')
    if show_photo_value == False:
        print("✓ Photo setting correctly persisted as HIDDEN")
        print("✓ Template will show placeholder icon instead of photo")
    else:
        print(f"✗ Expected show_photo=False, got: {show_photo_value}")
        return False
    
    # Step 4: Toggle back to show
    print("\n--- Step 4: Toggle to SHOW photo ---")
    response = client.post(reverse('scan'), {'toggle_photo': '1'}, follow=True)
    print(f"show_photo in context: {response.context.get('show_photo', 'NOT FOUND')}")
    
    session = client.session
    final_show = session.get('show_student_photo', 'NOT SET')
    print(f"show_student_photo in session after toggle back: {final_show}")
    
    if final_show == True:
        print("✓ Photo successfully shown again")
    else:
        print(f"✗ Expected True, got: {final_show}")
        return False
    
    print("\n" + "="*70)
    print("✓ ALL TESTS PASSED!")
    print("  The hide photo functionality is working correctly.")
    print("  Session persists the show_photo setting across requests.")
    print("="*70)
    return True

if __name__ == '__main__':
    try:
        success = test_hide_photo_toggle()
        if not success:
            print("\n✗ TESTS FAILED")
            exit(1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
