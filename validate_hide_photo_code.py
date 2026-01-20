"""
Code Implementation Validator for Hide Student Photo Feature
============================================================

This script validates that all necessary code is in place for the Hide Student Photo feature.
"""

import os
import sys
import re

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

class CodeValidator:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        
    def check_file_exists(self, filepath, description):
        """Check if a file exists"""
        if os.path.exists(filepath):
            self.passed.append(f"✅ {description}: File exists")
            return True
        else:
            self.failed.append(f"❌ {description}: File not found at {filepath}")
            return False
    
    def check_code_in_file(self, filepath, pattern, description, is_regex=False):
        """Check if specific code exists in a file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if is_regex:
                if re.search(pattern, content, re.MULTILINE | re.DOTALL):
                    self.passed.append(f"✅ {description}")
                    return True
                else:
                    self.failed.append(f"❌ {description}: Pattern not found")
                    return False
            else:
                if pattern in content:
                    self.passed.append(f"✅ {description}")
                    return True
                else:
                    self.failed.append(f"❌ {description}: Code not found")
                    return False
        except Exception as e:
            self.failed.append(f"❌ {description}: Error reading file - {e}")
            return False
    
    def validate_views_py(self):
        """Validate views.py implementation"""
        print("\n" + "="*80)
        print("VALIDATING: attendance/views.py")
        print("="*80)
        
        filepath = "d:/System-Flow_advance_test/attendance/views.py"
        
        if not self.check_file_exists(filepath, "views.py"):
            return
        
        # Check for toggle handler
        self.check_code_in_file(
            filepath,
            "if request.POST.get('toggle_photo'):",
            "Toggle photo POST handler exists"
        )
        
        # Check for session toggle logic
        self.check_code_in_file(
            filepath,
            "request.session['show_student_photo'] = not current",
            "Session toggle logic exists"
        )
        
        # Check for session.modified flag
        self.check_code_in_file(
            filepath,
            "request.session.modified = True",
            "Session.modified flag is set"
        )
        
        # Check for show_photo in context
        self.check_code_in_file(
            filepath,
            "show_photo = request.session.get('show_student_photo', True)",
            "show_photo retrieved from session"
        )
        
        # Check for show_photo passed to context
        self.check_code_in_file(
            filepath,
            "'show_photo': show_photo,",
            "show_photo passed to template context"
        )
    
    def validate_scan_html(self):
        """Validate scan.html template"""
        print("\n" + "="*80)
        print("VALIDATING: attendance/templates/attendance/scan.html")
        print("="*80)
        
        filepath = "d:/System-Flow_advance_test/attendance/templates/attendance/scan.html"
        
        if not self.check_file_exists(filepath, "scan.html"):
            return
        
        # Check for toggle button form
        self.check_code_in_file(
            filepath,
            '<input type="hidden" name="toggle_photo" value="1">',
            "Toggle photo hidden input exists"
        )
        
        # Check for dynamic button text
        self.check_code_in_file(
            filepath,
            "{% if show_photo %}Hide{% else %}Show{% endif %} Student Photo",
            "Dynamic button text (Hide/Show) exists"
        )
        
        # Check for dynamic icon
        self.check_code_in_file(
            filepath,
            "bi-{% if show_photo %}eye-slash{% else %}eye{% endif %}",
            "Dynamic icon (eye/eye-slash) exists"
        )
        
        # Check for photo conditional in modal
        self.check_code_in_file(
            filepath,
            r"{% if show_photo %}.*profile_picture",
            "Photo display conditional exists in modal",
            is_regex=True
        )
    
    def validate_session_settings(self):
        """Validate Django session settings"""
        print("\n" + "="*80)
        print("VALIDATING: core/settings.py (Session Configuration)")
        print("="*80)
        
        filepath = "d:/System-Flow_advance_test/core/settings.py"
        
        if not self.check_file_exists(filepath, "settings.py"):
            return
        
        # Check if sessions are enabled
        self.check_code_in_file(
            filepath,
            "django.contrib.sessions",
            "Sessions app is installed"
        )
        
        self.check_code_in_file(
            filepath,
            "SessionMiddleware",
            "Session middleware is enabled"
        )
        
        # Check for session configuration (optional)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'SESSION_COOKIE_AGE' in content:
                self.passed.append("✅ Session cookie age is configured")
            else:
                self.warnings.append("⚠️  SESSION_COOKIE_AGE not explicitly set (using Django default)")
    
    def print_summary(self):
        """Print validation summary"""
        print("\n" + "="*80)
        print("VALIDATION SUMMARY")
        print("="*80)
        
        print("\n✅ PASSED CHECKS:")
        for item in self.passed:
            print(f"  {item}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for item in self.warnings:
                print(f"  {item}")
        
        if self.failed:
            print("\n❌ FAILED CHECKS:")
            for item in self.failed:
                print(f"  {item}")
        
        print("\n" + "="*80)
        total = len(self.passed) + len(self.failed)
        percentage = (len(self.passed) / total * 100) if total > 0 else 0
        
        print(f"RESULT: {len(self.passed)}/{total} checks passed ({percentage:.1f}%)")
        
        if len(self.failed) == 0:
            print("\n🎉 ALL CRITICAL CHECKS PASSED!")
            print("The Hide Student Photo feature is properly implemented in the code.")
        else:
            print(f"\n⚠️  {len(self.failed)} check(s) failed.")
            print("Please review the implementation.")
        
        print("="*80)
    
    def run_all_validations(self):
        """Run all validation checks"""
        print("="*80)
        print("🔍 CODE IMPLEMENTATION VALIDATOR")
        print("Hide Student Photo Feature")
        print("="*80)
        
        self.validate_views_py()
        self.validate_scan_html()
        self.validate_session_settings()
        self.print_summary()


def main():
    validator = CodeValidator()
    validator.run_all_validations()


if __name__ == '__main__':
    main()
