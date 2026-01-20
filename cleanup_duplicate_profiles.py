"""
Script to clean up duplicate profile pictures from student_profiles folder.
This will keep only the most recent profile picture for each student.
"""

import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from attendance.models import Student
from collections import defaultdict

def cleanup_duplicate_profiles():
    """Remove duplicate profile pictures, keeping only the current one for each student"""
    
    media_root = 'media/student_profiles'
    
    if not os.path.exists(media_root):
        print(f"Directory {media_root} does not exist")
        return
    
    # Get all students with profile pictures
    students_with_pictures = Student.objects.exclude(profile_picture='').exclude(profile_picture__isnull=True)
    
    # Build a set of currently used profile picture paths
    current_pictures = set()
    for student in students_with_pictures:
        if student.profile_picture:
            try:
                # Get the full path
                full_path = student.profile_picture.path
                current_pictures.add(full_path)
                print(f"Active: {student.name} ({student.id}) -> {os.path.basename(full_path)}")
            except Exception as e:
                print(f"Error getting path for student {student.id}: {e}")
    
    # Get all files in the student_profiles directory
    all_files = []
    for filename in os.listdir(media_root):
        if filename.startswith('profile_') and filename.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            full_path = os.path.join(media_root, filename)
            all_files.append(full_path)
    
    print(f"\nTotal files in directory: {len(all_files)}")
    print(f"Currently active files: {len(current_pictures)}")
    
    # Delete files that are not in the current_pictures set
    deleted_count = 0
    for file_path in all_files:
        if file_path not in current_pictures:
            try:
                os.remove(file_path)
                print(f"Deleted: {os.path.basename(file_path)}")
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
    
    print(f"\nCleanup complete!")
    print(f"Deleted {deleted_count} duplicate/orphaned profile pictures")
    print(f"Kept {len(current_pictures)} active profile pictures")

if __name__ == '__main__':
    print("Starting cleanup of duplicate profile pictures...\n")
    cleanup_duplicate_profiles()
