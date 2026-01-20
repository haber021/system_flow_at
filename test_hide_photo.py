"""
Test script to verify Hide Student Photo functionality in the attendance system.
This script performs comprehensive tests on the show_photo feature.
"""

import os
import sys
import django

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import Client, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import User
from attendance.models import Student, Subject, SystemSettings

class PhotoToggleTest:
    """Test class for photo toggle functionality"""
    
    def __init__(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.test_results = []
        
    def setup_test_data(self):
        """Create test user if needed"""
        print("\n📋 Setting up test data...")
        try:
            # Get or create test user
            user, created = User.objects.get_or_create(
                username='test_admin',
                defaults={
                    'email': 'admin@test.com',
                    'is_staff': True,
                    'is_superuser': True
                }
            )
            if created:
                user.set_password('testpass123')
                user.save()
                print(f"✅ Created test user: {user.username}")
            else:
                print(f"✅ Using existing test user: {user.username}")
            return user
        except Exception as e:
            print(f"❌ Error setting up test data: {e}")
            return None
    
    def test_session_default_value(self):
        """Test 1: Verify default session value for show_photo is True"""
        print("\n🧪 TEST 1: Checking default session value for show_photo...")
        try:
            session = self.client.session
            # Default should be True when not set
            show_photo = session.get('show_student_photo', True)
            
            if show_photo is True:
                print("✅ PASS: Default show_photo value is True")
                self.test_results.append(("Default Session Value", "PASS"))
                return True
            else:
                print(f"❌ FAIL: Expected True, got {show_photo}")
                self.test_results.append(("Default Session Value", "FAIL"))
                return False
        except Exception as e:
            print(f"❌ ERROR: {e}")
            self.test_results.append(("Default Session Value", f"ERROR: {e}"))
            return False
    
    def test_toggle_functionality(self, user):
        """Test 2: Verify toggle functionality works"""
        print("\n🧪 TEST 2: Testing toggle functionality...")
        try:
            # Login
            self.client.force_login(user)
            
            # Get initial state
            response = self.client.get('/scan/')
            initial_state = self.client.session.get('show_student_photo', True)
            print(f"   Initial state: show_photo = {initial_state}")
            
            # Toggle via POST
            response = self.client.post('/scan/', {
                'toggle_photo': '1'
            })
            
            # Check if toggle worked
            toggled_state = self.client.session.get('show_student_photo', True)
            print(f"   After toggle: show_photo = {toggled_state}")
            
            if toggled_state == (not initial_state):
                print("✅ PASS: Toggle functionality works correctly")
                self.test_results.append(("Toggle Functionality", "PASS"))
                return True
            else:
                print(f"❌ FAIL: Toggle didn't work. Expected {not initial_state}, got {toggled_state}")
                self.test_results.append(("Toggle Functionality", "FAIL"))
                return False
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.test_results.append(("Toggle Functionality", f"ERROR: {e}"))
            return False
    
    def test_multiple_toggles(self, user):
        """Test 3: Verify multiple toggles work correctly"""
        print("\n🧪 TEST 3: Testing multiple toggle operations...")
        try:
            self.client.force_login(user)
            
            # Set initial state to True
            session = self.client.session
            session['show_student_photo'] = True
            session.save()
            
            states = [True]
            
            # Toggle 5 times
            for i in range(5):
                response = self.client.post('/scan/', {
                    'toggle_photo': '1'
                })
                current_state = self.client.session.get('show_student_photo', True)
                states.append(current_state)
                print(f"   Toggle {i+1}: {states[-2]} → {states[-1]}")
            
            # Check if pattern is True, False, True, False, True, False
            expected = [True, False, True, False, True, False]
            
            if states == expected:
                print("✅ PASS: Multiple toggles work correctly")
                self.test_results.append(("Multiple Toggles", "PASS"))
                return True
            else:
                print(f"❌ FAIL: Expected pattern {expected}, got {states}")
                self.test_results.append(("Multiple Toggles", "FAIL"))
                return False
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.test_results.append(("Multiple Toggles", f"ERROR: {e}"))
            return False
    
    def test_context_variable(self, user):
        """Test 4: Verify show_photo is passed to template context"""
        print("\n🧪 TEST 4: Checking if show_photo is in template context...")
        try:
            self.client.force_login(user)
            
            # Set show_photo to False
            session = self.client.session
            session['show_student_photo'] = False
            session.save()
            
            # Get scan page (follow redirects to get final rendered response)
            response = self.client.get('/scan/', follow=True)
            
            # Check if response has context (it should if we reached the template)
            if response.context is None:
                print("❌ FAIL: No template context in response (might be redirect or error)")
                self.test_results.append(("Context Variable", "FAIL - No context"))
                return False
            
            # Check if show_photo is in context
            if 'show_photo' in response.context:
                context_value = response.context['show_photo']
                session_value = self.client.session.get('show_student_photo', True)
                
                if context_value == session_value:
                    print(f"✅ PASS: show_photo in context matches session (value: {context_value})")
                    self.test_results.append(("Context Variable", "PASS"))
                    return True
                else:
                    print(f"❌ FAIL: Context value ({context_value}) doesn't match session ({session_value})")
                    self.test_results.append(("Context Variable", "FAIL"))
                    return False
            else:
                print("❌ FAIL: show_photo not found in template context")
                self.test_results.append(("Context Variable", "FAIL"))
                return False
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.test_results.append(("Context Variable", f"ERROR: {e}"))
            return False
    
    def test_persistence_across_requests(self, user):
        """Test 5: Verify state persists across multiple requests"""
        print("\n🧪 TEST 5: Testing persistence across requests...")
        try:
            self.client.force_login(user)
            
            # Set to False
            session = self.client.session
            session['show_student_photo'] = False
            session.save()
            
            # Make multiple GET requests (follow redirects)
            states = []
            for i in range(3):
                response = self.client.get('/scan/', follow=True)
                if response.context:
                    state = response.context.get('show_photo', None)
                    states.append(state)
                    print(f"   Request {i+1}: show_photo = {state}")
                else:
                    print(f"   Request {i+1}: No context (redirect or error)")
                    states.append(None)
            
            # All should be False
            if all(state is False for state in states):
                print("✅ PASS: State persists correctly across requests")
                self.test_results.append(("Persistence", "PASS"))
                return True
            else:
                print(f"❌ FAIL: State not persisting. Got: {states}")
                self.test_results.append(("Persistence", "FAIL"))
                return False
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            self.test_results.append(("Persistence", f"ERROR: {e}"))
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, result in self.test_results if result == "PASS")
        total = len(self.test_results)
        
        for test_name, result in self.test_results:
            status_icon = "✅" if result == "PASS" else "❌"
            print(f"{status_icon} {test_name:30s} : {result}")
        
        print("="*60)
        print(f"Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        print("="*60)
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED! The Hide Student Photo feature is working correctly.")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed. Please review the implementation.")
    
    def run_all_tests(self):
        """Run all tests"""
        print("="*60)
        print("🚀 STARTING HIDE STUDENT PHOTO FUNCTIONALITY TESTS")
        print("="*60)
        
        user = self.setup_test_data()
        if not user:
            print("❌ Cannot proceed without test user")
            return
        
        # Run all tests
        self.test_session_default_value()
        self.test_toggle_functionality(user)
        self.test_multiple_toggles(user)
        self.test_context_variable(user)
        self.test_persistence_across_requests(user)
        
        # Print summary
        self.print_summary()


def main():
    """Main test runner"""
    tester = PhotoToggleTest()
    tester.run_all_tests()


if __name__ == '__main__':
    main()
