"""
Quick check to see what's happening with the scan view
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

from django.test import Client
from django.contrib.auth.models import User
from attendance.models import Subject, Adviser, Instructor

client = Client()

# Get or create test user
user = User.objects.get(username='test_admin')
client.force_login(user)

# Check subjects
subjects = Subject.objects.filter(is_active=True)
print(f"Active subjects: {subjects.count()}")
for subj in subjects[:5]:
    print(f"  - {subj.code}: {subj.name}")

# Try to get the scan page
print("\nTrying to access /scan/...")
response = client.get('/scan/', follow=True)
print(f"Status code: {response.status_code}")
print(f"Has context: {response.context is not None}")
print(f"Redirect chain: {response.redirect_chain}")

if response.context:
    print(f"Context keys: {list(response.context.keys())}")
    print(f"show_photo value: {response.context.get('show_photo', 'NOT FOUND')}")
else:
    print("No context - checking response content...")
    print(response.content[:500].decode('utf-8', errors='ignore'))
