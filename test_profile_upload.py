"""
Test script to identify errors in profile picture upload functionality.
Run this with: python test_profile_upload.py
"""

import os
import sys
import django
import base64
from io import BytesIO
from PIL import Image

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from attendance.models import Student, Course, Section
from django.conf import settings
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def create_test_image(size=(800, 600), format='JPEG'):
    """Create a test image in memory"""
    img = Image.new('RGB', size, color=(73, 109, 137))
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer

def test_student_exists():
    """Test if there's at least one student in the database"""
    logger.info("=" * 60)
    logger.info("TEST 1: Checking for existing students")
    logger.info("=" * 60)
    
    try:
        students = Student.objects.all()
        count = students.count()
        logger.info(f"✓ Found {count} students in database")
        
        if count > 0:
            student = students.first()
            logger.info(f"  - Student ID: {student.id}")
            logger.info(f"  - Name: {student.name}")
            logger.info(f"  - RFID: {student.rfid_id}")
            logger.info(f"  - Current profile: {student.profile_picture.name if student.profile_picture else 'None'}")
            return student
        else:
            logger.warning("✗ No students found. Creating test student...")
            return create_test_student()
    except Exception as e:
        logger.error(f"✗ Error checking students: {e}")
        return None

def create_test_student():
    """Create a test student for upload testing"""
    try:
        # Get or create course and section
        course, _ = Course.objects.get_or_create(
            code='TEST',
            defaults={'name': 'Test Course', 'is_active': True}
        )
        section, _ = Section.objects.get_or_create(
            code='A',
            defaults={'name': 'Section A', 'is_active': True}
        )
        
        # Create user
        user, _ = User.objects.get_or_create(
            username='teststudent',
            defaults={'email': 'test@example.com', 'first_name': 'Test', 'last_name': 'Student'}
        )
        
        # Create student
        student, created = Student.objects.get_or_create(
            rfid_id='TEST123456',
            defaults={
                'student_id': 'TEST001',
                'name': 'Test Student',
                'course': course,
                'section': section,
                'email': 'test@example.com',
                'user': user
            }
        )
        
        if created:
            logger.info("✓ Created test student successfully")
        else:
            logger.info("✓ Test student already exists")
        
        return student
    except Exception as e:
        logger.error(f"✗ Error creating test student: {e}")
        return None

def test_image_upload(student):
    """Test uploading a profile picture"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Testing image upload")
    logger.info("=" * 60)
    
    try:
        # Create test image
        logger.info("Creating test image (800x600 JPEG)...")
        image_buffer = create_test_image(size=(800, 600), format='JPEG')
        
        # Create uploaded file object
        uploaded_file = SimpleUploadedFile(
            name='test_profile.jpg',
            content=image_buffer.read(),
            content_type='image/jpeg'
        )
        
        logger.info(f"  - File size: {uploaded_file.size / 1024:.2f} KB")
        logger.info(f"  - Content type: {uploaded_file.content_type}")
        
        # Save old profile path
        old_profile = student.profile_picture.name if student.profile_picture else None
        logger.info(f"  - Old profile: {old_profile or 'None'}")
        
        # Assign and save
        logger.info("Assigning new profile picture...")
        student.profile_picture = uploaded_file
        
        logger.info("Saving student model...")
        student.save()
        
        # Refresh from database
        logger.info("Refreshing from database...")
        student.refresh_from_db()
        
        # Check if saved
        if student.profile_picture:
            logger.info(f"✓ Profile picture saved successfully!")
            logger.info(f"  - New path: {student.profile_picture.name}")
            logger.info(f"  - File exists: {os.path.exists(student.profile_picture.path)}")
            logger.info(f"  - File size: {os.path.getsize(student.profile_picture.path) / 1024:.2f} KB")
            
            # Check if optimized
            try:
                img = Image.open(student.profile_picture.path)
                logger.info(f"  - Image dimensions: {img.size}")
                logger.info(f"  - Image format: {img.format}")
                img.close()
            except Exception as e:
                logger.warning(f"  - Could not read image: {e}")
            
            return True
        else:
            logger.error("✗ Profile picture not saved to database!")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error during upload: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_large_image(student):
    """Test uploading a large image"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Testing large image (3000x3000)")
    logger.info("=" * 60)
    
    try:
        # Create large test image
        logger.info("Creating large test image...")
        image_buffer = create_test_image(size=(3000, 3000), format='JPEG')
        
        uploaded_file = SimpleUploadedFile(
            name='test_large_profile.jpg',
            content=image_buffer.read(),
            content_type='image/jpeg'
        )
        
        logger.info(f"  - File size: {uploaded_file.size / 1024 / 1024:.2f} MB")
        
        # Assign and save
        student.profile_picture = uploaded_file
        student.save()
        student.refresh_from_db()
        
        if student.profile_picture:
            # Check if optimized to 400x400
            img = Image.open(student.profile_picture.path)
            logger.info(f"✓ Large image handled successfully!")
            logger.info(f"  - Optimized dimensions: {img.size}")
            logger.info(f"  - Should be max 400x400: {'✓' if img.width <= 400 and img.height <= 400 else '✗'}")
            img.close()
            return True
        else:
            logger.error("✗ Large image not saved!")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error with large image: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_png_upload(student):
    """Test uploading PNG image"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Testing PNG image upload")
    logger.info("=" * 60)
    
    try:
        # Create PNG with transparency
        logger.info("Creating PNG image with transparency...")
        img = Image.new('RGBA', (500, 500), color=(255, 0, 0, 128))
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        uploaded_file = SimpleUploadedFile(
            name='test_profile.png',
            content=buffer.read(),
            content_type='image/png'
        )
        
        # Assign and save
        student.profile_picture = uploaded_file
        student.save()
        student.refresh_from_db()
        
        if student.profile_picture:
            # Check if converted to JPEG (removes transparency)
            img = Image.open(student.profile_picture.path)
            logger.info(f"✓ PNG image handled successfully!")
            logger.info(f"  - Final format: {img.format}")
            logger.info(f"  - Final mode: {img.mode}")
            logger.info(f"  - Converted to JPEG: {'✓' if img.format == 'JPEG' else '✗'}")
            img.close()
            return True
        else:
            logger.error("✗ PNG image not saved!")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error with PNG image: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_base64_cropped_image(student):
    """Test uploading cropped image (base64)"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Testing base64 cropped image")
    logger.info("=" * 60)
    
    try:
        # Create test image and convert to base64
        logger.info("Creating base64 encoded image...")
        image_buffer = create_test_image(size=(600, 600), format='JPEG')
        image_base64 = base64.b64encode(image_buffer.read()).decode('utf-8')
        cropped_data = f"data:image/jpeg;base64,{image_base64}"
        
        logger.info(f"  - Base64 length: {len(image_base64)} characters")
        
        # Decode like the view does
        header, encoded = cropped_data.split(';base64,')
        mime_type = header.replace('data:', '')
        image_bytes = base64.b64decode(encoded)
        
        uploaded_file = SimpleUploadedFile(
            f"profile_cropped_{student.id}.jpg",
            image_bytes,
            content_type=mime_type
        )
        
        logger.info(f"  - Decoded size: {len(image_bytes) / 1024:.2f} KB")
        
        # Assign and save
        student.profile_picture = uploaded_file
        student.save()
        student.refresh_from_db()
        
        if student.profile_picture:
            logger.info(f"✓ Base64 cropped image saved successfully!")
            logger.info(f"  - Path: {student.profile_picture.name}")
            return True
        else:
            logger.error("✗ Base64 image not saved!")
            return False
            
    except Exception as e:
        logger.error(f"✗ Error with base64 image: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_permissions():
    """Test media directory permissions"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Checking file system permissions")
    logger.info("=" * 60)
    
    try:
        media_root = settings.MEDIA_ROOT
        student_profiles_dir = os.path.join(media_root, 'student_profiles')
        
        logger.info(f"MEDIA_ROOT: {media_root}")
        logger.info(f"Student profiles dir: {student_profiles_dir}")
        
        # Check if media root exists
        if os.path.exists(media_root):
            logger.info(f"✓ MEDIA_ROOT exists")
        else:
            logger.warning(f"✗ MEDIA_ROOT does not exist!")
            os.makedirs(media_root, exist_ok=True)
            logger.info(f"  - Created MEDIA_ROOT")
        
        # Check if student_profiles exists
        if os.path.exists(student_profiles_dir):
            logger.info(f"✓ student_profiles directory exists")
        else:
            logger.warning(f"✗ student_profiles directory does not exist!")
            os.makedirs(student_profiles_dir, exist_ok=True)
            logger.info(f"  - Created student_profiles directory")
        
        # Test write permissions
        test_file = os.path.join(student_profiles_dir, 'test_write.txt')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            logger.info(f"✓ Write permissions OK")
        except Exception as e:
            logger.error(f"✗ No write permissions: {e}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Error checking permissions: {e}")
        return False

def cleanup_test_files(student):
    """Clean up test files"""
    logger.info("\n" + "=" * 60)
    logger.info("CLEANUP: Removing test files")
    logger.info("=" * 60)
    
    try:
        if student and student.profile_picture:
            path = student.profile_picture.path
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"✓ Removed test file: {path}")
            student.profile_picture = None
            student.save()
            logger.info(f"✓ Cleared student profile picture")
        return True
    except Exception as e:
        logger.warning(f"Could not clean up: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("PROFILE PICTURE UPLOAD TEST SUITE")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Check student exists
    student = test_student_exists()
    results['Student Exists'] = student is not None
    
    if not student:
        logger.error("\n✗✗✗ Cannot proceed without a student! ✗✗✗")
        return
    
    # Test 2: File permissions
    results['File Permissions'] = test_file_permissions()
    
    # Test 3: Basic upload
    results['Basic Upload'] = test_image_upload(student)
    
    # Test 4: Large image
    results['Large Image (3000x3000)'] = test_large_image(student)
    
    # Test 5: PNG upload
    results['PNG Upload'] = test_png_upload(student)
    
    # Test 6: Base64 cropped
    results['Base64 Cropped'] = test_base64_cropped_image(student)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST RESULTS SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    logger.info("=" * 60)
    logger.info(f"TOTAL: {passed}/{total} tests passed")
    logger.info("=" * 60)
    
    # Cleanup
    if input("\nClean up test files? (y/n): ").lower() == 'y':
        cleanup_test_files(student)
    
    if passed == total:
        print("\n🎉 All tests passed! Profile upload is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the logs above for details.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        logger.error(f"\n✗✗✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
