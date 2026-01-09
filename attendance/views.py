from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.conf import settings as django_settings
from django.db.models import Q, Count, Sum, F
from django.db import transaction, IntegrityError
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.contrib.sessions.exceptions import SessionInterrupted
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMessage
from django.conf import settings as django_settings
from django.template.loader import render_to_string
import csv
import json
import traceback
import logging
import os
import base64
from datetime import datetime, timedelta
from decimal import Decimal
import pytz

from .models import (
    Student, Subject, Attendance, SystemSettings, 
    StudentSubject, EmailLog, SubjectSchedule, EnrollmentRequest, Adviser, Course, Instructor, Section, PasswordResetToken
)
from .email_utils import send_attendance_email, resend_email, send_emails_bulk

# Get Manila timezone
MANILA_TZ = pytz.timezone('Asia/Manila')

# Logger
logger = logging.getLogger(__name__)

# Cache key for SystemSettings
SETTINGS_CACHE_KEY = 'system_settings'
SETTINGS_CACHE_TIMEOUT = 300  # 5 minutes

def get_cached_settings():
    """Get SystemSettings with caching for better performance"""
    settings = cache.get(SETTINGS_CACHE_KEY)
    if settings is None:
        settings = SystemSettings.get_settings()
        cache.set(SETTINGS_CACHE_KEY, settings, SETTINGS_CACHE_TIMEOUT)
    return settings

def invalidate_settings_cache():
    """Invalidate SystemSettings cache when settings are updated"""
    cache.delete(SETTINGS_CACHE_KEY)

def mask_email(email):
    """
    Mask email address for security - shows first 3 letters of local part,
    then asterisks, followed by @domain.
    Example: vincenthaber21@gmail.com -> vin****@gmail.com
    """
    if not email or '@' not in email:
        return email
    
    local_part, domain = email.split('@', 1)
    
    if len(local_part) <= 3:
        # If local part is 3 chars or less, show all
        masked_local = local_part + '****'
    else:
        # Show first 3 chars + asterisks
        masked_local = local_part[:3] + '****'
    
    return f"{masked_local}@{domain}"

def make_aware_datetime(date, time):
    """Create a timezone-aware datetime in Manila timezone from date and time objects"""
    naive_dt = datetime.combine(date, time)
    return MANILA_TZ.localize(naive_dt)

def get_manila_now():
    """Get current time in Manila timezone"""
    return timezone.now().astimezone(MANILA_TZ)

def get_user_accessible_courses(user):
    """
    Get courses that a user can access based on their role.
    Returns queryset of Course objects.
    - Superuser/Staff: All active courses
    - Adviser: Courses assigned to the adviser
    - Student: Student's enrolled course only
    - Others: Empty queryset
    """
    if user.is_superuser or user.is_staff:
        return Course.objects.filter(is_active=True)
    elif hasattr(user, 'adviser_profile'):
        adviser = user.adviser_profile
        return adviser.courses.filter(is_active=True)
    elif hasattr(user, 'student_profile'):
        student = user.student_profile
        if student.course:
            return Course.objects.filter(id=student.course.id, is_active=True)
        return Course.objects.none()
    return Course.objects.none()

def filter_by_user_courses(queryset, user, course_field='course'):
    """
    Filter a queryset to only include records accessible by the user based on their courses.
    For Student queryset, use course_field='course'
    For Subject queryset, use course_field='course'
    """
    accessible_courses = get_user_accessible_courses(user)
    if user.is_superuser or user.is_staff:
        # Superuser/staff can see all
        return queryset
    elif accessible_courses.exists():
        # Filter by accessible courses
        return queryset.filter(**{f'{course_field}__in': accessible_courses})
    else:
        # No accessible courses, return empty queryset
        return queryset.none()

def filter_subjects_by_user(user):
    """
    Filter subjects based on user role:
    - Admin/Staff: All subjects
    - Adviser: Subjects they created OR subjects their assigned students are enrolled in
    - Others: Empty queryset
    Returns a filtered Subject queryset.
    """
    subjects = Subject.objects.all()
    if user.is_superuser or user.is_staff:
        # Admin/staff can see all subjects
        return subjects
    elif hasattr(user, 'adviser_profile'):
        # Advisers see subjects they created OR subjects their assigned students are enrolled in
        adviser = user.adviser_profile
        adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
        # Get subjects where students are enrolled
        enrolled_subject_ids = StudentSubject.objects.filter(
            student_id__in=adviser_student_ids
        ).values_list('subject_id', flat=True).distinct()
        # Combine: subjects created by adviser OR subjects their students are enrolled in
        return subjects.filter(
            Q(adviser=adviser) | Q(id__in=enrolled_subject_ids)
        ).distinct()
    else:
        # Other users see no subjects (unless they're students - handled separately)
        return subjects.none()

def filter_instructors_by_user(user):
    """
    Filter instructors based on user role:
    - Admin/Staff: All instructors
    - Adviser: Only instructors assigned to them
    - Others: Empty queryset
    Returns a filtered Instructor queryset.
    """
    instructors = Instructor.objects.all()
    if user.is_superuser or user.is_staff:
        # Admin/staff can see all instructors
        return instructors
    elif hasattr(user, 'adviser_profile'):
        # Advisers only see instructors assigned to them
        return instructors.filter(adviser=user.adviser_profile)
    else:
        # Other users see no instructors
        return instructors.none()

def filter_by_adviser_students(queryset, user, student_field='student'):
    """
    Filter a queryset to include records for students assigned to the adviser.
    For Attendance queryset, use student_field='student'
    For StudentSubject queryset, use student_field='student'
    - Admin/Staff: All records
    - Adviser: Records for students assigned to them (regardless of subject ownership)
    - Others: Filtered by accessible courses
    """
    if user.is_superuser or user.is_staff:
        # Superuser/staff can see all
        return queryset
    elif hasattr(user, 'adviser_profile'):
        # Advisers can see all data for their assigned students
        adviser = user.adviser_profile
        adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
        return queryset.filter(**{f'{student_field}__in': adviser_student_ids})
    else:
        # Other users filter by accessible courses
        accessible_courses = get_user_accessible_courses(user)
        if accessible_courses.exists():
            return queryset.filter(**{f'{student_field}__course__in': accessible_courses})
        else:
            return queryset.none()

def validate_attendance_time(subject, attendance_date, attendance_time, settings=None):
    """
    Validate if attendance is allowed at the given date and time.
    
    Returns a tuple: (is_valid: bool, error_message: str, schedule: SubjectSchedule or None)
    """
    if settings is None:
        settings = SystemSettings.get_settings()
    
    # If time validation is disabled, allow all attendance
    if not settings.enable_time_validation:
        return True, None, None
    
    # Use the actual attendance_time as-is for validation
    # Don't normalize here - use precise time for accurate boundary checking
    # Normalization should only happen when storing to database
    
    # Get the day of week for the attendance date (0=Monday, 6=Sunday)
    day_of_week = attendance_date.weekday()
    day_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day_of_week]
    
    # First check for specific date schedules (for backward compatibility)
    date_schedules = SubjectSchedule.objects.filter(
        subject=subject,
        date=attendance_date
    ).order_by('time_start')
    
    if date_schedules.exists():
        schedules = date_schedules
    else:
        # Check for weekly schedules (day of week)
        # Look for schedules where date is NULL (weekly) and day_of_week matches exactly
        schedules = SubjectSchedule.objects.filter(
            subject=subject,
            day_of_week=day_of_week,
            date__isnull=True
        ).order_by('time_start')
    
    # Convert attendance_time to datetime for accurate comparison
    attendance_datetime = make_aware_datetime(attendance_date, attendance_time)
    
    if schedules.exists():
        # Check against schedules for this date/day
        valid_schedule = None
        
        for schedule in schedules:
            # Calculate valid time window with grace periods using datetime for accurate comparison
            # Start time: schedule.time_start - early_attendance_minutes
            start_datetime = make_aware_datetime(attendance_date, schedule.time_start)
            early_start_dt = start_datetime - timedelta(minutes=settings.early_attendance_minutes)
            
            # End time: schedule.time_end + late_attendance_minutes
            end_datetime = make_aware_datetime(attendance_date, schedule.time_end)
            late_end_dt = end_datetime + timedelta(minutes=settings.late_attendance_minutes)
            
            # Compare using datetime to avoid time wrapping issues
            # Make sure attendance_datetime falls within the valid window (inclusive on both ends)
            if early_start_dt <= attendance_datetime <= late_end_dt:
                valid_schedule = schedule
                break
        
        if valid_schedule:
            return True, None, valid_schedule
        else:
            # Format schedule details for error message
            schedule_details = []
            for schedule in schedules:
                # Show actual schedule time from database with grace periods
                actual_start = schedule.time_start.strftime('%I:%M %p')
                actual_end = schedule.time_end.strftime('%I:%M %p')
                
                # Calculate and show valid time window
                start_dt = make_aware_datetime(attendance_date, schedule.time_start)
                end_dt = make_aware_datetime(attendance_date, schedule.time_end)
                early_start_dt = start_dt - timedelta(minutes=settings.early_attendance_minutes)
                late_end_dt = end_dt + timedelta(minutes=settings.late_attendance_minutes)
                
                valid_start = early_start_dt.time().strftime('%I:%M %p')
                valid_end = late_end_dt.time().strftime('%I:%M %p')
                
                schedule_details.append(f"{actual_start} - {actual_end} (Valid: {valid_start} - {valid_end})")
            
            schedule_details_str = " | ".join(schedule_details)
            return False, f"Attendance not allowed at this time for {day_name} ({attendance_date.strftime('%Y-%m-%d')}). Valid time window: {schedule_details_str}.", None
    
    # No schedule found for this specific date/day - strict validation
    # Check if subject has any schedules at all
    all_schedules = SubjectSchedule.objects.filter(
        subject=subject,
        date__isnull=True
    ).exclude(day_of_week__isnull=True)
    
    if all_schedules.exists():
        # Show which days have schedules
        scheduled_days = []
        for schedule in all_schedules:
            day_name_sched = dict(SubjectSchedule.DAY_CHOICES).get(schedule.day_of_week, 'Unknown')
            if day_name_sched not in scheduled_days:
                scheduled_days.append(day_name_sched)
        
        scheduled_days_str = ", ".join(sorted(scheduled_days))
        return False, f"No schedule found for {subject.code} on {day_name} ({attendance_date.strftime('%Y-%m-%d')}). Available schedules: {scheduled_days_str}. Please add a schedule for {day_name} or edit the subject to add schedules.", None
    else:
        # Check if subject has general schedule times as last resort fallback
        if subject.schedule_time_start and subject.schedule_time_end:
            # Use general schedule as fallback
            class_start = subject.schedule_time_start
            class_end = subject.schedule_time_end
            
            # Calculate valid time window with grace periods using datetime for accurate comparison
            start_datetime = make_aware_datetime(attendance_date, class_start)
            end_datetime = make_aware_datetime(attendance_date, class_end)
            early_start_dt = start_datetime - timedelta(minutes=settings.early_attendance_minutes)
            late_end_dt = end_datetime + timedelta(minutes=settings.late_attendance_minutes)
            
            # Compare using datetime to avoid time wrapping issues
            if early_start_dt <= attendance_datetime <= late_end_dt:
                return True, None, None
            else:
                # Show actual schedule time from database
                actual_start = subject.schedule_time_start.strftime('%I:%M %p')
                actual_end = subject.schedule_time_end.strftime('%I:%M %p')
                valid_start = early_start_dt.time().strftime('%I:%M %p')
                valid_end = late_end_dt.time().strftime('%I:%M %p')
                return False, f"Attendance not allowed at this time for {day_name}. Schedule: {actual_start} - {actual_end} (Valid: {valid_start} - {valid_end}).", None
        else:
            # No schedules at all
            return False, f"No schedule found for {subject.code} on {day_name} ({attendance_date.strftime('%Y-%m-%d')}). Please add schedules for this subject in the admin panel or subject management page.", None

# Authentication Views
def login_view(request):
    if request.user.is_authenticated:
        # Check if user is a student
        if hasattr(request.user, 'student_profile'):
            return redirect('student_dashboard')
        # Check if user is an adviser (not staff/admin and has assigned students)
        if not (request.user.is_staff or request.user.is_superuser):
            if hasattr(request.user, 'adviser_profile'):
                has_assigned_students = Student.objects.filter(adviser=request.user.adviser_profile).exists()
                if has_assigned_students:
                    return redirect('adviser_features')
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        # If authentication failed, try to find user by employee_id
        if user is None:
            try:
                # Check if the input matches an adviser's employee_id
                adviser = Adviser.objects.get(employee_id=username)
                if adviser.user:
                    # Try to authenticate with the linked user's username
                    user = authenticate(request, username=adviser.user.username, password=password)
            except Adviser.DoesNotExist:
                pass
        
        if user is not None:
            login(request, user)
            # Check if user is a student and redirect accordingly
            if hasattr(user, 'student_profile'):
                messages.success(request, f"Welcome, {user.student_profile.name}!")
                return redirect('student_dashboard')
            # Check if user is an adviser (not staff/admin and has assigned students)
            elif not (user.is_staff or user.is_superuser):
                if hasattr(user, 'adviser_profile'):
                    has_assigned_students = Student.objects.filter(adviser=user.adviser_profile).exists()
                    adviser_name = user.adviser_profile.name
                    if has_assigned_students:
                        messages.success(request, f"Welcome, {adviser_name}!")
                        return redirect('adviser_features')
                    else:
                        messages.success(request, f"Welcome, {adviser_name}!")
                        return redirect('dashboard')
                else:
                    messages.success(request, f"Welcome, {user.get_full_name() or user.username}!")
                    return redirect('dashboard')
            else:
                # Admin/Staff user
                messages.success(request, f"Welcome, {user.get_full_name() or user.username}!")
                return redirect('dashboard')
        else:
            messages.error(request, "Invalid username/employee ID or password.")
    
    return render(request, 'attendance/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

def forgot_password_view(request):
    """Handle forgot password requests"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        
        if not email:
            messages.error(request, "Please enter your email address.")
            return render(request, 'attendance/forgot_password.html')
        
        try:
            # Find user by email
            user = User.objects.get(email=email)
            
            # Generate password reset token
            reset_token = PasswordResetToken.generate_token(user)
            
            # Create reset link
            reset_url = request.build_absolute_uri(
                reverse('reset_password', args=[reset_token.token])
            )
            
            # Prepare email content
            email_subject = "Password Reset Request - DMMMSU Attendance Monitor"
            email_body = f"""
Hello {user.get_full_name() or user.username},

You have requested to reset your password for your DMMMSU Attendance Monitor account.

Please click the following link to reset your password:
{reset_url}

This link will expire in 24 hours. If you did not request this password reset, please ignore this email.

If you have any concerns, please contact the system administrator.

Best regards,
DMMMSU Attendance Monitor System
"""
            
            # Send email
            try:
                email_message = EmailMessage(
                    subject=email_subject,
                    body=email_body,
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    to=[email],
                )
                email_message.send(fail_silently=False)
                
                messages.success(
                    request, 
                    "Password reset link has been sent to your email address. Please check your inbox (and spam folder)."
                )
            except Exception as e:
                logger.error(f"Failed to send password reset email to {email}: {str(e)}")
                messages.error(
                    request,
                    "Failed to send password reset email. Please try again later or contact the administrator."
                )
            
        except User.DoesNotExist:
            # Don't reveal whether email exists or not (security best practice)
            messages.success(
                request,
                "If an account with that email exists, a password reset link has been sent."
            )
        except Exception as e:
            logger.error(f"Error in forgot_password_view: {str(e)}")
            messages.error(request, "An error occurred. Please try again later.")
        
        return redirect('login')
    
    return render(request, 'attendance/forgot_password.html')

def reset_password_view(request, token):
    """Handle password reset with token"""
    try:
        # Find the token
        reset_token = PasswordResetToken.objects.get(token=token)
        
        # Check if token is valid
        if not reset_token.is_valid():
            messages.error(request, "This password reset link has expired or has already been used. Please request a new one.")
            return redirect('forgot_password')
        
        if request.method == 'POST':
            password = request.POST.get('password')
            password_confirm = request.POST.get('password_confirm')
            
            # Validate passwords
            if not password or not password_confirm:
                messages.error(request, "Please fill in all password fields.")
                return render(request, 'attendance/reset_password.html', {'token': token, 'valid': True})
            
            if password != password_confirm:
                messages.error(request, "Passwords do not match.")
                return render(request, 'attendance/reset_password.html', {'token': token, 'valid': True})
            
            if len(password) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
                return render(request, 'attendance/reset_password.html', {'token': token, 'valid': True})
            
            # Set new password
            user = reset_token.user
            user.set_password(password)
            user.save()
            
            # Mark token as used
            reset_token.mark_as_used()
            
            messages.success(request, "Your password has been reset successfully. You can now login with your new password.")
            return redirect('login')
        
        # GET request - show reset form
        return render(request, 'attendance/reset_password.html', {'token': token, 'valid': True})
        
    except PasswordResetToken.DoesNotExist:
        messages.error(request, "Invalid password reset link. Please request a new one.")
        return redirect('forgot_password')
    except Exception as e:
        logger.error(f"Error in reset_password_view: {str(e)}")
        messages.error(request, "An error occurred. Please try again.")
        return redirect('forgot_password')

# Dashboard
@login_required
def dashboard(request):
    # Cache static counts for 5 minutes, but refresh today's attendance more frequently
    cache_key_static = f'dashboard_static_counts_{request.user.id}'
    # Use Manila timezone for 'today' so attendance recorded in Manila timezone
    cache_key_today = f'dashboard_today_{get_manila_now().date()}_{request.user.id}'
    
    static_data = cache.get(cache_key_static)
    if static_data is None:
        # Filter by user's accessible courses
        accessible_courses = get_user_accessible_courses(request.user)
        
        # Filter students: For advisers, show only students assigned to them
        if request.user.is_superuser or request.user.is_staff:
            students_qs = Student.objects.all()
        elif hasattr(request.user, 'adviser_profile'):
            # Advisers only see their own assigned students
            students_qs = Student.objects.filter(adviser=request.user.adviser_profile)
            # Also filter by accessible courses for additional security
            if accessible_courses.exists():
                students_qs = students_qs.filter(course__in=accessible_courses)
            else:
                students_qs = students_qs.none()
        else:
            students_qs = filter_by_user_courses(Student.objects.all(), request.user)
        
        # Filter subjects by adviser first, then by courses
        subjects_qs = filter_subjects_by_user(request.user)
        subjects_qs = filter_by_user_courses(subjects_qs.filter(is_active=True), request.user, course_field='course')
        
        # Filter instructors by user
        instructors_qs = filter_instructors_by_user(request.user)
        
        static_data = {
            'total_students': students_qs.count(),
            'total_subjects': subjects_qs.count(),
            'total_instructors': instructors_qs.filter(is_active=True).count(),
        }
        cache.set(cache_key_static, static_data, 300)  # 5 minutes
    
    today_data = cache.get(cache_key_today)
    if today_data is None:
        today = get_manila_now().date()
        # Filter attendance by user's own data
        attendance_qs = Attendance.objects.filter(date=today)
        # Use the new helper function to filter by adviser's students
        attendance_qs = filter_by_adviser_students(attendance_qs, request.user, student_field='student')
        
        today_data = {
            'present_today': attendance_qs.filter(status='PRESENT').count(),
            'absent_today': attendance_qs.filter(status='ABSENT').count(),
            'late_today': attendance_qs.filter(status='LATE').count(),
        }
        cache.set(cache_key_today, today_data, 60)  # 1 minute for today's data
    
    settings = SystemSettings.get_settings()
    
    # Get pending enrollment requests count
    # For staff/superuser, show all pending. For advisers, show requests for subjects where instructor belongs to this adviser
    if request.user.is_staff or request.user.is_superuser:
        pending_enrollments = EnrollmentRequest.objects.filter(status='PENDING').count()
    else:
        if hasattr(request.user, 'adviser_profile'):
            # Advisers see enrollment requests only for subjects where instructor belongs to this adviser
            adviser = request.user.adviser_profile
            pending_enrollments = EnrollmentRequest.objects.filter(
                status='PENDING',
                subject__instructor__adviser=adviser
            ).count()
        else:
            pending_enrollments = 0
    
    # Get instructors list for display
    instructors_qs = filter_instructors_by_user(request.user).filter(is_active=True).select_related('adviser').order_by('name')
    
    context = {
        'total_students': static_data['total_students'],
        'total_subjects': static_data['total_subjects'],
        'total_instructors': static_data['total_instructors'],
        'present_today': today_data['present_today'],
        'absent_today': today_data['absent_today'],
        'late_today': today_data['late_today'],
        'last_sync': settings.last_sync,
        'user': request.user,
        'pending_enrollments': pending_enrollments,
        'instructors': instructors_qs,
    }
    return render(request, 'attendance/dashboard.html', context)

# Student Management
@login_required
def student_list(request):
    # Handle POST actions on the student list page (e.g., mark student absent)
    if request.method == 'POST':
        action = request.POST.get('action')
        # Support AJAX detection
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'

        if action == 'make_absent':
            student_id = request.POST.get('student_id')
            try:
                student = Student.objects.get(id=int(student_id))
            except (Student.DoesNotExist, ValueError, TypeError):
                msg = 'Student not found.'
                messages.error(request, msg)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': msg}, status=404)
                return redirect('student_list')

            # Security check: ensure user can access this student
            accessible_courses = get_user_accessible_courses(request.user)
            if not (request.user.is_superuser or request.user.is_staff):
                if not hasattr(request.user, 'adviser_profile'):
                    if student.course not in accessible_courses:
                        msg = "You don't have permission to mark this student absent."
                        messages.error(request, msg)
                        if is_ajax:
                            return JsonResponse({'success': False, 'error': msg}, status=403)
                        return redirect('student_list')

            # Mark absent for each subject the student is enrolled in for today
            today = get_manila_now().date()
            student_subjects = StudentSubject.objects.filter(student=student).select_related('subject')
            # If specific subject IDs were provided from the form, filter to those only
            subject_ids = request.POST.getlist('subject_ids')
            if subject_ids:
                try:
                    subject_ids = [int(s) for s in subject_ids if s]
                    student_subjects = student_subjects.filter(subject__id__in=subject_ids)
                except ValueError:
                    # ignore invalid ids and proceed with full list
                    pass
            created_count = 0
            updated_count = 0
            with transaction.atomic():
                for ss in student_subjects:
                    attendance, created = Attendance.objects.get_or_create(
                        student=student,
                        subject=ss.subject,
                        date=today,
                        defaults={
                            'time_in': None,
                            'status': 'ABSENT',
                            'notes': f"Marked absent by {request.user.get_full_name() or request.user.username}"
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        # If existing attendance is not already marked ABSENT, update it
                        if attendance.status != 'ABSENT':
                            attendance.status = 'ABSENT'
                            attendance.time_in = None
                            attendance.time_out = None
                            note_prefix = f"Marked absent by {request.user.get_full_name() or request.user.username}"
                            if attendance.notes:
                                attendance.notes = attendance.notes + "\n" + note_prefix
                            else:
                                attendance.notes = note_prefix
                            attendance.save(update_fields=['status', 'time_in', 'time_out', 'notes'])
                            updated_count += 1

            total_changed = created_count + updated_count
            if total_changed > 0:
                msg = f"Marked {student.name} absent for {total_changed} subject(s)."
                messages.success(request, msg)
            else:
                msg = f"No changes made. {student.name} already has attendance records for today."
                messages.info(request, msg)

            if is_ajax:
                return JsonResponse({'success': True, 'message': msg})

            # Preserve query params if present when redirecting back
            redirect_url = reverse('student_list')
            adviser_filter = request.POST.get('adviser', '')
            course_filter = request.POST.get('course', '')
            search_query = request.POST.get('search', '')
            search_by = request.POST.get('search_by', '')
            params = []
            if adviser_filter:
                params.append(f'adviser={adviser_filter}')
            if course_filter:
                params.append(f'course={course_filter}')
            if search_query:
                params.append(f'search={search_query}')
            if search_by and search_by != 'all':
                params.append(f'search_by={search_by}')
            if params:
                redirect_url += '?' + '&'.join(params)
            return redirect(redirect_url)
    # Get search parameters
    search_query = request.GET.get('search', '').strip()
    search_by = request.GET.get('search_by', 'all')  # all, name, rfid_id, student_id, course, email, adviser
    course_filter = request.GET.get('course', '')
    adviser_filter = request.GET.get('adviser', '')
    
    # Determine if we should apply course filtering or adviser-based filtering
    # If user is an adviser and filtering by their own name/ID, show their students regardless of course
    current_user_is_adviser = hasattr(request.user, 'adviser_profile')
    current_adviser_id = None
    if current_user_is_adviser:
        current_adviser_id = request.user.adviser_profile.id
    
    # Check if filtering by current user's adviser profile
    filter_by_current_adviser = False
    if adviser_filter and current_adviser_id:
        try:
            filter_adviser_id = int(adviser_filter)
            filter_by_current_adviser = (filter_adviser_id == current_adviser_id)
        except (ValueError, TypeError):
            # Try matching by name
            if request.user.adviser_profile.name.lower() == adviser_filter.lower():
                filter_by_current_adviser = True
    
    # Apply course-based security filtering
    # If filtering by current adviser's own students, include them regardless of course
    if filter_by_current_adviser:
        # Get students from accessible courses OR students assigned to this adviser
        accessible_courses = get_user_accessible_courses(request.user)
        if request.user.is_superuser or request.user.is_staff:
            students = Student.objects.all()
        else:
            students = Student.objects.filter(
                Q(course__in=accessible_courses) | Q(adviser_id=current_adviser_id)
            ).distinct()
    else:
        # Default behavior when no adviser filter is provided:
        # - Superuser/staff: see all students
        # - Adviser: see students assigned to them (regardless of course)
        # - Other users: see students based on accessible courses
        if request.user.is_superuser or request.user.is_staff:
            students = Student.objects.all()
        elif hasattr(request.user, 'adviser_profile'):
            students = Student.objects.filter(adviser=request.user.adviser_profile)
        else:
            students = filter_by_user_courses(Student.objects.all(), request.user)
    
    # Apply search query based on selected search type
    if search_query:
        if search_by == 'all':
            # Search across all fields
            students = students.filter(
                Q(name__icontains=search_query) |
                Q(rfid_id__icontains=search_query) |
                Q(student_id__icontains=search_query) |
                Q(course__code__icontains=search_query) |
                Q(course__name__icontains=search_query) |
                Q(section__code__icontains=search_query) |
                Q(section__name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(adviser__name__icontains=search_query)
            )
        elif search_by == 'name':
            students = students.filter(name__icontains=search_query)
        elif search_by == 'rfid_id':
            students = students.filter(rfid_id__icontains=search_query)
        elif search_by == 'student_id':
            students = students.filter(student_id__icontains=search_query)
        elif search_by == 'course':
            students = students.filter(
                Q(course__code__icontains=search_query) |
                Q(course__name__icontains=search_query)
            )
        elif search_by == 'section':
            students = students.filter(
                Q(section__code__icontains=search_query) |
                Q(section__name__icontains=search_query)
            )
        elif search_by == 'email':
            students = students.filter(email__icontains=search_query)
        elif search_by == 'adviser':
            students = students.filter(adviser__name__icontains=search_query)
    
    # Apply additional filters
    if course_filter:
        try:
            course_id = int(course_filter)
            students = students.filter(course_id=course_id)
        except (ValueError, TypeError):
            students = students.filter(
                Q(course__code__icontains=course_filter) |
                Q(course__name__icontains=course_filter)
            )
    
    # Resolve adviser filter to ID for template use
    resolved_adviser_id = None
    if adviser_filter:
        try:
            # First try to convert to int (ID)
            adviser_id = int(adviser_filter)
            resolved_adviser_id = adviser_id
            students = students.filter(adviser_id=adviser_id)
        except (ValueError, TypeError):
            # If not an ID, try to find adviser by exact name match first
            try:
                adviser_obj = Adviser.objects.get(name__iexact=adviser_filter)
                resolved_adviser_id = adviser_obj.id
                students = students.filter(adviser_id=adviser_obj.id)
            except (Adviser.DoesNotExist, Adviser.MultipleObjectsReturned):
                # If no exact match, fall back to partial name match
                students = students.filter(adviser__name__icontains=adviser_filter)
                # Try to get first matching adviser ID for pre-selection
                matching_advisers = Adviser.objects.filter(name__icontains=adviser_filter)
                if matching_advisers.exists():
                    resolved_adviser_id = matching_advisers.first().id
    
    # Get unique values for filter dropdowns
    # For the add student modal, match the logic from student_add view
    # Advisers see all courses and all advisers (full access)
    if request.user.is_superuser or request.user.is_staff:
        all_courses = Course.objects.filter(is_active=True).order_by('code')
        all_advisers = Adviser.objects.all().order_by('name')
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers have full access to all courses and all advisers
        all_courses = Course.objects.filter(is_active=True).order_by('code')
        all_advisers = Adviser.objects.all().order_by('name')
    else:
        # For other users, use accessible courses
        accessible_courses = get_user_accessible_courses(request.user)
        all_courses = accessible_courses.order_by('code')
        if accessible_courses.exists():
            all_advisers = Adviser.objects.filter(courses__in=accessible_courses).distinct().order_by('name')
        else:
            all_advisers = Adviser.objects.none()
    
    # For the filter dropdowns on the page, use accessible courses
    accessible_courses = get_user_accessible_courses(request.user)
    if request.user.is_superuser or request.user.is_staff:
        filter_courses = Course.objects.filter(is_active=True).order_by('code')
    else:
        filter_courses = accessible_courses.order_by('code')
    
    # Filter advisers by accessible courses for the filter dropdown
    if request.user.is_superuser or request.user.is_staff:
        filter_advisers = Adviser.objects.all().order_by('name')
    else:
        if accessible_courses.exists():
            filter_advisers = Adviser.objects.filter(courses__in=accessible_courses).distinct().order_by('name')
        else:
            filter_advisers = Adviser.objects.none()
    
    total_count = students.count()
    
    # Check if we need to highlight a specific student (from URL parameter)
    highlight_student_id = request.GET.get('highlight')
    
    paginator = Paginator(students, 25)
    page_number = request.GET.get('page')
    
    # If highlighting a student, find which page they're on
    if highlight_student_id:
        try:
            highlight_student = Student.objects.get(id=int(highlight_student_id))
            # Check if the student is in the filtered queryset
            student_position = list(students.values_list('id', flat=True)).index(highlight_student.id) if highlight_student.id in students.values_list('id', flat=True) else None
            if student_position is not None:
                # Calculate which page the student is on (0-indexed position / items per page + 1)
                page_number = (student_position // 25) + 1
        except (Student.DoesNotExist, ValueError, TypeError):
            pass
    
    page_obj = paginator.get_page(page_number)
    
    sections = Section.objects.filter(is_active=True).order_by('code')
    
    # Get current user's adviser ID if they are an adviser
    current_adviser_id = None
    if hasattr(request.user, 'adviser_profile'):
        current_adviser_id = request.user.adviser_profile.id
    
    # Build query string for preserving filters in edit links
    query_parts = []
    if adviser_filter:
        query_parts.append(f'adviser={adviser_filter}')
    if course_filter:
        query_parts.append(f'course={course_filter}')
    if search_query:
        query_parts.append(f'search={search_query}')
    if search_by and search_by != 'all':
        query_parts.append(f'search_by={search_by}')
    query_string = '&'.join(query_parts) if query_parts else ''
    if query_string:
        query_string = '?' + query_string
    
    context = {
        'students': page_obj,
        'search_query': search_query,
        'search_by': search_by,
        'course_filter': course_filter,
        'adviser_filter': adviser_filter,
        'resolved_adviser_id': resolved_adviser_id,  # Add resolved adviser ID for pre-selection
        'current_adviser_id': current_adviser_id,  # Current user's adviser ID for auto-selection
        'total_count': total_count,
        'all_courses': all_courses,  # All courses for add modal
        'all_advisers': all_advisers,  # All advisers for add modal
        'filter_courses': filter_courses,  # Filtered courses for filter dropdown
        'filter_advisers': filter_advisers,  # Filtered advisers for filter dropdown
        'sections': sections,
        'query_string': query_string,  # Query string for edit links
    }
    return render(request, 'attendance/student_list.html', context)

@login_required
def student_add(request):
    if request.method == 'POST':
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'
        
        try:
            adviser_id = request.POST.get('adviser', '')
            adviser_obj = None
            if adviser_id:
                try:
                    adviser_obj = Adviser.objects.get(id=int(adviser_id))
                except (Adviser.DoesNotExist, ValueError):
                    pass
            
            # Get course object
            course_id = request.POST.get('course', '')
            course_obj = None
            if course_id:
                try:
                    course_obj = Course.objects.get(id=int(course_id), is_active=True)
                    # Security check: ensure user can assign to this course
                    # Advisers can assign students to any active course
                    if not (request.user.is_superuser or request.user.is_staff):
                        if not hasattr(request.user, 'adviser_profile'):
                            # For other users (not advisers), check accessible courses
                            accessible_courses = get_user_accessible_courses(request.user)
                            if course_obj not in accessible_courses:
                                error_msg = "You don't have permission to assign students to this course."
                                messages.error(request, error_msg)
                                if is_ajax:
                                    return JsonResponse({'success': False, 'error': error_msg}, status=403)
                                return redirect('student_add')
                except (Course.DoesNotExist, ValueError):
                    error_msg = "Invalid course selected."
                    messages.error(request, error_msg)
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    return redirect('student_add')
            else:
                error_msg = "Course is required."
                messages.error(request, error_msg)
                if is_ajax:
                    return JsonResponse({'success': False, 'error': error_msg}, status=400)
                return redirect('student_add')
            
            # Get section object
            section_id = request.POST.get('section', '')
            section_obj = None
            if section_id:
                try:
                    section_obj = Section.objects.get(id=int(section_id), is_active=True)
                except (Section.DoesNotExist, ValueError):
                    error_msg = "Invalid section selected."
                    messages.error(request, error_msg)
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    return redirect('student_add')
            else:
                # Default to first active section if none selected
                section_obj = Section.objects.filter(is_active=True).first()
                if not section_obj:
                    error_msg = "No active sections available. Please create a section first."
                    messages.error(request, error_msg)
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    return redirect('section_add')
            
            student = Student.objects.create(
                rfid_id=request.POST.get('rfid_id'),
                student_id=request.POST.get('student_id', ''),
                name=request.POST.get('name'),
                course=course_obj,
                section=section_obj,
                email=request.POST.get('email'),
                adviser=adviser_obj,
            )
            
            # Send confirmation email to the student
            try:
                email_subject = "Welcome to Attendance RFID Monitoring System"
                masked_email = mask_email(student.email)
                email_body = f"""Dear {student.name},

Welcome! You have been successfully added to the Attendance RFID Monitoring System.

Your account details:
- Name: {student.name}
- Email: {masked_email}
- RFID ID: {student.rfid_id}
- Student ID: {student.student_id if student.student_id else 'Not provided'}
- Course: {student.course.name if student.course else 'Not assigned'}
- Section: {student.get_section_display() if student.section else 'Not assigned'}
- Adviser: {student.adviser.name if student.adviser else 'Not assigned'}

You can now use your RFID card to track your attendance in the system.

If you have any questions, please contact your adviser or system administrator.

Thank you!

Best regards,
Attendance RFID Monitoring System"""
                
                send_attendance_email(
                    student=student,
                    email_to=student.email,
                    subject=email_subject,
                    message_body=email_body,
                    email_type='CUSTOM',
                    silent=False
                )
                messages.success(request, f"Student {student.name} added successfully! Confirmation email sent to {student.email}.")
            except Exception as email_error:
                # Log email error but don't fail student creation
                logger.error(f"Failed to send confirmation email to {student.email}: {str(email_error)}")
                messages.success(request, f"Student {student.name} added successfully! However, the confirmation email could not be sent.")
            
            # Preserve adviser filter if present in GET parameters
            redirect_url = reverse('student_list')
            adviser_filter = request.GET.get('adviser', '')
            if adviser_filter:
                redirect_url += f'?adviser={adviser_filter}'
            
            # Return JSON response for AJAX requests
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': f"Student {student.name} added successfully! Confirmation email sent to {student.email}.",
                    'redirect_url': redirect_url
                })
            
            return redirect(redirect_url)
        except Exception as e:
            error_msg = f"Error adding student: {str(e)}"
            messages.error(request, error_msg)
            logger.error(f"Error in student_add: {str(e)}", exc_info=True)
            
            # Return JSON response for AJAX requests on error
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'
            if is_ajax:
                return JsonResponse({'success': False, 'error': error_msg}, status=500)
    
    # Get accessible courses and advisers for the form
    # Advisers have full access to all courses and all advisers
    default_course_id = None
    if request.user.is_superuser or request.user.is_staff:
        all_courses = Course.objects.filter(is_active=True).order_by('code')
        advisers = Adviser.objects.all().order_by('name')
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers have full access to all courses and all advisers
        all_courses = Course.objects.filter(is_active=True).order_by('code')
        advisers = Adviser.objects.all().order_by('name')
        # Auto-select if adviser has only one assigned course
        adviser = request.user.adviser_profile
        adviser_courses = adviser.courses.filter(is_active=True)
        if adviser_courses.count() == 1:
            default_course_id = adviser_courses.first().id
    else:
        # For other users, use restrictive filtering
        accessible_courses = get_user_accessible_courses(request.user)
        all_courses = accessible_courses.order_by('code')
        if accessible_courses.exists():
            advisers = Adviser.objects.filter(courses__in=accessible_courses).distinct().order_by('name')
        else:
            advisers = Adviser.objects.none()
    
    sections = Section.objects.filter(is_active=True).order_by('code')
    
    return render(request, 'attendance/student_form.html', {
        'action': 'Add', 
        'advisers': advisers,
        'courses': all_courses,
        'sections': sections,
        'default_course_id': default_course_id,
    })

@login_required
def student_edit(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    
    # Security check: ensure user can access this student
    # Advisers have full access to all students
    accessible_courses = get_user_accessible_courses(request.user)
    if not (request.user.is_superuser or request.user.is_staff):
        # Advisers can access all students, so skip course check for them
        if not hasattr(request.user, 'adviser_profile'):
            if student.course not in accessible_courses:
                messages.error(request, "You don't have permission to edit this student.")
                return redirect('student_list')
    
    # Get query parameters to preserve filters (from GET or POST)
    query_params = {}
    if request.method == 'GET':
        # Preserve query parameters from the edit page URL
        for key in ['adviser', 'course', 'search', 'search_by', 'page']:
            if key in request.GET:
                query_params[key] = request.GET.get(key)
    elif request.method == 'POST':
        # Get query parameters from hidden form fields or referrer
        for key in ['adviser', 'course', 'search', 'search_by', 'page']:
            if key in request.POST:
                query_params[key] = request.POST.get(key)
    
    if request.method == 'POST':
        try:
            student.rfid_id = request.POST.get('rfid_id')
            student.student_id = request.POST.get('student_id', '')
            student.name = request.POST.get('name')
            
            # Get section object
            section_id = request.POST.get('section', '')
            if section_id:
                try:
                    section_obj = Section.objects.get(id=int(section_id), is_active=True)
                    student.section = section_obj
                except (Section.DoesNotExist, ValueError):
                    messages.error(request, "Invalid section selected.")
                    return redirect('student_edit', student_id=student_id)
            else:
                messages.error(request, "Section is required.")
                return redirect('student_edit', student_id=student_id)
            
            # Get course object
            course_id = request.POST.get('course', '')
            if course_id:
                try:
                    course_obj = Course.objects.get(id=int(course_id), is_active=True)
                    # Security check: ensure user can assign to this course
                    # Advisers have full access to assign students to any active course
                    if not (request.user.is_superuser or request.user.is_staff):
                        if not hasattr(request.user, 'adviser_profile'):
                            if course_obj not in accessible_courses:
                                messages.error(request, "You don't have permission to assign students to this course.")
                                return redirect('student_edit', student_id=student_id)
                    student.course = course_obj
                except (Course.DoesNotExist, ValueError):
                    messages.error(request, "Invalid course selected.")
                    return redirect('student_edit', student_id=student_id)
            else:
                messages.error(request, "Course is required.")
                return redirect('student_edit', student_id=student_id)
            
            student.email = request.POST.get('email')
            adviser_id = request.POST.get('adviser', '')
            adviser_obj = None
            if adviser_id:
                try:
                    adviser_obj = Adviser.objects.get(id=int(adviser_id))
                except (Adviser.DoesNotExist, ValueError):
                    pass
            student.adviser = adviser_obj
            student.save()
            messages.success(request, f"Student {student.name} updated successfully!")
            
            # Preserve query parameters in redirect
            redirect_url = reverse('student_list')
            if query_params:
                query_string = '&'.join([f'{k}={v}' for k, v in query_params.items() if v])
                if query_string:
                    redirect_url += f'?{query_string}'
            
            return redirect(redirect_url)
        except Exception as e:
            messages.error(request, f"Error updating student: {str(e)}")
    
    # Get accessible courses and advisers for the form
    # Advisers have full access to all courses and all advisers
    default_course_id = None
    if request.user.is_superuser or request.user.is_staff:
        all_courses = Course.objects.filter(is_active=True).order_by('code')
        advisers = Adviser.objects.all().order_by('name')
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers have full access to all courses and all advisers
        all_courses = Course.objects.filter(is_active=True).order_by('code')
        advisers = Adviser.objects.all().order_by('name')
        # Auto-select if adviser has only one assigned course and student doesn't have one yet
        adviser = request.user.adviser_profile
        adviser_courses = adviser.courses.filter(is_active=True)
        if adviser_courses.count() == 1 and not student.course:
            default_course_id = adviser_courses.first().id
    else:
        all_courses = accessible_courses.order_by('code')
        if accessible_courses.exists():
            advisers = Adviser.objects.filter(courses__in=accessible_courses).distinct().order_by('name')
        else:
            advisers = Adviser.objects.none()
    
    sections = Section.objects.filter(is_active=True).order_by('code')
    
    # Build query string for cancel link and hidden fields
    query_string = ''
    if query_params:
        query_string = '&'.join([f'{k}={v}' for k, v in query_params.items() if v])
        if query_string:
            query_string = '?' + query_string
    
    return render(request, 'attendance/student_form.html', {
        'student': student, 
        'action': 'Edit', 
        'advisers': advisers,
        'courses': all_courses,
        'sections': sections,
        'default_course_id': default_course_id,
        'query_params': query_params,
        'query_string': query_string,
    })

@login_required
def student_delete(request, student_id):
    # Get query parameters to preserve filters
    query_params = {}
    if request.method == 'POST':
        # Get query parameters from hidden form fields
        for key in ['adviser', 'course', 'search', 'search_by', 'page']:
            if key in request.POST:
                query_params[key] = request.POST.get(key)
    
    if request.method == 'POST':
        student = get_object_or_404(Student, id=student_id)
        student_name = student.name
        student.delete()
        messages.success(request, f"Student {student_name} deleted successfully!")
    
    # Preserve query parameters in redirect
    redirect_url = reverse('student_list')
    if query_params:
        query_string = '&'.join([f'{k}={v}' for k, v in query_params.items() if v])
        if query_string:
            redirect_url += f'?{query_string}'
    
    return redirect(redirect_url)

@login_required
def student_import_csv(request):
    if request.method == 'POST':
        if 'csv_file' in request.FILES:
            try:
                csv_file = request.FILES['csv_file']
                decoded_file = csv_file.read().decode('utf-8').splitlines()
                reader = csv.DictReader(decoded_file)
                
                imported = 0
                errors = []
                
                for idx, row in enumerate(reader, start=2):
                    try:
                        if not row.get('rfid_id') or not row.get('name'):
                            errors.append(f"Row {idx}: Missing required fields")
                            continue
                        adviser_name = row.get('adviser', '').strip()
                        adviser_obj = None
                        if adviser_name:
                            # Try to find adviser by name or email
                            try:
                                adviser_obj = Adviser.objects.filter(
                                    Q(name__iexact=adviser_name) | Q(email__iexact=adviser_name)
                                ).first()
                            except Exception:
                                pass
                        
                        # Get course by code or name
                        course_code = row.get('course', '').strip()
                        course_obj = None
                        if course_code:
                            try:
                                course_obj = Course.objects.filter(
                                    Q(code__iexact=course_code) | Q(name__iexact=course_code)
                                ).first()
                                if not course_obj:
                                    errors.append(f"Row {idx}: Course '{course_code}' not found")
                                    continue
                                # Security check: ensure user can assign to this course
                                accessible_courses = get_user_accessible_courses(request.user)
                                if not (request.user.is_superuser or request.user.is_staff):
                                    if course_obj not in accessible_courses:
                                        errors.append(f"Row {idx}: No permission to assign to course '{course_code}'")
                                        continue
                            except Exception as e:
                                errors.append(f"Row {idx}: Error finding course: {str(e)}")
                                continue
                        else:
                            errors.append(f"Row {idx}: Course is required")
                            continue
                        
                        Student.objects.get_or_create(
                            rfid_id=row.get('rfid_id', '').strip(),
                            defaults={
                                'student_id': row.get('student_id', '').strip(),
                                'name': row.get('name', '').strip(),
                                'course': course_obj,
                                'email': row.get('email', '').strip(),
                                'adviser': adviser_obj,
                            }
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx}: {str(e)}")
                
                messages.success(request, f"Imported {imported} students successfully!")
                if errors:
                    messages.warning(request, f"Some errors occurred: {len(errors)} rows failed.")
            except Exception as e:
                messages.error(request, f"Error importing CSV: {str(e)}")
        else:
            messages.error(request, "No CSV file provided.")
    
    return redirect('student_list')

@login_required
def student_export_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="students_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['RFID ID', 'Student ID', 'Name', 'Course Code', 'Course Name', 'Email', 'Adviser'])
    
    # Filter students using the same logic as student_list view
    if request.user.is_superuser or request.user.is_staff:
        # Admin/staff can see all students
        students = Student.objects.all()
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers see their assigned students
        adviser = request.user.adviser_profile
        accessible_courses = get_user_accessible_courses(request.user)
        if accessible_courses.exists():
            # Include students from accessible courses OR assigned to this adviser
            students = Student.objects.filter(
                Q(course__in=accessible_courses) | Q(adviser=adviser)
            ).distinct()
        else:
            # If no accessible courses, show only adviser's students
            students = Student.objects.filter(adviser=adviser)
    else:
        # Other users filter by accessible courses
        students = filter_by_user_courses(Student.objects.all(), request.user)
    
    # Write data rows
    for student in students:
        writer.writerow([
            student.rfid_id or '',
            student.student_id or '',
            student.name or '',
            student.course.code if student.course else '',
            student.course.name if student.course else '',
            student.email or '',
            student.adviser.name if student.adviser else '',
        ])
    
    return response

# Subject Management
@login_required
def subject_list(request):
    # If user is an adviser, show the adviser features view instead
    if hasattr(request.user, 'adviser_profile') and not (request.user.is_staff or request.user.is_superuser):
        return adviser_features_view(request)
    
    search_query = request.GET.get('search', '').strip()
    instructor_filter = request.GET.get('instructor', '').strip()
    student_search = request.GET.get('student_search', '').strip()  # Search by enrolled student name
    
    # Filter subjects by user: advisers only see subjects registered to them
    subjects = filter_subjects_by_user(request.user)
    
    # Apply course-based security filtering for additional security
    subjects = filter_by_user_courses(subjects, request.user, course_field='course')
    
    # Annotate subjects with enrolled student count and prefetch related data
    subjects = subjects.prefetch_related(
        'schedules',
        'students__student'  # Prefetch enrolled students through StudentSubject
    ).annotate(
        enrolled_count=Count('students', distinct=True)
    )
    
    # Filter by subject code or name
    if search_query:
        subjects = subjects.filter(
            Q(code__icontains=search_query) |
            Q(name__icontains=search_query)
        )
    
    # Filter by instructor
    if instructor_filter:
        subjects = subjects.filter(
            Q(instructor__name__icontains=instructor_filter) |
            Q(instructor__email__icontains=instructor_filter) |
            Q(instructor__employee_id__icontains=instructor_filter)
        )
    
    # Filter by enrolled student name (find subjects where student is enrolled)
    if student_search:
        subjects = subjects.filter(
            students__student__name__icontains=student_search
        ).distinct()
    
    # Get instructors from accessible subjects for dropdown
    # For advisers, only show instructors from subjects registered to them
    accessible_subjects_for_instructors = filter_subjects_by_user(request.user)
    
    # Get unique instructors for filter dropdown (exclude None values)
    instructor_ids = accessible_subjects_for_instructors.exclude(instructor__isnull=True).values_list('instructor', flat=True).distinct()
    from .models import Instructor
    instructors = Instructor.objects.filter(id__in=instructor_ids).order_by('name')
    
    context = {
        'subjects': subjects,
        'search_query': search_query,
        'instructor_filter': instructor_filter,
        'student_search': student_search,
        'instructors': instructors,
    }
    return render(request, 'attendance/subject_list.html', context)

@login_required
def subject_add(request):
    # Determine the adviser for this subject
    adviser_obj = None
    if hasattr(request.user, 'adviser_profile'):
        adviser_obj = request.user.adviser_profile
    elif not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "You don't have permission to create subjects.")
        return redirect('subject_list')
    
    if request.method == 'POST':
        try:
            # Get form data
            code = request.POST.get('code', '').strip()
            name = request.POST.get('name', '').strip()
            instructor_input = request.POST.get('instructor', '').strip()
            schedule_days = request.POST.get('schedule_days', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not code or not name or not instructor_input:
                messages.error(request, "Code, Name, and Instructor are required fields.")
                return redirect('subject_add')
            
            # Get adviser for superusers/staff (if not already set) - must be done first
            if not adviser_obj and (request.user.is_superuser or request.user.is_staff):
                adviser_id = request.POST.get('adviser', '').strip()
                if adviser_id:
                    try:
                        adviser_obj = Adviser.objects.get(id=int(adviser_id))
                    except (Adviser.DoesNotExist, ValueError):
                        messages.error(request, "Invalid adviser selected.")
                        return redirect('subject_add')
                else:
                    messages.error(request, "Adviser is required.")
                    return redirect('subject_add')
            
            # Get or create instructor
            instructor_obj = None
            try:
                # Try to get by ID first (if it's an existing instructor)
                if adviser_obj:
                    # For advisers, filter by their adviser
                    instructor_obj = Instructor.objects.get(id=int(instructor_input), adviser=adviser_obj)
                else:
                    # For superusers/staff, search across all instructors
                    instructor_obj = Instructor.objects.get(id=int(instructor_input))
            except (ValueError, Instructor.DoesNotExist):
                # If not found by ID, try to find by name
                if adviser_obj:
                    # For advisers, search within their instructors
                    instructor_obj = Instructor.objects.filter(name__iexact=instructor_input, adviser=adviser_obj).first()
                else:
                    # For superusers/staff, search across all instructors
                    instructor_obj = Instructor.objects.filter(name__iexact=instructor_input, is_active=True).first()
                
                # If still not found, try to create new instructor
                if not instructor_obj:
                    if adviser_obj:
                        # Can create new instructor if we have an adviser
                        instructor_obj = Instructor.objects.create(
                            name=instructor_input,
                            adviser=adviser_obj
                        )
                        messages.info(request, f"Created new instructor: {instructor_obj.name}")
                    else:
                        # For superusers/staff without adviser context, cannot create new instructor
                        messages.error(request, f"Instructor '{instructor_input}' not found. Please select an existing instructor from the list, or create the instructor through an adviser account first.")
                        return redirect('subject_add')
            
            if not instructor_obj:
                messages.error(request, "Could not create or find instructor.")
                return redirect('subject_add')
            
            # Get course object (optional)
            course_obj = None
            course_id = request.POST.get('course', '').strip()
            if course_id:
                try:
                    course_obj = Course.objects.get(id=int(course_id))
                    # Security check: ensure user can assign to this course
                    accessible_courses = get_user_accessible_courses(request.user)
                    if not (request.user.is_superuser or request.user.is_staff):
                        if course_obj not in accessible_courses:
                            messages.error(request, "You don't have permission to assign subjects to this course.")
                            return redirect('subject_add')
                except (Course.DoesNotExist, ValueError):
                    messages.error(request, "Invalid course selected.")
                    return redirect('subject_add')
            
            # Get course code and course number (optional)
            course_code = request.POST.get('course_code', '').strip()
            course_number = request.POST.get('course_number', '').strip()
            
            # Create subject with adviser
            subject = Subject.objects.create(
                code=code,
                name=name,
                instructor=instructor_obj,
                adviser=adviser_obj,  # Assign the adviser (or None)
                course=course_obj,
                course_code=course_code,
                course_number=course_number,
                schedule_days=schedule_days,
                schedule_time_start=None,  # Will be set from first schedule entry if available
                schedule_time_end=None,     # Will be set from first schedule entry if available
                is_active=is_active,
            )
            
            # Handle weekly schedule entries (day of week and time)
            schedule_days_list = request.POST.getlist('schedule_day[]')
            schedule_time_starts = request.POST.getlist('schedule_time_start[]')
            schedule_time_ends = request.POST.getlist('schedule_time_end[]')
            
            schedule_created_count = 0
            first_schedule_start = None
            first_schedule_end = None
            
            for i, schedule_day in enumerate(schedule_days_list):
                if schedule_day and i < len(schedule_time_starts) and i < len(schedule_time_ends):
                    try:
                        day_of_week = int(schedule_day)
                        time_start_str = schedule_time_starts[i].strip()
                        time_end_str = schedule_time_ends[i].strip()
                        
                        if not time_start_str or not time_end_str:
                            continue
                        
                        # Parse time strings - handle both HH:MM and HH:MM:SS formats
                        try:
                            if len(time_start_str.split(':')) == 2:
                                time_start_obj = datetime.strptime(time_start_str, '%H:%M').time()
                            else:
                                time_start_obj = datetime.strptime(time_start_str, '%H:%M:%S').time()
                        except ValueError:
                            messages.warning(request, f"Invalid start time format: {time_start_str}. Use HH:MM format.")
                            continue
                        
                        try:
                            if len(time_end_str.split(':')) == 2:
                                time_end_obj = datetime.strptime(time_end_str, '%H:%M').time()
                            else:
                                time_end_obj = datetime.strptime(time_end_str, '%H:%M:%S').time()
                        except ValueError:
                            messages.warning(request, f"Invalid end time format: {time_end_str}. Use HH:MM format.")
                            continue
                        
                        # Validate that start time is before end time
                        if time_start_obj >= time_end_obj:
                            messages.warning(request, f"Start time ({time_start_str}) must be before end time ({time_end_str}).")
                            continue
                        
                        # Store first schedule times for fallback on Subject model
                        if first_schedule_start is None:
                            first_schedule_start = time_start_obj
                            first_schedule_end = time_end_obj
                        
                        SubjectSchedule.objects.create(
                            subject=subject,
                            day_of_week=day_of_week,
                            time_start=time_start_obj,
                            time_end=time_end_obj,
                            date=None  # Weekly schedule, not specific date
                        )
                        schedule_created_count += 1
                    except (ValueError, IndexError, TypeError) as e:
                        # Skip invalid entries but log for debugging
                        messages.warning(request, f"Skipped invalid schedule entry: {str(e)}")
                        continue
            
            # Set general schedule times on Subject model as fallback (from first schedule entry)
            if first_schedule_start and first_schedule_end:
                subject.schedule_time_start = first_schedule_start
                subject.schedule_time_end = first_schedule_end
                subject.save(update_fields=['schedule_time_start', 'schedule_time_end'])
            
            if schedule_created_count > 0:
                messages.success(request, f"Subject {subject.code} added successfully with {schedule_created_count} schedule entry/entries!")
            else:
                messages.warning(request, f"Subject {subject.code} added, but no valid schedule entries were created. Please add schedules for proper date identification.")
            
            return redirect('subject_list')
        except Exception as e:
            messages.error(request, f"Error adding subject: {str(e)}")
    
    # Get instructors for dropdown - show instructors designated to this adviser
    if request.user.is_superuser or request.user.is_staff:
        instructors = Instructor.objects.filter(is_active=True).order_by('name')
    elif hasattr(request.user, 'adviser_profile'):
        instructors = Instructor.objects.filter(adviser=request.user.adviser_profile, is_active=True).order_by('name')
    else:
        instructors = Instructor.objects.none()
    
    # Get existing values from database for dropdowns - filter by adviser or show all for admin
    if request.user.is_superuser or request.user.is_staff:
        accessible_subjects = Subject.objects.all()
    elif hasattr(request.user, 'adviser_profile'):
        accessible_subjects = Subject.objects.filter(adviser=request.user.adviser_profile)
    else:
        accessible_subjects = Subject.objects.none()
    
    codes = accessible_subjects.values_list('code', flat=True).distinct().order_by('code')
    names = accessible_subjects.values_list('name', flat=True).distinct().order_by('name')
    
    # Create a mapping of code to name for auto-fill functionality
    code_to_name = dict(accessible_subjects.values_list('code', 'name'))
    code_to_name_json = json.dumps(code_to_name)
    
    # Get accessible courses for the form
    accessible_courses = get_user_accessible_courses(request.user)
    if request.user.is_superuser or request.user.is_staff:
        all_courses = Course.objects.filter(is_active=True).order_by('code')
    else:
        all_courses = accessible_courses.order_by('code')
    
    # Get advisers for superusers/staff to select
    advisers = None
    if request.user.is_superuser or request.user.is_staff:
        advisers = Adviser.objects.all().order_by('name')
    
    return render(request, 'attendance/subject_form.html', {
        'action': 'Add',
        'instructors': instructors,
        'codes': codes,
        'names': names,
        'courses': all_courses,
        'advisers': advisers,
        'code_to_name_json': code_to_name_json,
        'is_superuser_or_staff': request.user.is_superuser or request.user.is_staff,
    })

@login_required
def subject_edit(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    
    # Security check: ensure user can access this subject
    # Advisers can only edit subjects registered to them
    if request.user.is_superuser or request.user.is_staff:
        # Admin/staff can edit any subject
        pass
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers can only edit subjects registered to them
        if not subject.adviser or subject.adviser != request.user.adviser_profile:
            messages.error(request, "You don't have permission to edit this subject. You can only edit subjects registered to you.")
            return redirect('subject_list')
    else:
        messages.error(request, "You don't have permission to edit subjects.")
        return redirect('subject_list')
    
    # Additional course-based check
    accessible_courses = get_user_accessible_courses(request.user)
    if not (request.user.is_superuser or request.user.is_staff):
        if subject.course and subject.course not in accessible_courses:
            messages.error(request, "You don't have permission to edit this subject.")
            return redirect('subject_list')
    
    if request.method == 'POST':
        try:
            # Get form data
            code = request.POST.get('code', '').strip()
            name = request.POST.get('name', '').strip()
            instructor_input = request.POST.get('instructor', '').strip()
            schedule_days = request.POST.get('schedule_days', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not code or not name or not instructor_input:
                messages.error(request, "Code, Name, and Instructor are required fields.")
                return redirect('subject_edit', subject_id=subject_id)
            
            # Get or create instructor
            instructor_obj = None
            adviser_obj = subject.adviser
            try:
                # Try to get by ID first (if it's an existing instructor)
                instructor_obj = Instructor.objects.get(id=int(instructor_input), adviser=adviser_obj)
            except (ValueError, Instructor.DoesNotExist):
                # If not found by ID, try to find by name for this adviser
                instructor_obj = Instructor.objects.filter(name__iexact=instructor_input, adviser=adviser_obj).first()
                
                # If still not found, create new instructor
                if not instructor_obj:
                    instructor_obj = Instructor.objects.create(
                        name=instructor_input,
                        adviser=adviser_obj
                    )
                    messages.info(request, f"Created new instructor: {instructor_obj.name}")
            
            if not instructor_obj:
                messages.error(request, "Could not create or find instructor.")
                return redirect('subject_edit', subject_id=subject_id)
            
            # Get course object (optional)
            course_obj = None
            course_id = request.POST.get('course', '').strip()
            if course_id:
                try:
                    course_obj = Course.objects.get(id=int(course_id))
                    # Security check: ensure user can assign to this course
                    if not (request.user.is_superuser or request.user.is_staff):
                        if course_obj not in accessible_courses:
                            messages.error(request, "You don't have permission to assign subjects to this course.")
                            return redirect('subject_edit', subject_id=subject_id)
                except (Course.DoesNotExist, ValueError):
                    messages.error(request, "Invalid course selected.")
                    return redirect('subject_edit', subject_id=subject_id)
            
            # Get course code and course number (optional)
            course_code = request.POST.get('course_code', '').strip()
            course_number = request.POST.get('course_number', '').strip()
            
            # Update subject basic info
            subject.code = code
            subject.name = name
            subject.instructor = instructor_obj
            subject.course = course_obj
            subject.course_code = course_code
            subject.course_number = course_number
            subject.schedule_days = schedule_days
            subject.is_active = is_active
            
            # Delete existing schedule entries and create new ones
            SubjectSchedule.objects.filter(subject=subject).delete()
            
            # Handle weekly schedule entries (day of week and time)
            schedule_days_list = request.POST.getlist('schedule_day[]')
            schedule_time_starts = request.POST.getlist('schedule_time_start[]')
            schedule_time_ends = request.POST.getlist('schedule_time_end[]')
            
            schedule_created_count = 0
            first_schedule_start = None
            first_schedule_end = None
            
            for i, schedule_day in enumerate(schedule_days_list):
                if schedule_day and i < len(schedule_time_starts) and i < len(schedule_time_ends):
                    try:
                        day_of_week = int(schedule_day)
                        time_start_str = schedule_time_starts[i].strip()
                        time_end_str = schedule_time_ends[i].strip()
                        
                        if not time_start_str or not time_end_str:
                            continue
                        
                        # Parse time strings - handle both HH:MM and HH:MM:SS formats
                        try:
                            if len(time_start_str.split(':')) == 2:
                                time_start_obj = datetime.strptime(time_start_str, '%H:%M').time()
                            else:
                                time_start_obj = datetime.strptime(time_start_str, '%H:%M:%S').time()
                        except ValueError:
                            messages.warning(request, f"Invalid start time format: {time_start_str}. Use HH:MM format.")
                            continue
                        
                        try:
                            if len(time_end_str.split(':')) == 2:
                                time_end_obj = datetime.strptime(time_end_str, '%H:%M').time()
                            else:
                                time_end_obj = datetime.strptime(time_end_str, '%H:%M:%S').time()
                        except ValueError:
                            messages.warning(request, f"Invalid end time format: {time_end_str}. Use HH:MM format.")
                            continue
                        
                        # Validate that start time is before end time
                        if time_start_obj >= time_end_obj:
                            messages.warning(request, f"Start time ({time_start_str}) must be before end time ({time_end_str}).")
                            continue
                        
                        # Store first schedule times for fallback on Subject model
                        if first_schedule_start is None:
                            first_schedule_start = time_start_obj
                            first_schedule_end = time_end_obj
                        
                        SubjectSchedule.objects.create(
                            subject=subject,
                            day_of_week=day_of_week,
                            time_start=time_start_obj,
                            time_end=time_end_obj,
                            date=None  # Weekly schedule, not specific date
                        )
                        schedule_created_count += 1
                    except (ValueError, IndexError, TypeError) as e:
                        # Skip invalid entries but log for debugging
                        messages.warning(request, f"Skipped invalid schedule entry: {str(e)}")
                        continue
            
            # Set general schedule times on Subject model as fallback (from first schedule entry)
            if first_schedule_start and first_schedule_end:
                subject.schedule_time_start = first_schedule_start
                subject.schedule_time_end = first_schedule_end
            else:
                # If no schedules, clear the fallback times
                subject.schedule_time_start = None
                subject.schedule_time_end = None
            
            subject.save()
            
            if schedule_created_count > 0:
                messages.success(request, f"Subject {subject.code} updated successfully with {schedule_created_count} schedule entry/entries!")
            else:
                messages.warning(request, f"Subject {subject.code} updated, but no valid schedule entries were created. Please add schedules for proper date identification.")
            
            return redirect('subject_list')
        except Exception as e:
            messages.error(request, f"Error updating subject: {str(e)}")
    
    # Get instructors for dropdown - show instructors designated to this adviser
    if request.user.is_superuser or request.user.is_staff:
        instructors = Instructor.objects.filter(is_active=True).order_by('name')
    elif hasattr(request.user, 'adviser_profile'):
        instructors = Instructor.objects.filter(adviser=request.user.adviser_profile, is_active=True).order_by('name')
    else:
        instructors = Instructor.objects.none()
    
    # Get existing values for code/name dropdowns
    if request.user.is_superuser or request.user.is_staff:
        accessible_subjects = Subject.objects.all()
    elif hasattr(request.user, 'adviser_profile'):
        accessible_subjects = Subject.objects.filter(adviser=request.user.adviser_profile)
    else:
        accessible_subjects = Subject.objects.none()
    
    codes = accessible_subjects.values_list('code', flat=True).distinct().order_by('code')
    names = accessible_subjects.values_list('name', flat=True).distinct().order_by('name')
    
    # Create a mapping of code to name for auto-fill functionality
    code_to_name = dict(accessible_subjects.values_list('code', 'name'))
    code_to_name_json = json.dumps(code_to_name)
    
    # Get accessible courses for the form
    accessible_courses = get_user_accessible_courses(request.user)
    if request.user.is_superuser or request.user.is_staff:
        all_courses = Course.objects.filter(is_active=True).order_by('code')
    else:
        all_courses = accessible_courses.order_by('code')
    
    return render(request, 'attendance/subject_form.html', {
        'subject': subject,
        'action': 'Edit',
        'instructors': instructors,
        'codes': codes,
        'names': names,
        'courses': all_courses,
        'code_to_name_json': code_to_name_json,
    })

@login_required
def subject_delete(request, subject_id):
    if request.method == 'POST':
        subject = get_object_or_404(Subject, id=subject_id)
        
        # Security check: ensure user can delete this subject
        # Advisers can only delete their own subjects, admin can delete all
        if request.user.is_superuser or request.user.is_staff:
            # Admin/staff can delete any subject
            pass
        elif hasattr(request.user, 'adviser_profile'):
            # Advisers can only delete subjects registered to them
            if not subject.adviser or subject.adviser != request.user.adviser_profile:
                messages.error(request, "You don't have permission to delete this subject. You can only delete subjects registered to you.")
                return redirect('subject_list')
        else:
            messages.error(request, "You don't have permission to delete subjects.")
            return redirect('subject_list')
        
        subject_code = subject.code
        subject.delete()
        messages.success(request, f"Subject {subject_code} deleted successfully!")
    return redirect('subject_list')

@login_required
def assign_students_to_subject(request, subject_id):
    subject = get_object_or_404(Subject, id=subject_id)
    
    # Security check: ensure user can access this subject
    # Advisers can only assign students to their own subjects, admin can assign to all
    if request.user.is_superuser or request.user.is_staff:
        # Admin/staff can assign to any subject
        pass
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers can only assign to subjects registered to them
        if not subject.adviser or subject.adviser != request.user.adviser_profile:
            messages.error(request, "You don't have permission to assign students to this subject. You can only assign students to subjects registered to you.")
            return redirect('subject_list')
    else:
        messages.error(request, "You don't have permission to assign students to subjects.")
        return redirect('subject_list')
    
    # Additional course-based check
    accessible_courses = get_user_accessible_courses(request.user)
    if not (request.user.is_superuser or request.user.is_staff):
        if subject.course and subject.course not in accessible_courses:
            messages.error(request, "You don't have permission to assign students to this subject.")
            return redirect('subject_list')
    
    if request.method == 'POST':
        student_ids = request.POST.getlist('student_ids')
        academic_year = request.POST.get('academic_year', '2025-2026')
        semester = request.POST.get('semester', '1st Semester')
        
        for student_id in student_ids:
            try:
                student = Student.objects.get(id=student_id)
                # Security check: ensure student is in accessible course
                if not (request.user.is_superuser or request.user.is_staff):
                    if student.course not in accessible_courses:
                        messages.warning(request, f"Skipped {student.name}: Not in your accessible courses.")
                        continue
                StudentSubject.objects.get_or_create(
                    student=student,
                    subject=subject,
                    academic_year=academic_year,
                    semester=semester,
                )
            except Exception as e:
                messages.error(request, f"Error assigning student: {str(e)}")
        
        messages.success(request, f"Students assigned to {subject.code} successfully!")
        return redirect('subject_list')
    
    enrolled_students = StudentSubject.objects.filter(subject=subject).values_list('student_id', flat=True)
    all_students = Student.objects.exclude(id__in=enrolled_students)
    
    # Filter students by accessible courses
    all_students = filter_by_user_courses(all_students, request.user)
    
    context = {
        'subject': subject,
        'students': all_students,
        'enrolled_students': Student.objects.filter(id__in=enrolled_students),
    }
    return render(request, 'attendance/assign_students.html', context)

# RFID Attendance Scan
def validate_timeout_time(subject, attendance_date, scan_time, schedule=None, settings=None):
    """
    Validate if time-out is allowed at the given time.
    Time-out is only allowed 15 minutes before the class ends.
    
    Returns a tuple: (is_valid: bool, error_message: str)
    """
    if settings is None:
        settings = get_cached_settings()
    
    # Get class end time
    class_end = None
    
    # First try to get from schedule
    if schedule:
        class_end = schedule.time_end
    elif subject.schedule_time_end:
        class_end = subject.schedule_time_end
    else:
        class_end = settings.class_end_time
    
    if not class_end:
        # If no end time is set, allow time-out
        return True, None
    
    # Convert to datetime for comparison
    scan_datetime = make_aware_datetime(attendance_date, scan_time)
    end_datetime = make_aware_datetime(attendance_date, class_end)
    
    # Calculate 15 minutes before class ends
    earliest_timeout = end_datetime - timedelta(minutes=15)
    
    # Check if scan time is at least 15 minutes before class ends
    if scan_datetime < earliest_timeout:
        earliest_timeout_str = earliest_timeout.time().strftime('%I:%M %p')
        class_end_str = class_end.strftime('%I:%M %p')
        return False, f"Time-out is only allowed 15 minutes before class ends. Earliest time-out: {earliest_timeout_str} (Class ends at {class_end_str})"
    
    return True, None

def check_and_send_warning_email(student, subject):
    """
    Check if student has reached the warning threshold for absences and send warning email if needed.
    
    Args:
        student: Student model instance
        subject: Subject model instance
    """
    settings = get_cached_settings()
    
    # Check if email notifications are enabled
    if not settings.email_notifications_enabled:
        return
    
    # Check if student has an email
    if not student.email:
        return
    
    # Get student's enrollment for this subject (get the most recent one)
    student_subject = StudentSubject.objects.filter(
        student=student,
        subject=subject
    ).order_by('-enrolled_at').first()
    
    if not student_subject:
        return
    
    # Count total absences for this subject (all time, or could be filtered by academic year/semester)
    absences = Attendance.objects.filter(
        student=student,
        subject=subject,
        status='ABSENT'
    ).count()
    
    # Check if absences have reached the warning threshold
    if absences >= settings.send_warnings_after:
        # Check if we've already sent a warning for this threshold (avoid spam)
        # Look for recent warning emails (within last 7 days) for this student and subject
        from datetime import timedelta
        recent_warnings = EmailLog.objects.filter(
            student=student,
            email_type='WARNING',
            status='SENT',
            sent_at__gte=timezone.now() - timedelta(days=7)
        ).exists()
        
        # Only send if we haven't sent a warning recently
        if not recent_warnings:
            try:
                # Generate warning message
                warning_message = f"""Dear {student.name},

This is an automated warning regarding your attendance in {subject.code} - {subject.name}.

You have accumulated {absences} absence(s), which has reached or exceeded the warning threshold of {settings.send_warnings_after} absence(s).

Please be advised that continued absences may affect your academic standing. We encourage you to:
- Attend all scheduled classes
- Contact your instructor if you have valid reasons for absences
- Review the attendance policy in your course syllabus

Current Absences: {absences}
Warning Threshold: {settings.send_warnings_after}

If you have any questions or concerns, please contact your instructor or academic adviser.

Best regards,
Attendance Monitoring System
University Attendance Office"""
                
                # Send warning email
                send_attendance_email(
                    student=student,
                    email_to=student.email,
                    subject=f"Attendance Warning - {subject.code}",
                    message_body=warning_message,
                    email_type='WARNING',
                    check_duplicate=True,
                    duplicate_window_hours=24,  # Prevent duplicate warnings within 24 hours
                    silent=False
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send warning email to {student.email}: {str(e)}")

def send_attendance_confirmation_email(student, subject, attendance_date, time_in=None, time_out=None, status='PRESENT'):
    """
    Send an email notification to the student when attendance is recorded.
    
    Args:
        student: Student model instance
        subject: Subject model instance
        attendance_date: Date of attendance
        time_in: Time in (TimeField or None)
        time_out: Time out (TimeField or None)
        status: Attendance status (PRESENT, LATE, etc.)
    """
    # Check if email notifications are enabled
    settings = get_cached_settings()
    if not settings.email_notifications_enabled:
        return
    
    # Check if student has an email
    if not student.email:
        return
    
    try:
        # Determine email type and content
        if time_out:
            # Check-out notification
            email_type = 'CUSTOM'
            subject_line = f"Attendance Check-Out Confirmation - {subject.code}"
            time_in_str = time_in.strftime('%I:%M %p') if time_in else 'N/A'
            time_out_str = time_out.strftime('%I:%M %p')
            
            message_body = f"""Dear {student.name},

Your attendance has been recorded for {subject.code} - {subject.name}.

Date: {attendance_date.strftime('%B %d, %Y')}
Time In: {time_in_str}
Time Out: {time_out_str}
Status: {status}

Thank you for your attendance.

Best regards,
Attendance System"""
        else:
            # Check-in notification
            email_type = 'CUSTOM'
            subject_line = f"Attendance Check-In Confirmation - {subject.code}"
            time_in_str = time_in.strftime('%I:%M %p') if time_in else 'N/A'
            
            message_body = f"""Dear {student.name},

Your attendance has been recorded for {subject.code} - {subject.name}.

Date: {attendance_date.strftime('%B %d, %Y')}
Time In: {time_in_str}
Status: {status}

Thank you for your attendance.

Best regards,
Attendance System"""
        
        # Send email (use duplicate_window_hours=1 to prevent duplicate emails within 1 hour)
        send_attendance_email(
            student=student,
            email_to=student.email,
            subject=subject_line,
            message_body=message_body,
            email_type=email_type,
            check_duplicate=True,
            duplicate_window_hours=1,  # Prevent duplicate emails within 1 hour
            silent=False
        )
    except Exception as e:
        # Log error but don't interrupt the attendance recording process
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send attendance confirmation email to {student.email}: {str(e)}")

@login_required
def scan_view(request):
    # Filter subjects by adviser first
    subjects_qs = filter_subjects_by_user(request.user).filter(is_active=True).prefetch_related('schedules')

    # Cache settings and current Manila time for auto subject selection
    settings = get_cached_settings()
    now_manila = get_manila_now()
    today = now_manila.date()
    current_time = now_manila.time()

    # Identify a subject whose schedule is active right now (with grace periods)
    auto_subject = None
    auto_subject_window_start = None
    for subj in subjects_qs:
        try:
            is_active_now, _, schedule = validate_attendance_time(
                subj, today, current_time, settings
            )
        except Exception:
            # Skip subjects that fail validation to avoid breaking the scan page
            continue

        if not is_active_now:
            continue

        # Use the beginning of the valid window so we pick the earliest active class
        window_start_dt = None
        if schedule and schedule.time_start:
            window_start_dt = make_aware_datetime(today, schedule.time_start) - timedelta(minutes=settings.early_attendance_minutes)
        elif subj.schedule_time_start:
            window_start_dt = make_aware_datetime(today, subj.schedule_time_start) - timedelta(minutes=settings.early_attendance_minutes)
        elif getattr(settings, 'class_start_time', None):
            window_start_dt = make_aware_datetime(today, settings.class_start_time) - timedelta(minutes=settings.early_attendance_minutes)

        if auto_subject_window_start is None or (window_start_dt and window_start_dt < auto_subject_window_start):
            auto_subject = subj
            auto_subject_window_start = window_start_dt
    
    # Get subject_id from GET parameter (for dropdown changes)
    active_subject_id = request.GET.get('subject_id')
    active_subject = None
    
    if active_subject_id:
        try:
            active_subject = subjects_qs.filter(id=active_subject_id).first()
        except (ValueError, TypeError):
            pass
    
    # Auto-switch to the subject whose schedule is currently active
    auto_selected = False
    if auto_subject and (not active_subject or active_subject.id != auto_subject.id):
        active_subject = auto_subject
        auto_selected = True
        if request.method == 'GET':
            messages.info(request, f"Active subject switched to {active_subject.code} based on the current schedule.")
    
    # Fallback to first active subject if none selected
    if not active_subject:
        active_subject = subjects_qs.first()
    
    # Always display all active subjects for the adviser in the dropdown
    # This allows easy switching between subjects
    subjects_to_display = subjects_qs
    
    # Filter last_scan based on active subject if one is selected
    if active_subject:
        # Show last scan for the active subject
        last_scan = Attendance.objects.select_related('student', 'subject').filter(
            subject=active_subject
        ).order_by('-created_at').first()
    else:
        # If no active subject, show last scan from any accessible subject
        accessible_subject_ids = subjects_qs.values_list('id', flat=True)
        last_scan = Attendance.objects.select_related('student', 'subject').filter(
            subject_id__in=accessible_subject_ids
        ).order_by('-created_at').first()
    
    # Get last scanned student from session for modal display
    last_scanned_student = request.session.pop('last_scanned_student', None)
    
    context = {
        'subject': active_subject,
        'subjects': subjects_to_display,
        'last_scan': last_scan,
        'last_scanned_student': last_scanned_student,
        'auto_selected_subject_id': active_subject.id if auto_selected else None,
    }
    
    if request.method == 'POST':
            rfid_id = request.POST.get('rfid_id', '').strip()
            subject_id = request.POST.get('subject_id', '')
            manual_time = request.POST.get('manual_time', '')
            
            # Validate and get subject from POST - this takes priority over GET
            final_subject = None
            if subject_id:
                try:
                    post_subject = subjects_qs.filter(id=subject_id).first()
                    if post_subject:
                        final_subject = post_subject
                        active_subject = post_subject
                        context['subject'] = active_subject
                    else:
                        # If POST subject_id is invalid, try to use GET or default
                        if active_subject:
                            final_subject = active_subject
                        else:
                            final_subject = subjects_qs.first()
                            active_subject = final_subject
                            context['subject'] = active_subject
                except (ValueError, TypeError) as e:
                    messages.error(request, f"Invalid subject ID: {str(e)}")
            elif active_subject:
                final_subject = active_subject
            else:
                # No subject_id in POST and no active_subject, get default
                final_subject = subjects_qs.first()
                active_subject = final_subject
                context['subject'] = active_subject
            
            if not rfid_id:
                messages.error(request, "Please scan an RFID card.")
            elif not final_subject:
                messages.error(request, "Please select an active subject.")
            else:
                try:
                    # Optimized query: use only() to fetch only needed fields for faster lookup
                    student = Student.objects.only('id', 'name', 'rfid_id', 'email', 'profile_picture').get(rfid_id=rfid_id)
                    subject = final_subject
                    
                    # Check if student is enrolled in this subject (any semester/year)
                    # Optimized: use exists() for faster check
                    enrollment = StudentSubject.objects.filter(
                        student=student,
                        subject=subject
                    ).exists()
                    
                    if not enrollment:
                        # Get list of subjects student is enrolled in for better error message
                        student_subjects = StudentSubject.objects.filter(
                            student=student
                        ).select_related('subject').only('subject__code', 'subject__name').values_list('subject__code', 'subject__name')
                        
                        enrolled_list = ', '.join([f"{code} - {name}" for code, name in student_subjects]) if student_subjects else 'None'
                        
                        error_msg = (
                            f"✗ Enrollment Error: {student.name} (RFID: {rfid_id}) is not enrolled in {subject.code} - {subject.name}. "
                            f"Student's enrolled subjects: {enrolled_list if enrolled_list != 'None' else 'None (no enrollments found)'}"
                        )
                        
                        messages.error(request, error_msg)
                        return redirect(f"{reverse('scan')}?subject_id={subject.id}")
                    
                    # Get current time in Manila timezone
                    now_manila = get_manila_now()
                    today = now_manila.date()
                    # Use cached settings for better performance
                    settings = get_cached_settings()
                    
                    # Determine scan time (use manual time if provided, otherwise current time in Manila)
                    # Use actual current time with seconds for accurate validation
                    now_time = now_manila.time()
                    scan_time = now_time  # Keep actual time for validation
                    attendance_date = today
                    
                    if manual_time:
                        try:
                            # Parse time - try HH:MM format first
                            parsed_time = datetime.strptime(manual_time, '%H:%M').time()
                            scan_time = parsed_time
                            # If manual time is provided, we still use today's date
                        except ValueError:
                            # Try with seconds format
                            try:
                                parsed_time = datetime.strptime(manual_time, '%H:%M:%S').time()
                                scan_time = parsed_time
                            except:
                                # If parsing fails, use current time
                                scan_time = now_time
                    
                    # Check if student already has both time_in and time_out recorded for today
                    existing_attendance_check = Attendance.objects.filter(
                        student=student,
                        subject=subject,
                        date=attendance_date
                    ).first()
                    
                    if existing_attendance_check and existing_attendance_check.time_in and existing_attendance_check.time_out:
                        # Student already has both time_in and time_out
                        time_in_str = existing_attendance_check.time_in.strftime('%I:%M %p')
                        time_out_str = existing_attendance_check.time_out.strftime('%I:%M %p')
                        messages.info(request, f"ℹ You already have time in and time out recorded for today. Time In: {time_in_str}, Time Out: {time_out_str}")
                        return redirect(f"{reverse('scan')}?subject_id={subject.id}")
                    
                    # Validate attendance time and date using actual time
                    is_valid, error_message, schedule = validate_attendance_time(
                        subject, attendance_date, scan_time, settings
                    )
                    
                    if not is_valid:
                        # Check if the error is about time window being closed
                        if "not allowed at this time" in error_message.lower() or "valid time window" in error_message.lower():
                            messages.error(request, f"✗ The time is no longer available. {error_message}")
                        else:
                            messages.error(request, f"✗ {error_message}")
                        return redirect(f"{reverse('scan')}?subject_id={subject.id}")
                    
                    # Normalize time only when storing to database (remove seconds/microseconds)
                    stored_time = scan_time.replace(second=0, microsecond=0)
                    
                    # Use transaction with locking to prevent duplicate records
                    with transaction.atomic():
                        # Get or create attendance record - only ONE record per student/subject/date
                        # Use select_for_update to lock the row and prevent race conditions
                        existing_attendance, created = Attendance.objects.select_for_update().get_or_create(
                            student=student,
                            subject=subject,
                            date=attendance_date,
                            defaults={
                                'time': stored_time,
                                'time_in': stored_time,
                                'status': 'PRESENT'
                            }
                        )
                        
                        # Determine status based on time (if this is a new record, we'll update it)
                        class_start = None
                        if schedule:
                            class_start = schedule.time_start
                        elif subject.schedule_time_start:
                            class_start = subject.schedule_time_start
                        else:
                            class_start = settings.class_start_time
                        
                        status = 'PRESENT'
                        if class_start:
                            scan_datetime = make_aware_datetime(attendance_date, scan_time)
                            start_datetime = make_aware_datetime(attendance_date, class_start)
                            
                            # Calculate time difference in minutes
                            time_diff = scan_datetime - start_datetime
                            minutes_late = time_diff.total_seconds() / 60
                            
                            # If grace_period_minutes or more late, mark as LATE
                            if minutes_late >= settings.grace_period_minutes:
                                status = 'LATE'
                            else:
                                status = 'PRESENT'
                        
                        # Check if this should be a time-out or time-in update
                        should_do_timeout = False
                        if not created and existing_attendance.time_out is None:
                            # Student has an existing time-in without time_out
                            # Check if this is a valid time-out attempt
                            is_timeout_valid, timeout_error = validate_timeout_time(
                                subject, attendance_date, scan_time, schedule, settings
                            )
                            
                            if is_timeout_valid:
                                should_do_timeout = True
                        
                        if should_do_timeout:
                            # Valid time-out - student is checking out
                            # Only update if time_out is not already set or if new time is different
                            if existing_attendance.time_out is None or existing_attendance.time_out != stored_time:
                                existing_attendance.time_out = stored_time
                                existing_attendance.save(update_fields=['time_out'])
                                time_in_str = existing_attendance.time_in.strftime('%I:%M %p') if existing_attendance.time_in else 'N/A'
                                time_out_str = existing_attendance.time_out.strftime('%I:%M %p')
                                messages.success(request, f"✓ Time Out recorded! {student.name} - Time In: {time_in_str}, Time Out: {time_out_str}")

                                # Get profile picture URL efficiently
                                profile_picture_url = student.get_profile_picture_url()

                                # Store student info in session for display modal
                                request.session['last_scanned_student'] = {
                                    'id': student.id,
                                    'name': student.name,
                                    'rfid_id': student.rfid_id,
                                    'profile_picture_url': profile_picture_url,
                                    'action': 'time_out',
                                    'time_in': time_in_str,
                                    'time_out': time_out_str,
                                    'status': existing_attendance.status,
                                    'subject_code': subject.code
                                }

                                # Send email notification for check-out
                                send_attendance_confirmation_email(
                                    student=student,
                                    subject=subject,
                                    attendance_date=attendance_date,
                                    time_in=existing_attendance.time_in,
                                    time_out=existing_attendance.time_out,
                                    status=existing_attendance.status
                                )
                            else:
                                # Time-out already recorded at this time - no duplicate
                                time_in_str = existing_attendance.time_in.strftime('%I:%M %p') if existing_attendance.time_in else 'N/A'
                                time_out_str = existing_attendance.time_out.strftime('%I:%M %p') if existing_attendance.time_out else 'N/A'
                                messages.info(request, f"ℹ Time-out already recorded at {time_out_str}. No duplicate created.")
                        else:
                            # Student is checking in (time in) or updating existing record
                            if existing_attendance.time_in is not None:
                                # Preserve original time-in to avoid accidental changes from re-scans
                                time_in_str = existing_attendance.time_in.strftime('%I:%M %p') if existing_attendance.time_in else 'N/A'
                                time_out_str = existing_attendance.time_out.strftime('%I:%M %p') if existing_attendance.time_out else 'N/A'
                                messages.info(
                                    request,
                                    f"ℹ Time-in already recorded at {time_in_str}. "
                                    f"{'Time-out recorded at ' + time_out_str if existing_attendance.time_out else 'Time-out not yet recorded.'}"
                                )
                            else:
                                # Only set time-in when it has not been recorded yet
                                existing_attendance.time = stored_time  # Keep for backward compatibility
                                existing_attendance.time_in = stored_time
                                existing_attendance.status = status
                                existing_attendance.save(update_fields=['time', 'time_in', 'status'])
                                time_in_str = stored_time.strftime('%I:%M %p')
                                messages.success(request, f"✓ Time In recorded! {student.name} - {status} at {time_in_str}")

                                # Get profile picture URL efficiently
                                profile_picture_url = student.get_profile_picture_url()

                                # Store student info in session for display modal
                                request.session['last_scanned_student'] = {
                                    'id': student.id,
                                    'name': student.name,
                                    'rfid_id': student.rfid_id,
                                    'profile_picture_url': profile_picture_url,
                                    'action': 'time_in',
                                    'time_in': time_in_str,
                                    'time_out': None,
                                    'status': status,
                                    'subject_code': subject.code
                                }

                                # Send email notification for check-in
                                send_attendance_confirmation_email(
                                    student=student,
                                    subject=subject,
                                    attendance_date=attendance_date,
                                    time_in=stored_time,
                                    time_out=None,
                                    status=status
                                )

                                # Check and send warning email if student has reached absence threshold
                                if status == 'ABSENT':
                                    check_and_send_warning_email(student, subject)
                            
                        return redirect(f"{reverse('scan')}?subject_id={subject.id}")

                        
                except Student.DoesNotExist:
                    messages.error(request, "✗ RFID card not recognized")
                except Subject.DoesNotExist:
                    messages.error(request, "✗ Subject not found")
                except Exception as e:
                    messages.error(request, f"An error occurred: {str(e)}")
    
    return render(request, 'attendance/scan.html', context)

@login_required
def manual_entry(request):
    if request.method == 'POST':
        try:
            student_id = request.POST.get('student_id')
            subject_id = request.POST.get('subject_id')
            date = request.POST.get('date')
            time_in_str = request.POST.get('time_in')
            time_out_str = request.POST.get('time_out')
            status = request.POST.get('status', 'PRESENT')
            skip_validation = request.POST.get('skip_validation') == 'on'  # Admin override option
            
            student = Student.objects.get(id=student_id)
            subject = Subject.objects.get(id=subject_id)
            
            attendance_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            # Parse time_in
            if time_in_str:
                try:
                    time_in = datetime.strptime(time_in_str, '%H:%M').time().replace(second=0, microsecond=0)
                except ValueError:
                    try:
                        time_in = datetime.strptime(time_in_str, '%H:%M:%S').time().replace(second=0, microsecond=0)
                    except ValueError:
                        messages.error(request, f"Invalid time_in format: {time_in_str}. Use HH:MM format.")
                        context = {
                            'students': Student.objects.all(),
                            'subjects': Subject.objects.filter(is_active=True),
                        }
                        return render(request, 'attendance/manual_entry.html', context)
            else:
                # Use current time if not provided
                now_time = timezone.now().time()
                time_in = now_time.replace(second=0, microsecond=0)
            
            # Parse time_out (optional)
            time_out = None
            if time_out_str:
                try:
                    time_out = datetime.strptime(time_out_str, '%H:%M').time().replace(second=0, microsecond=0)
                except ValueError:
                    try:
                        time_out = datetime.strptime(time_out_str, '%H:%M:%S').time().replace(second=0, microsecond=0)
                    except ValueError:
                        messages.error(request, f"Invalid time_out format: {time_out_str}. Use HH:MM format.")
                        context = {
                            'students': Student.objects.all(),
                            'subjects': Subject.objects.filter(is_active=True),
                        }
                        return render(request, 'attendance/manual_entry.html', context)
            
            settings = SystemSettings.get_settings()
            
            # Validate attendance time and date using time_in (unless admin chooses to skip)
            if not skip_validation:
                is_valid, error_message, schedule = validate_attendance_time(
                    subject, attendance_date, time_in, settings
                )
                
                if not is_valid:
                    messages.error(request, f"Error: {error_message}")
                    context = {
                        'students': Student.objects.all(),
                        'subjects': Subject.objects.filter(is_active=True),
                    }
                    return render(request, 'attendance/manual_entry.html', context)
            
            # Use transaction to prevent duplicates
            with transaction.atomic():
                # Get or create attendance record - only ONE record per student/subject/date
                # Use select_for_update to lock the row and prevent race conditions
                existing, created = Attendance.objects.select_for_update().get_or_create(
                    student=student,
                    subject=subject,
                    date=attendance_date,
                    defaults={
                        'time': time_in,
                        'time_in': time_in,
                        'time_out': time_out,
                        'status': status
                    }
                )
                
                if not created:
                    # Update existing attendance - prevent duplicate time_in/time_out
                    updated = False
                    if existing.time_in != time_in:
                        existing.time = time_in  # Keep for backward compatibility
                        existing.time_in = time_in
                        updated = True
                    if time_out and existing.time_out != time_out:
                        existing.time_out = time_out
                        updated = True
                    if existing.status != status:
                        existing.status = status
                        updated = True

                    if updated:
                        existing.save()
                        messages.success(request, "Attendance updated successfully!")
                    else:
                        messages.info(request, "Attendance already exists with the same data. No duplicate created.")
                else:
                    messages.success(request, "Attendance recorded successfully!")
                    
                    # Check and send warning email if status is ABSENT
                    if status == 'ABSENT':
                        check_and_send_warning_email(student, subject)
            return redirect('scan')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    
    context = {
        'students': Student.objects.all(),
        'subjects': Subject.objects.filter(is_active=True),
    }
    return render(request, 'attendance/manual_entry.html', context)

# Daily Attendance Logs
@login_required
def attendance_logs(request):
    subject_id = request.GET.get('subject_id', '')
    date_filter = request.GET.get('date', timezone.now().strftime('%Y-%m-%d'))
    
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
    except:
        filter_date = timezone.now().date()
    
    # Filter by user's accessible courses or adviser's students
    attendances = Attendance.objects.filter(date=filter_date).select_related('student', 'subject')
    # Use the new helper function to filter by adviser's students
    attendances = filter_by_adviser_students(attendances, request.user, student_field='student')
    
    subject_id_int = None
    if subject_id:
        try:
            subject_id_int = int(subject_id)
            # Security check: ensure subject is accessible
            if not (request.user.is_superuser or request.user.is_staff):
                subject = Subject.objects.filter(id=subject_id_int).first()
                if subject:
                    # Check if subject is accessible based on user role
                    is_accessible = False
                    if hasattr(request.user, 'adviser_profile'):
                        # For advisers: check if subject is created by them OR their students are enrolled
                        adviser = request.user.adviser_profile
                        if subject.adviser == adviser:
                            is_accessible = True
                        else:
                            # Check if any of adviser's students are enrolled in this subject
                            adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
                            if StudentSubject.objects.filter(subject=subject, student_id__in=adviser_student_ids).exists():
                                is_accessible = True
                    else:
                        # For other users: check accessible courses
                        accessible_courses = get_user_accessible_courses(request.user)
                        if subject.course and subject.course in accessible_courses:
                            is_accessible = True
                    
                    if not is_accessible:
                        messages.error(request, "You don't have permission to view this subject's attendance.")
                        return redirect('attendance_logs')
            attendances = attendances.filter(subject_id=subject_id_int)
        except (ValueError, TypeError):
            pass
    
        # Get all students enrolled in the subject (if filtered)
        if subject_id_int:
            enrolled_students = StudentSubject.objects.filter(subject_id=subject_id_int).values_list('student_id', flat=True)
            all_students = Student.objects.filter(id__in=enrolled_students)
            
            # Filter by adviser's students or accessible courses
            if request.user.is_superuser or request.user.is_staff:
                pass  # Show all students
            elif hasattr(request.user, 'adviser_profile'):
                # Advisers see all their assigned students enrolled in the subject
                adviser = request.user.adviser_profile
                adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
                all_students = all_students.filter(id__in=adviser_student_ids)
            else:
                # Other users filter by accessible courses
                accessible_courses = get_user_accessible_courses(request.user)
                if accessible_courses.exists():
                    all_students = all_students.filter(course__in=accessible_courses)
                else:
                    all_students = all_students.none()
        
        # Create attendance records for absent students
        present_student_ids = attendances.values_list('student_id', flat=True)
        absent_students = all_students.exclude(id__in=present_student_ids)
        
        for student in absent_students:
            attendance, created = Attendance.objects.get_or_create(
                student=student,
                subject_id=subject_id_int,
                date=filter_date,
                defaults={'status': 'ABSENT'}
            )
            # Check and send warning email if attendance was just created as ABSENT
            if created and attendance.status == 'ABSENT':
                subject = Subject.objects.get(id=subject_id_int)
                check_and_send_warning_email(student, subject)
        
        attendances = Attendance.objects.filter(date=filter_date, subject_id=subject_id_int).select_related('student', 'subject')
        # Use the new helper function to filter by adviser's students
        attendances = filter_by_adviser_students(attendances, request.user, student_field='student')
    
    attendances = attendances.order_by('student__name')
    
    stats = {
        'present': attendances.filter(status='PRESENT').count(),
        'absent': attendances.filter(status='ABSENT').count(),
        'late': attendances.filter(status='LATE').count(),
        'total': attendances.count(),
    }
    
    # Filter subjects by adviser first, then by courses
    subjects = filter_subjects_by_user(request.user)
    subjects = filter_by_user_courses(subjects.filter(is_active=True), request.user, course_field='course')
    
    context = {
        'attendances': attendances,
        'subjects': subjects,
        'selected_subject_id': subject_id,
        'date_filter': filter_date.strftime('%Y-%m-%d'),
        'stats': stats,
    }
    return render(request, 'attendance/attendance_logs.html', context)

@login_required
def attendance_logs_export_csv(request):
    subject_id = request.GET.get('subject_id', '')
    date_filter = request.GET.get('date', timezone.now().strftime('%Y-%m-%d'))
    
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
    except:
        filter_date = timezone.now().date()
    
    # Filter by user's accessible courses or adviser's students (same logic as attendance_logs view)
    attendances = Attendance.objects.filter(date=filter_date).select_related('student', 'subject')
    # Use the new helper function to filter by adviser's students
    attendances = filter_by_adviser_students(attendances, request.user, student_field='student')
    
    subject_id_int = None
    if subject_id:
        try:
            subject_id_int = int(subject_id)
            # Security check: ensure subject is accessible (same as attendance_logs view)
            if not (request.user.is_superuser or request.user.is_staff):
                subject = Subject.objects.filter(id=subject_id_int).first()
                if subject:
                    # Check if subject is accessible based on user role
                    is_accessible = False
                    if hasattr(request.user, 'adviser_profile'):
                        # For advisers: check if subject is created by them OR their students are enrolled
                        adviser = request.user.adviser_profile
                        if subject.adviser == adviser:
                            is_accessible = True
                        else:
                            # Check if any of adviser's students are enrolled in this subject
                            adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
                            if StudentSubject.objects.filter(subject=subject, student_id__in=adviser_student_ids).exists():
                                is_accessible = True
                    else:
                        # For other users: check accessible courses
                        accessible_courses = get_user_accessible_courses(request.user)
                        if subject.course and subject.course in accessible_courses:
                            is_accessible = True
                    
                    if not is_accessible:
                        # Return empty CSV if not accessible
                        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
                        response['Content-Disposition'] = f'attachment; filename="attendance_log_{filter_date}.csv"'
                        writer = csv.writer(response)
                        writer.writerow(['Student ID', 'Student Name', 'Subject', 'Time In', 'Time Out', 'Status'])
                        return response
            
            attendances = attendances.filter(subject_id=subject_id_int)
        except (ValueError, TypeError):
            pass
    
    # Order by student name
    attendances = attendances.order_by('student__name')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="attendance_log_{filter_date}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Student ID', 'Student Name', 'Subject', 'Time In', 'Time Out', 'Status'])
    
    # Write data rows
    for att in attendances:
        if not att.student:
            continue
            
        time_in_str = '--:--'
        if att.time_in:
            time_in_str = att.time_in.strftime('%I:%M %p')
        elif att.time:
            time_in_str = att.time.strftime('%I:%M %p')
        
        time_out_str = '--:--'
        if att.time_out:
            time_out_str = att.time_out.strftime('%I:%M %p')
        
        subject_code = att.subject.code if att.subject else 'N/A'
        
        writer.writerow([
            att.student.rfid_id or '',
            att.student.name or '',
            subject_code,
            time_in_str,
            time_out_str,
            att.status or '',
        ])
    
    return response

# Student Attendance Summary
@login_required
@login_required
def student_attendance_summary(request, student_id=None):
    """
    Display all subjects with their enrolled students for a given academic year and semester.
    """
    academic_year = request.GET.get('academic_year', '2025-2026')
    semester = request.GET.get('semester', '1st Semester')
    
    # Get accessible subjects based on user permissions (includes subjects where adviser's students are enrolled)
    subjects = filter_subjects_by_user(request.user)
    subjects = filter_by_user_courses(subjects.filter(is_active=True), request.user, course_field='course')
    
    # Prepare data for each subject with enrolled students
    subjects_data = []
    total_enrollments = 0
    
    # Prefetch all enrollments for better performance (avoids N+1 queries)
    all_enrollments = StudentSubject.objects.filter(
        subject__in=subjects,
        academic_year=academic_year,
        semester=semester
    ).select_related('student', 'student__course', 'student__adviser', 'subject')
    
    # Filter enrollments by adviser's students
    all_enrollments = filter_by_adviser_students(all_enrollments, request.user, student_field='student')
    
    # Group enrollments by subject
    enrollments_by_subject = {}
    for enrollment in all_enrollments:
        subject_id = enrollment.subject.id
        if subject_id not in enrollments_by_subject:
            enrollments_by_subject[subject_id] = []
        enrollments_by_subject[subject_id].append(enrollment)
    
    for subject in subjects.order_by('code'):
        # Get enrolled students for this subject
        enrollments = enrollments_by_subject.get(subject.id, [])
        
        # Get students list
        students_list = []
        for enrollment in enrollments:
            students_list.append({
                'student': enrollment.student,
                'enrollment': enrollment,
            })
        
        enrollment_count = len(students_list)
        total_enrollments += enrollment_count
        
        subjects_data.append({
            'subject': subject,
            'students': students_list,
            'enrollment_count': enrollment_count,
        })
    
    # Calculate statistics
    total_subjects = len(subjects_data)
    avg_enrollments = round(total_enrollments / total_subjects, 1) if total_subjects > 0 else 0
    
    context = {
        'subjects_data': subjects_data,
        'academic_year': academic_year,
        'semester': semester,
        'total_subjects': total_subjects,
        'total_enrollments': total_enrollments,
        'avg_enrollments': avg_enrollments,
    }
    return render(request, 'attendance/student_summary.html', context)

# End of Semester Report
@login_required
def semester_report(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    
    # Permission check: advisers can only view reports for their assigned students
    if not (request.user.is_superuser or request.user.is_staff):
        if hasattr(request.user, 'adviser_profile'):
            if student.adviser != request.user.adviser_profile:
                messages.error(request, "You don't have permission to view this student's report.")
                return redirect('student_summary')
        else:
            # Other users can only view their own report
            if hasattr(request.user, 'student_profile'):
                if student != request.user.student_profile:
                    messages.error(request, "You don't have permission to view this student's report.")
                    return redirect('student_view')
            else:
                messages.error(request, "You don't have permission to view student reports.")
                return redirect('dashboard')
    
    academic_year = request.GET.get('academic_year', '2025-2026')
    semester = request.GET.get('semester', '1st Semester')
    
    # Get all attendances for this student in the semester
    student_subjects = StudentSubject.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester
    ).select_related('subject')
    
    report_data = []
    total_days = 0
    total_present = 0
    total_absent = 0
    missed_dates = {}
    
    for ss in student_subjects:
        attendances = Attendance.objects.filter(
            student=student,
            subject=ss.subject
        )
        
        subject_days = attendances.count()
        subject_present = attendances.filter(status='PRESENT').count()
        subject_absent = attendances.filter(status='ABSENT').count()
        
        # Get missed dates
        missed = attendances.filter(status='ABSENT').values_list('date', flat=True)
        missed_dates[ss.subject.code] = list(missed)
        
        report_data.append({
            'subject': ss.subject,
            'total_days': subject_days,
            'present': subject_present,
            'absent': subject_absent,
            'percentage': round((subject_present / subject_days * 100) if subject_days > 0 else 0, 1),
        })
        
        total_days += subject_days
        total_present += subject_present
        total_absent += subject_absent
    
    context = {
        'student': student,
        'report_data': report_data,
        'total_days': total_days,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_percentage': round((total_present / total_days * 100) if total_days > 0 else 0, 1),
        'missed_dates': missed_dates,
        'academic_year': academic_year,
        'semester': semester,
    }
    return render(request, 'attendance/semester_report.html', context)

# Email Notification
@login_required
def email_preview(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    
    # Permission check: advisers can only view/preview emails for their assigned students
    if not (request.user.is_superuser or request.user.is_staff):
        if hasattr(request.user, 'adviser_profile'):
            if student.adviser != request.user.adviser_profile:
                messages.error(request, "You don't have permission to view this student's email preview.")
                return redirect('student_summary')
        else:
            # Other users can only view their own email preview
            if hasattr(request.user, 'student_profile'):
                if student != request.user.student_profile:
                    messages.error(request, "You don't have permission to view this student's email preview.")
                    return redirect('student_view')
            else:
                messages.error(request, "You don't have permission to view email previews.")
                return redirect('dashboard')
    
    academic_year = request.GET.get('academic_year', '2025-2026')
    semester = request.GET.get('semester', '1st Semester')
    
    # Check if email notifications are enabled
    settings = SystemSettings.get_settings()
    if not settings.email_notifications_enabled:
        messages.warning(request, "Email notifications are currently disabled in system settings.")
        return redirect('student_summary')
    
    # Respect student opt-out preference
    if hasattr(student, 'email_opt_in') and not student.email_opt_in:
        messages.warning(request, "This student has opted out of email notifications.")
        return redirect('student_summary')
    
    # Get report data (similar to semester_report)
    student_subjects = StudentSubject.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester
    ).select_related('subject')
    
    total_days = 0
    total_present = 0
    total_absent = 0
    missed_subjects = []
    
    for ss in student_subjects:
        attendances = Attendance.objects.filter(
            student=student,
            subject=ss.subject
        )
        
        subject_days = attendances.count()
        subject_present = attendances.filter(status='PRESENT').count()
        subject_absent = attendances.filter(status='ABSENT').count()
        
        if subject_absent > 0:
            missed_subjects.append({
                'subject': ss.subject.code,
                'days': subject_absent,
            })
        
        total_days += subject_days
        total_present += subject_present
        total_absent += subject_absent
    
    if request.method == 'POST':
        email_to = request.POST.get('email_to', student.email)
        email_cc = request.POST.get('email_cc', '')
        email_bcc = request.POST.get('email_bcc', '')
        subject_line = request.POST.get('subject', f'Attendance Report - {semester} AY {academic_year}')
        message_body = request.POST.get('message_body', '')
        
        # Send email using the email utility
        success, email_log, error_message = send_attendance_email(
            student=student,
            email_to=email_to,
            subject=subject_line,
            message_body=message_body,
            email_type='SEMESTER',
            email_cc=email_cc if email_cc else None,
            email_bcc=email_bcc if email_bcc else None,
        )
        
        if success:
            # Check if it was a duplicate
            if error_message and 'Duplicate' in error_message:
                messages.warning(request, f"Email was not sent - duplicate detected. {error_message}")
            else:
                messages.success(request, f"Email sent successfully to {email_to}!")
            return redirect('email_logs')
        else:
            messages.error(request, f"Failed to send email: {error_message}")
    
    # Generate default message
    default_message = f"""Dear {student.name},

This is your attendance summary for {semester}, Academic Year {academic_year}.

Total Class Days : {total_days}
Present Days     : {total_present} ({round((total_present/total_days*100) if total_days > 0 else 0, 1)}%)
Absent Days      : {total_absent} ({round((total_absent/total_days*100) if total_days > 0 else 0, 1)}%)

"""
    
    if missed_subjects:
        default_message += "Missed Subjects:\n"
        for ms in missed_subjects:
            default_message += f"- {ms['subject']} : {ms['days']} days\n"
        default_message += "\n"
    
    default_message += """Please contact your instructor for concerns.

Regards,
RFID Attendance Monitoring System
University Attendance Office"""
    
    context = {
        'student': student,
        'email_to': student.email,
        'subject': f'Attendance Report - {semester} AY {academic_year}',
        'message_body': default_message,
        'total_days': total_days,
        'total_present': total_present,
        'total_absent': total_absent,
        'missed_subjects': missed_subjects,
        'academic_year': academic_year,
        'semester': semester,
    }
    return render(request, 'attendance/email_preview.html', context)

@login_required
def bulk_send_emails(request):
    """
    Send email reports to multiple students at once.
    """
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('student_summary')
    
    # Check if email notifications are enabled
    settings = SystemSettings.get_settings()
    if not settings.email_notifications_enabled:
        messages.warning(request, "Email notifications are currently disabled in system settings. Please enable them in Settings to send emails.")
        return redirect('student_summary')
    
    student_ids = request.POST.getlist('student_ids')
    academic_year = request.POST.get('academic_year', '2025-2026')
    semester = request.POST.get('semester', '1st Semester')
    
    if not student_ids:
        messages.error(request, "Please select at least one student.")
        return redirect(f"{reverse('student_summary')}?academic_year={academic_year}&semester={semester}")
    
    # Get students (with permission check)
    if request.user.is_superuser or request.user.is_staff:
        students = Student.objects.filter(id__in=student_ids)
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers can send emails to their assigned students
        adviser = request.user.adviser_profile
        students = Student.objects.filter(
            id__in=student_ids,
            adviser=adviser
        )
    else:
        # Other users filter by accessible courses
        accessible_courses = get_user_accessible_courses(request.user)
        students = Student.objects.filter(id__in=student_ids, course__in=accessible_courses)
    
    if not students.exists():
        messages.error(request, "No accessible students found.")
        return redirect(f"{reverse('student_summary')}?academic_year={academic_year}&semester={semester}")
    
    # Prepare email tasks for bulk sending
    email_tasks = []
    failed_students = []
    
    for student in students:
        # Skip students who opted out
        if hasattr(student, 'email_opt_in') and not student.email_opt_in:
            failed_students.append(f"{student.name} (opted out)")
            continue
        try:
            # Get report data for this student
            student_subjects = StudentSubject.objects.filter(
                student=student,
                academic_year=academic_year,
                semester=semester
            ).select_related('subject')
            
            total_days = 0
            total_present = 0
            total_absent = 0
            missed_subjects = []
            
            for ss in student_subjects:
                attendances = Attendance.objects.filter(
                    student=student,
                    subject=ss.subject
                )
                
                subject_days = attendances.count()
                subject_present = attendances.filter(status='PRESENT').count()
                subject_absent = attendances.filter(status='ABSENT').count()
                
                if subject_absent > 0:
                    missed_subjects.append({
                        'subject': ss.subject.code,
                        'days': subject_absent,
                    })
                
                total_days += subject_days
                total_present += subject_present
                total_absent += subject_absent
            
            # Generate email message
            default_message = f"""Dear {student.name},

This is your attendance summary for {semester}, Academic Year {academic_year}.

Total Class Days : {total_days}
Present Days     : {total_present} ({round((total_present/total_days*100) if total_days > 0 else 0, 1)}%)
Absent Days      : {total_absent} ({round((total_absent/total_days*100) if total_days > 0 else 0, 1)}%)

"""
            
            if missed_subjects:
                default_message += "Missed Subjects:\n"
                for ms in missed_subjects:
                    default_message += f"- {ms['subject']} : {ms['days']} days\n"
                default_message += "\n"
            
            default_message += """Please contact your instructor for concerns.

Regards,
RFID Attendance Monitoring System
University Attendance Office"""
            
            # Add to email tasks list
            email_tasks.append((
                student,
                student.email,
                f'Attendance Report - {semester} AY {academic_year}',
                default_message,
                {'email_type': 'SEMESTER'}
            ))
        
        except Exception as e:
            failed_students.append(f"{student.name} ({str(e)})")
    
    # Send all emails using threaded bulk sending (max 5 concurrent workers)
    success_count, failed_count, results = send_emails_bulk(email_tasks, max_workers=5, silent=False)
    
    # Collect failed students from results
    for i, (success, email_log, error_message) in enumerate(results):
        if not success and email_log:
            failed_students.append(f"{email_log.student.name} ({error_message})")
    
    # Show success/error messages
    if success_count > 0:
        messages.success(request, f"Successfully sent {success_count} email report(s)!")
    if failed_count > 0:
        error_msg = f"Failed to send {failed_count} email(s): " + "; ".join(failed_students[:5])
        if len(failed_students) > 5:
            error_msg += f" and {len(failed_students) - 5} more..."
        messages.error(request, error_msg)
    
    return redirect(f"{reverse('student_summary')}?academic_year={academic_year}&semester={semester}")

@login_required
def email_logs(request):
    email_type = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    logs = EmailLog.objects.select_related('student').all()
    
    # Filter by adviser's students
    if request.user.is_superuser or request.user.is_staff:
        pass  # Show all logs
    elif hasattr(request.user, 'adviser_profile'):
        # Advisers see email logs for their assigned students
        adviser = request.user.adviser_profile
        adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
        logs = logs.filter(student_id__in=adviser_student_ids)
    else:
        # Other users filter by accessible courses
        accessible_courses = get_user_accessible_courses(request.user)
        if accessible_courses.exists():
            logs = logs.filter(student__course__in=accessible_courses)
        else:
            logs = logs.none()
    
    if email_type:
        logs = logs.filter(email_type=email_type)
    
    if date_from:
        try:
            logs = logs.filter(created_at__gte=datetime.strptime(date_from, '%Y-%m-%d'))
        except:
            pass
    
    if date_to:
        try:
            logs = logs.filter(created_at__lte=datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        except:
            pass
    
    logs = logs.order_by('-created_at')
    
    stats = {
        'total_sent': logs.filter(status='SENT').count(),
        'total_failed': logs.filter(status='FAILED').count(),
    }
    
    context = {
        'logs': logs,
        'email_type': email_type,
        'date_from': date_from,
        'date_to': date_to,
        'stats': stats,
    }
    return render(request, 'attendance/email_logs.html', context)

@login_required
def email_resend(request, log_id):
    log = get_object_or_404(EmailLog, id=log_id)
    
    if request.method == 'POST':
        # Resend email using the email utility
        success, error_message = resend_email(log)
        
        if success:
            messages.success(request, "Email resent successfully!")
        else:
            messages.error(request, f"Failed to resend: {error_message}")
    
    return redirect('email_logs')

# System Settings
@login_required
@login_required
def settings_view(request):
    settings = SystemSettings.get_settings()
    
    if request.method == 'POST':
        try:
            # Parse and validate dates
            semester_start_date_str = request.POST.get('semester_start_date')
            semester_end_date_str = request.POST.get('semester_end_date')
            
            if semester_start_date_str:
                settings.semester_start_date = datetime.strptime(semester_start_date_str, '%Y-%m-%d').date()
            if semester_end_date_str:
                settings.semester_end_date = datetime.strptime(semester_end_date_str, '%Y-%m-%d').date()
            
            # Validate that end date is after start date
            if settings.semester_start_date and settings.semester_end_date:
                if settings.semester_end_date < settings.semester_start_date:
                    messages.error(request, "Semester end date must be after start date.")
                    return render(request, 'attendance/settings.html', {'settings': settings})
            
            # Parse and validate times
            class_start_time_str = request.POST.get('class_start_time')
            class_end_time_str = request.POST.get('class_end_time')
            
            if class_start_time_str:
                # Handle both HH:MM and HH:MM:SS formats
                if len(class_start_time_str.split(':')) == 2:
                    settings.class_start_time = datetime.strptime(class_start_time_str, '%H:%M').time()
                else:
                    settings.class_start_time = datetime.strptime(class_start_time_str, '%H:%M:%S').time()
            
            if class_end_time_str:
                # Handle both HH:MM and HH:MM:SS formats
                if len(class_end_time_str.split(':')) == 2:
                    settings.class_end_time = datetime.strptime(class_end_time_str, '%H:%M').time()
                else:
                    settings.class_end_time = datetime.strptime(class_end_time_str, '%H:%M:%S').time()
            
            # Validate that end time is after start time
            if settings.class_start_time and settings.class_end_time:
                if settings.class_end_time <= settings.class_start_time:
                    messages.error(request, "Class end time must be after start time.")
                    return render(request, 'attendance/settings.html', {'settings': settings})
            
            # Parse integer fields with validation
            grace_period = request.POST.get('grace_period_minutes', '15')
            late_threshold = request.POST.get('late_threshold_minutes', '30')
            absent_threshold = request.POST.get('absent_threshold_percent', '50')
            send_warnings = request.POST.get('send_warnings_after', '3')
            data_retention = request.POST.get('data_retention_years', '5')
            early_attendance = request.POST.get('early_attendance_minutes', '30')
            late_attendance = request.POST.get('late_attendance_minutes', '60')
            
            settings.grace_period_minutes = int(grace_period) if grace_period else 15
            settings.late_threshold_minutes = int(late_threshold) if late_threshold else 30
            settings.absent_threshold_percent = int(absent_threshold) if absent_threshold else 50
            settings.send_warnings_after = int(send_warnings) if send_warnings else 3
            settings.data_retention_years = int(data_retention) if data_retention else 5
            settings.early_attendance_minutes = int(early_attendance) if early_attendance else 30
            settings.late_attendance_minutes = int(late_attendance) if late_attendance else 60
            
            # Validate percentage range
            if settings.absent_threshold_percent < 0 or settings.absent_threshold_percent > 100:
                messages.error(request, "Absent threshold must be between 0 and 100.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            # Validate minimum values
            if settings.grace_period_minutes < 0:
                messages.error(request, "Grace period cannot be negative.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            if settings.late_threshold_minutes < 0:
                messages.error(request, "Late threshold cannot be negative.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            if settings.send_warnings_after < 1:
                messages.error(request, "Send warnings after must be at least 1.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            if settings.data_retention_years < 1:
                messages.error(request, "Data retention years must be at least 1.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            if settings.early_attendance_minutes < 0:
                messages.error(request, "Early attendance minutes cannot be negative.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            if settings.late_attendance_minutes < 0:
                messages.error(request, "Late attendance minutes cannot be negative.")
                return render(request, 'attendance/settings.html', {'settings': settings})
            
            # Parse boolean fields
            settings.email_notifications_enabled = request.POST.get('email_notifications_enabled') == 'on'
            settings.auto_send_reports = request.POST.get('auto_send_reports') == 'on'
            settings.auto_backup_enabled = request.POST.get('auto_backup_enabled') == 'on'
            settings.enable_time_validation = request.POST.get('enable_time_validation') == 'on'
            
            # Save settings
            settings.save()
            # Invalidate cache after saving
            invalidate_settings_cache()
            messages.success(request, "Settings saved successfully!")
            return redirect('settings')
            
        except ValueError as e:
            messages.error(request, f"Invalid date or time format: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error saving settings: {str(e)}")
            import traceback
            traceback.print_exc()
    
    return render(request, 'attendance/settings.html', {'settings': settings})

# User Profile
@login_required
def profile_view(request):
    if request.method == 'POST':
        if 'update_profile' in request.POST:
            request.user.first_name = request.POST.get('first_name', '')
            request.user.last_name = request.POST.get('last_name', '')
            request.user.email = request.POST.get('email', '')
            request.user.save()
            messages.success(request, "Profile updated successfully!")
        
        elif 'change_password' in request.POST:
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if not request.user.check_password(old_password):
                messages.error(request, "Old password is incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            elif len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                messages.success(request, "Password changed successfully!")
                return redirect('login')
    
    return render(request, 'attendance/profile.html')

# Real-time Monitoring
@login_required
def live_monitor(request):
    subject_id = request.GET.get('subject_id')
    today = timezone.now().date()
    
    # Filter subjects by adviser first
    subjects_qs = filter_subjects_by_user(request.user).filter(is_active=True)
    
    active_subject = None
    if subject_id:
        active_subject = subjects_qs.filter(id=subject_id).first()
    
    if not active_subject:
        active_subject = subjects_qs.first()
    
    attendances = Attendance.objects.filter(date=today).select_related('student', 'subject')
    
    if active_subject:
        attendances = attendances.filter(subject=active_subject)
    else:
        # If no active subject, filter attendances to only show subjects accessible by user
        accessible_subject_ids = subjects_qs.values_list('id', flat=True)
        attendances = attendances.filter(subject_id__in=accessible_subject_ids)
    
    recent_activity = attendances.order_by('-time_in', '-time', '-created_at')[:10]
    
    stats = {
        'present': attendances.filter(status='PRESENT').count(),
        'absent': attendances.filter(status='ABSENT').count(),
        'late': attendances.filter(status='LATE').count(),
        'total': attendances.count(),
    }
    
    context = {
        'active_subject': active_subject,
        'subjects': subjects_qs,
        'recent_activity': recent_activity,
        'stats': stats,
        'current_time': timezone.now(),
    }
    return render(request, 'attendance/live_monitor.html', context)

@login_required
def live_monitor_api(request):
    """API endpoint for real-time updates"""
    subject_id = request.GET.get('subject_id')
    today = timezone.now().date()
    
    attendances = Attendance.objects.filter(date=today).select_related('student', 'subject')
    
    if subject_id:
        attendances = attendances.filter(subject_id=subject_id)
    
    recent = attendances.order_by('-time_in', '-time', '-created_at')[:5]
    
    data = {
        'stats': {
            'present': attendances.filter(status='PRESENT').count(),
            'absent': attendances.filter(status='ABSENT').count(),
            'late': attendances.filter(status='LATE').count(),
            'total': attendances.count(),
        },
        'recent_activity': [
            {
                'student_name': att.student.name,
                'subject': att.subject.code,
                'time': att.time_in.strftime('%I:%M %p') if att.time_in else (att.time.strftime('%I:%M %p') if att.time else '--:--'),
                'time_in': att.time_in.strftime('%I:%M %p') if att.time_in else None,
                'time_out': att.time_out.strftime('%I:%M %p') if att.time_out else None,
                'status': att.status,
            }
            for att in recent
        ],
        'timestamp': timezone.now().isoformat(),
    }
    
    return JsonResponse(data)

@login_required
def enrollment_requests_count_api(request):
    """API endpoint to get pending enrollment requests count"""
    try:
        # For staff/superuser, show all pending. For regular users, show their assigned students
        if request.user.is_staff or request.user.is_superuser:
            pending_count = EnrollmentRequest.objects.filter(status='PENDING').count()
        else:
            if hasattr(request.user, 'adviser_profile'):
                # Advisers see enrollment requests only for subjects where instructor belongs to this adviser
                adviser = request.user.adviser_profile
                pending_count = EnrollmentRequest.objects.filter(
                    status='PENDING',
                    subject__instructor__adviser=adviser
                ).count()
            else:
                pending_count = 0
        
        return JsonResponse({
            'pending_count': pending_count,
            'success': True
        })
    except Exception as e:
        return JsonResponse({
            'pending_count': 0,
            'success': False,
            'error': str(e)
        }, status=500)

# Mobile View
def mobile_scan(request):
    """Mobile-optimized RFID scan view"""
    active_subject = Subject.objects.filter(is_active=True).first()
    last_scan = Attendance.objects.select_related('student', 'subject').order_by('-created_at').first()
    
    context = {
        'subject': active_subject,
        'last_scan': last_scan,
    }
    
    if request.method == 'POST':
        rfid_id = request.POST.get('rfid_id', '').strip()
        student_id = request.POST.get('student_id', '').strip()
        
        if not rfid_id and not student_id:
            messages.error(request, "Please scan RFID card or enter Student ID.")
        else:
            try:
                if rfid_id:
                    student = Student.objects.get(rfid_id=rfid_id)
                else:
                    student = Student.objects.get(student_id=student_id)
                
                if active_subject:
                    # Check if student is enrolled in this subject (any semester/year)
                    enrollment = StudentSubject.objects.filter(
                        student=student,
                        subject=active_subject
                    ).first()
                    
                    if not enrollment:
                        # Get list of subjects student is enrolled in for better error message
                        student_subjects = StudentSubject.objects.filter(
                            student=student
                        ).select_related('subject').values_list('subject__code', 'subject__name')
                        
                        enrolled_list = ', '.join([f"{code} - {name}" for code, name in student_subjects]) if student_subjects else 'None'
                        
                        error_msg = (
                            f"✗ Enrollment Error: {student.name} (RFID: {rfid_id or student_id}) is not enrolled in {active_subject.code} - {active_subject.name}. "
                            f"Student's enrolled subjects: {enrolled_list if enrolled_list != 'None' else 'None (no enrollments found)'}"
                        )
                        
                        messages.error(request, error_msg)
                    else:
                        # Get current time in Manila timezone
                        now_manila = get_manila_now()
                        today = now_manila.date()
                        settings = SystemSettings.get_settings()
                        scan_time = now_manila.time()  # Use actual time with seconds for validation

                        # Check if student already has both time_in and time_out recorded for today
                        existing_attendance_check = Attendance.objects.filter(
                            student=student,
                            subject=active_subject,
                            date=today
                        ).first()

                        if existing_attendance_check and existing_attendance_check.time_in and existing_attendance_check.time_out:
                            # Student already has both time_in and time_out
                            time_in_str = existing_attendance_check.time_in.strftime('%I:%M %p')
                            time_out_str = existing_attendance_check.time_out.strftime('%I:%M %p')
                            messages.info(request, f"ℹ You already have time in and time out recorded for today. Time In: {time_in_str}, Time Out: {time_out_str}")
                        else:
                            # Validate attendance time and date
                            is_valid, error_message, schedule = validate_attendance_time(
                                active_subject, today, scan_time, settings
                            )

                            if not is_valid:
                                # Check if the error is about time window being closed
                                if "not allowed at this time" in error_message.lower() or "valid time window" in error_message.lower():
                                    messages.error(request, f"✗ The time is no longer available. {error_message}")
                                else:
                                    messages.error(request, f"✗ {error_message}")
                            else:
                                # Normalize time only when storing to database (remove seconds/microseconds)
                                stored_time = scan_time.replace(second=0, microsecond=0)

                                # Use transaction with locking to prevent duplicate records
                                with transaction.atomic():
                                    # Get or create attendance record - only ONE record per student/subject/date
                                    existing_attendance, created = Attendance.objects.select_for_update().get_or_create(
                                        student=student,
                                        subject=active_subject,
                                        date=today,
                                        defaults={
                                            'time': stored_time,
                                            'time_in': stored_time,
                                            'status': 'PRESENT'
                                        }
                                    )

                                    # Determine status based on time
                                    class_start = None
                                    if schedule:
                                        class_start = schedule.time_start
                                    elif active_subject.schedule_time_start:
                                        class_start = active_subject.schedule_time_start
                                    else:
                                        class_start = settings.class_start_time

                                    status = 'PRESENT'
                                    if class_start:
                                        scan_datetime = make_aware_datetime(today, scan_time)
                                        start_datetime = make_aware_datetime(today, class_start)

                                        # Calculate time difference in minutes
                                        time_diff = scan_datetime - start_datetime
                                        minutes_late = time_diff.total_seconds() / 60

                                        # If grace_period_minutes or more late, mark as LATE
                                        if minutes_late >= settings.grace_period_minutes:
                                            status = 'LATE'
                                        else:
                                            status = 'PRESENT'

                                        # Check if this should be a time-out or time-in update
                                        should_do_timeout = False
                                        if not created and existing_attendance.time_out is None:
                                            # Student has an existing time-in without time_out
                                            # Check if this is a valid time-out attempt
                                            is_timeout_valid, timeout_error = validate_timeout_time(
                                                active_subject, today, scan_time, schedule, settings
                                            )

                                            if is_timeout_valid:
                                                should_do_timeout = True

                                        if should_do_timeout:
                                            # Valid time-out - student is checking out
                                            # Only update if time_out is not already set or if new time is different
                                            if existing_attendance.time_out is None or existing_attendance.time_out != stored_time:
                                                existing_attendance.time_out = stored_time
                                                existing_attendance.save(update_fields=['time_out'])
                                                time_in_str = existing_attendance.time_in.strftime('%I:%M %p') if existing_attendance.time_in else 'N/A'
                                                time_out_str = existing_attendance.time_out.strftime('%I:%M %p')
                                                messages.success(request, f"✓ Time Out! {student.name} - Time In: {time_in_str}, Time Out: {time_out_str}")

                                                # Send email notification for check-out
                                                send_attendance_confirmation_email(
                                                    student=student,
                                                    subject=active_subject,
                                                    attendance_date=today,
                                                    time_in=existing_attendance.time_in,
                                                    time_out=existing_attendance.time_out,
                                                    status=existing_attendance.status
                                                )
                                            else:
                                                # Time-out already recorded at this time - no duplicate
                                                time_in_str = existing_attendance.time_in.strftime('%I:%M %p') if existing_attendance.time_in else 'N/A'
                                                time_out_str = existing_attendance.time_out.strftime('%I:%M %p') if existing_attendance.time_out else 'N/A'
                                                messages.info(request, f"ℹ Time-out already recorded at {time_out_str}. No duplicate created.")
                                        else:
                                            # Student is checking in (time in) or updating existing record
                                            # Only update if time_in is not set or if new time is different
                                            if existing_attendance.time_in is None or existing_attendance.time_in != stored_time:
                                                existing_attendance.time = stored_time  # Keep for backward compatibility
                                                existing_attendance.time_in = stored_time
                                                existing_attendance.status = status
                                                existing_attendance.save(update_fields=['time', 'time_in', 'status'])
                                                messages.success(request, f"✓ Time In! {student.name} - {status} at {stored_time.strftime('%I:%M %p')}")

                                                # Send email notification for check-in
                                                send_attendance_confirmation_email(
                                                    student=student,
                                                    subject=active_subject,
                                                    attendance_date=today,
                                                    time_in=stored_time,
                                                    time_out=None,
                                                    status=status
                                                )

                                                # Check and send warning email if student has reached absence threshold
                                                if status == 'ABSENT':
                                                    check_and_send_warning_email(student, active_subject)
                                            else:
                                                # Time-in already recorded at this time - no duplicate
                                                time_in_str = existing_attendance.time_in.strftime('%I:%M %p') if existing_attendance.time_in else 'N/A'
                                                messages.info(request, f"ℹ Time-in already recorded at {time_in_str}. No duplicate created.")
                else:
                    messages.error(request, "No active subject found.")
            except Student.DoesNotExist:
                messages.error(request, "✗ Student not found")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    
    return render(request, 'attendance/mobile_scan.html', context)

# Student View (Public)
def student_view(request):
    student = None
    attendances = Attendance.objects.none()
    stats = {
        'total_present': 0,
        'total_absent': 0,
        'total_late': 0,
        'total_records': 0,
        'attendance_rate': 0.0
    }
    
    if request.method == 'POST':
        rfid_id = request.POST.get('rfid_id', '').strip()
        
        if not rfid_id:
            messages.error(request, "Please enter your RFID ID.")
        else:
            try:
                student = Student.objects.get(rfid_id=rfid_id)
                attendances = Attendance.objects.filter(student=student).order_by('-date', '-time')
                
                stats['total_present'] = attendances.filter(status='PRESENT').count()
                stats['total_absent'] = attendances.filter(status='ABSENT').count()
                stats['total_late'] = attendances.filter(status='LATE').count()
                stats['total_records'] = attendances.count()
                
                if stats['total_records'] > 0:
                    stats['attendance_rate'] = round((stats['total_present'] / stats['total_records']) * 100, 2)
                
            except Student.DoesNotExist:
                messages.error(request, "RFID ID not found.")
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
    
    context = {
        'student': student,
        'attendances': attendances,
        'stats': stats,
    }
    return render(request, 'attendance/student_view.html', context)

# Student Login and Dashboard
def student_register(request):
    """Student registration view - allows students to create an account"""
    if request.user.is_authenticated:
        # Check if user is a student
        if hasattr(request.user, 'student_profile'):
            return redirect('student_dashboard')
        else:
            # If admin/staff, redirect to admin dashboard
            return redirect('dashboard')
    
    # Get active courses for the dropdown
    courses = Course.objects.filter(is_active=True).order_by('code')
    # Get all advisers for the dropdown
    advisers = Adviser.objects.all().order_by('name')
    # Get active sections for the dropdown
    sections = Section.objects.filter(is_active=True).order_by('code')
    
    if request.method == 'POST':
        # Get form data
        rfid_id = request.POST.get('rfid_id', '').strip()
        student_id = request.POST.get('student_id', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        middle_name = request.POST.get('middle_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()  # Normalize email to lowercase
        course_id = request.POST.get('course', '').strip()
        section_id = request.POST.get('section', '').strip()
        adviser_id = request.POST.get('adviser', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        
        # Combine name parts and convert to uppercase
        name_parts = [part for part in [first_name, middle_name, last_name] if part]
        name = ' '.join(name_parts).upper() if name_parts else ''
        
        # Validation
        errors = []
        
        if not rfid_id:
            errors.append("RFID ID is required.")
        elif Student.objects.filter(rfid_id=rfid_id).exists():
            errors.append("This RFID ID is already registered.")
        
        if student_id and Student.objects.filter(student_id=student_id).exists():
            errors.append("This Student ID is already registered.")
        
        if not first_name:
            errors.append("First name is required.")
        
        if not last_name:
            errors.append("Last name is required.")
        
        if not email:
            errors.append("Email is required.")
        else:
            # Check if email exists in User table (case-insensitive)
            existing_user = User.objects.filter(email__iexact=email).first()
            if existing_user:
                # Check if this user is already linked to a student
                if hasattr(existing_user, 'student_profile'):
                    errors.append("This email is already registered.")
                # If user exists but has no student_profile, allow registration
                # (might be an orphaned user from a failed registration)
            
            # Check if email exists in Student table (case-insensitive)
            if Student.objects.filter(email__iexact=email).exists():
                errors.append("This email is already registered.")
        
        # Validate and get course object
        course_obj = None
        if not course_id:
            errors.append("Course is required.")
        else:
            try:
                course_obj = Course.objects.get(id=course_id, is_active=True)
            except Course.DoesNotExist:
                errors.append("Please select a valid course.")
        
        # Validate and get section object (required)
        section_obj = None
        if not section_id:
            errors.append("Section is required.")
        else:
            try:
                section_obj = Section.objects.get(id=int(section_id), is_active=True)
            except (Section.DoesNotExist, ValueError):
                errors.append("Please select a valid section.")
        
        # Validate and get adviser object (optional)
        adviser_obj = None
        if adviser_id:
            try:
                adviser_obj = Adviser.objects.get(id=int(adviser_id))
            except (Adviser.DoesNotExist, ValueError):
                errors.append("Please select a valid adviser.")
        
        if not password:
            errors.append("Password is required.")
        elif len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        
        if password != password_confirm:
            errors.append("Passwords do not match.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                # Use database transaction to ensure all data is saved atomically
                with transaction.atomic():
                    # Check if User already exists with this email (case-insensitive)
                    existing_user = User.objects.filter(email__iexact=email).first()
                    
                    if existing_user and not hasattr(existing_user, 'student_profile'):
                        # Reuse existing user (from a failed registration attempt)
                        user = existing_user
                        user.set_password(password)  # Update password
                        user.first_name = first_name.upper()
                        user.last_name = last_name.upper()
                        user.email = email  # Email is already normalized
                        user.save()
                    else:
                        # Create new User account
                        username = email  # Use email as username (already normalized)
                        if User.objects.filter(username=username).exists():
                            # If username exists, append a number
                            counter = 1
                            while User.objects.filter(username=f"{username}{counter}").exists():
                                counter += 1
                            username = f"{username}{counter}"
                        
                        user = User.objects.create_user(
                            username=username,
                            email=email,  # Email is already normalized
                            password=password,
                            first_name=first_name.upper(),
                            last_name=last_name.upper()
                        )
                    
                    # Create Student record with all form fields
                    student = Student.objects.create(
                        rfid_id=rfid_id,
                        student_id=student_id if student_id else None,  # Save student_id if provided
                        name=name,
                        email=email,  # Email is already normalized
                        course=course_obj,
                        section=section_obj,  # Section is required
                        adviser=adviser_obj,  # Save adviser if provided
                        user=user
                    )
                
                # All data saved successfully
                # Send registration confirmation email
                try:
                    email_subject = "Registration Successful - Attendance RFID Monitoring System"
                    masked_email = mask_email(student.email)
                    email_body = f"""Dear {student.name},

Congratulations! You have successfully registered in the Attendance RFID Monitoring System.

Your registration details:
- Name: {student.name}
- Email: {masked_email}
- RFID ID: {student.rfid_id}
- Student ID: {student.student_id if student.student_id else 'Not provided'}
- Course: {student.course.name if student.course else 'Not assigned'}
- Section: {student.section.name if student.section else 'Not assigned'}
- Adviser: {student.adviser.name if student.adviser else 'Not assigned'}

You can now log in to the system using your RFID ID to track your attendance.

Thank you for registering!

Best regards,
Attendance RFID Monitoring System"""
                    
                    send_attendance_email(
                        student=student,
                        email_to=student.email,  # Use student.email instead of email variable
                        subject=email_subject,
                        message_body=email_body,
                        email_type='CUSTOM',
                        silent=False
                    )
                    messages.success(request, f"Registration successful! A confirmation email has been sent to {masked_email}. You can now login with your RFID ID.")
                except Exception as email_error:
                    # Log email error but don't fail registration
                    logger.error(f"Failed to send registration email to {student.email}: {str(email_error)}")
                    messages.success(request, "Registration successful! However, the confirmation email could not be sent. You can now login with your RFID ID.")
                
                return redirect('student_login')
                
            except Exception as e:
                # Transaction will automatically rollback on exception
                messages.error(request, f"An error occurred during registration: {str(e)}")
                print(f"Registration error: {traceback.format_exc()}")  # Log for debugging
    
    return render(request, 'attendance/student_register.html', {'courses': courses, 'advisers': advisers, 'sections': sections})

def student_login(request):
    """Student login view - students login with RFID ID only"""
    if request.user.is_authenticated:
        # Check if user is a student
        if hasattr(request.user, 'student_profile'):
            return redirect('student_dashboard')
        else:
            # If admin/staff, redirect to admin dashboard
            return redirect('dashboard')
    
    if request.method == 'POST':
        rfid_id = request.POST.get('rfid_id', '').strip()
        
        if not rfid_id:
            messages.error(request, "Please enter your RFID ID.")
        else:
            try:
                # Find student by RFID ID
                student = Student.objects.get(rfid_id=rfid_id)
                
                # Check if student has a linked user account
                if student.user:
                    # Log in the student using their linked user account
                    user = student.user
                    login(request, user)
                    messages.success(request, f"Welcome, {student.name}!")
                    return redirect('student_dashboard')
                else:
                    # Automatically create a user account for the student
                    try:
                        # Generate username from student_id or rfid_id
                        username = student.student_id or student.rfid_id
                        if not username:
                            messages.error(request, "Student account cannot be created. Please contact your administrator.")
                            return render(request, 'attendance/student_login.html')
                        
                        # Check if username already exists
                        if User.objects.filter(username=username).exists():
                            # Try with email prefix
                            username = student.email.split('@')[0]
                            if User.objects.filter(username=username).exists():
                                # Try with rfid_id prefix
                                username = f"student_{student.rfid_id}"
                        
                        # Create user with unusable password (since login is via RFID only)
                        # Use a temporary password first, then set it to unusable
                        user = User.objects.create_user(
                            username=username,
                            email=student.email,
                            password='temp_password_123',  # Temporary password, will be set to unusable
                            first_name=student.name.split()[0] if student.name.split() else '',
                            last_name=' '.join(student.name.split()[1:]) if len(student.name.split()) > 1 else '',
                        )
                        user.set_unusable_password()  # Set unusable password since login is via RFID
                        user.save()
                        
                        # Link student to user
                        student.user = user
                        student.save()
                        
                        # Log in the student
                        login(request, user)
                        messages.success(request, f"Welcome, {student.name}!")
                        return redirect('student_dashboard')
                    except Exception as e:
                        messages.error(request, f"Error creating account: {str(e)}. Please contact your administrator.")
            except Student.DoesNotExist:
                messages.error(request, "RFID ID not found. Please check your RFID ID and try again.")
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
    
    return render(request, 'attendance/student_login.html')

@login_required
def student_dashboard(request):
    """Student dashboard showing their absences and attendance"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "Student profile not found. Please contact administrator.")
        logout(request)
        return redirect('student_login')
    
    # Get filter parameters
    subject_id = request.GET.get('subject_id', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    time_filter = request.GET.get('time_filter', '')  # new, yesterday, past_week
    academic_year = request.GET.get('academic_year', '2025-2026')
    semester = request.GET.get('semester', '1st Semester')
    
    # Calculate date ranges for time filters
    today = timezone.localtime().date()
    yesterday = today - timedelta(days=1)
    past_week_start = today - timedelta(days=7)
    
    # Get all attendances for this student
    attendances = Attendance.objects.filter(student=student).select_related('subject')
    
    # Filter by subject if provided
    if subject_id:
        try:
            attendances_qs = attendances_qs.filter(subject_id=int(subject_id))
        except (ValueError, TypeError):
            pass
    
    # Filter by date range if provided
    if date_from:
        try:
            attendances = attendances.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except:
            pass
    
    if date_to:
        try:
            attendances = attendances.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except:
            pass
    
    # Get absences specifically
    absences = attendances.filter(status='ABSENT')
    
    # Get subjects for this student
    student_subjects = StudentSubject.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester
    ).select_related('subject')
    
    # Calculate statistics
    total_attendances = attendances.count()
    total_present = attendances.filter(status='PRESENT').count()
    total_absent = attendances.filter(status='ABSENT').count()
    total_late = attendances.filter(status='LATE').count()
    
    attendance_rate = 0.0
    if total_attendances > 0:
        attendance_rate = round((total_present / total_attendances) * 100, 2)
    
    # Get subject-wise statistics
    subject_stats = []
    for ss in student_subjects:
        subject_attendances = attendances.filter(subject=ss.subject)
        subject_total = subject_attendances.count()
        subject_present = subject_attendances.filter(status='PRESENT').count()
        subject_absent = subject_attendances.filter(status='ABSENT').count()
        subject_late = subject_attendances.filter(status='LATE').count()
        subject_rate = round((subject_present / subject_total * 100) if subject_total > 0 else 0, 2)
        
        subject_stats.append({
            'subject': ss.subject,
            'total': subject_total,
            'present': subject_present,
            'absent': subject_absent,
            'late': subject_late,
            'rate': subject_rate,
        })
    
    # Paginate absences
    paginator = Paginator(absences, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get recent attendance records with time in/out (for display)
    # Use the same filtered attendances but exclude absences and limit to 50 most recent
    # Order by date (most recent first), then by time fields
    recent_attendances_qs = attendances.exclude(status='ABSENT').order_by(
        '-date', 
        '-time_out', 
        '-time_in', 
        '-time'
    )[:50]
    
    # Create time-filtered attendance lists for tabs
    # Today's records (New)
    today_attendances_qs = attendances.exclude(status='ABSENT').filter(date=today).order_by(
        '-time_out', '-time_in', '-time'
    )
    
    # Yesterday's records
    yesterday_attendances_qs = attendances.exclude(status='ABSENT').filter(date=yesterday).order_by(
        '-time_out', '-time_in', '-time'
    )
    
    # Past week records (last 7 days, excluding today)
    past_week_attendances_qs = attendances.exclude(status='ABSENT').filter(
        date__gte=past_week_start,
        date__lt=today
    ).order_by('-date', '-time_out', '-time_in', '-time')
    
    # Helper function to format attendance records
    def format_attendance_records(qs):
        records = []
        for att in qs:
            time_in_str = None
            if att.time_in:
                time_in_str = att.time_in.strftime('%I:%M %p')
            elif att.time:
                time_in_str = att.time.strftime('%I:%M %p')
            
            time_out_str = None
            if att.time_out:
                time_out_str = att.time_out.strftime('%I:%M %p')
            
            records.append({
                'attendance': att,
                'time_in_formatted': time_in_str,
                'time_out_formatted': time_out_str,
            })
        return records
    
    # Format all attendance records
    recent_attendances = format_attendance_records(recent_attendances_qs)
    today_attendances = format_attendance_records(today_attendances_qs)
    yesterday_attendances = format_attendance_records(yesterday_attendances_qs)
    past_week_attendances = format_attendance_records(past_week_attendances_qs)
    
    # Get counts for tab badges
    today_count = today_attendances_qs.count()
    yesterday_count = yesterday_attendances_qs.count()
    past_week_count = past_week_attendances_qs.count()
    
    # Convert subject_id to int for template comparison
    selected_subject_id_int = None
    if subject_id:
        try:
            selected_subject_id_int = int(subject_id)
        except (ValueError, TypeError):
            pass
    
    context = {
        'student': student,
        'absences': page_obj,
        'recent_attendances': recent_attendances,
        'today_attendances': today_attendances,
        'yesterday_attendances': yesterday_attendances,
        'past_week_attendances': past_week_attendances,
        'today_count': today_count,
        'yesterday_count': yesterday_count,
        'past_week_count': past_week_count,
        'today_date': today,
        'yesterday_date': yesterday,
        'past_week_start': past_week_start,
        'total_attendances': total_attendances,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_late': total_late,
        'attendance_rate': attendance_rate,
        'subject_stats': subject_stats,
        'subjects': [ss.subject for ss in student_subjects],
        'selected_subject_id': subject_id,
        'selected_subject_id_int': selected_subject_id_int,
        'date_from': date_from,
        'date_to': date_to,
        'time_filter': time_filter,
        'academic_year': academic_year,
        'semester': semester,
    }
    return render(request, 'attendance/student_dashboard.html', context)

@login_required
def student_enroll_subjects(request):
    """Student view to enroll/unenroll in subjects"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "Student profile not found. Please contact administrator.")
        logout(request)
        return redirect('student_login')
    
    academic_year = request.GET.get('academic_year', '2025-2026')
    semester = request.GET.get('semester', '1st Semester')
    
    if request.method == 'POST':
        academic_year = request.POST.get('academic_year', academic_year)
        semester = request.POST.get('semester', semester)
        action = request.POST.get('action')
        subject_id = request.POST.get('subject_id')
        
        try:
            subject = Subject.objects.get(id=subject_id, is_active=True)
            
            if action == 'enroll':
                # Check if already enrolled
                existing_enrollment = StudentSubject.objects.filter(
                    student=student,
                    subject=subject,
                    academic_year=academic_year,
                    semester=semester,
                ).exists()
                
                if existing_enrollment:
                    messages.info(request, f"You are already enrolled in {subject.code} - {subject.name}.")
                else:
                    # Check if there's already a pending request
                    pending_request = EnrollmentRequest.objects.filter(
                        student=student,
                        subject=subject,
                        academic_year=academic_year,
                        semester=semester,
                        status='PENDING'
                    ).exists()
                    
                    if pending_request:
                        messages.info(request, f"You already have a pending enrollment request for {subject.code} - {subject.name}. Please wait for your adviser's approval.")
                    else:
                        # Create enrollment request (pending adviser approval)
                        EnrollmentRequest.objects.create(
                            student=student,
                            subject=subject,
                            academic_year=academic_year,
                            semester=semester,
                            status='PENDING'
                        )
                        messages.success(request, f"Enrollment request submitted for {subject.code} - {subject.name}! Your adviser will review and confirm your enrollment.")
            
            elif action == 'unenroll':
                # Unenroll student from subject (no confirmation needed for unenrollment)
                deleted = StudentSubject.objects.filter(
                    student=student,
                    subject=subject,
                    academic_year=academic_year,
                    semester=semester,
                ).delete()
                if deleted[0] > 0:
                    messages.success(request, f"Successfully unenrolled from {subject.code} - {subject.name}!")
                else:
                    messages.warning(request, f"You are not enrolled in {subject.code} - {subject.name}.")
        
        except Subject.DoesNotExist:
            messages.error(request, "Subject not found or is not active.")
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
    
    # Get all active subjects with prefetched schedules
    all_subjects = Subject.objects.filter(is_active=True).prefetch_related('schedules').order_by('code')
    
    # Get enrolled subject IDs for current academic year and semester
    enrolled_subject_ids = StudentSubject.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester
    ).values_list('subject_id', flat=True)
    
    # Get pending request subject IDs
    pending_subject_ids = EnrollmentRequest.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester,
        status='PENDING'
    ).values_list('subject_id', flat=True)
    
    # Prepare subject data with enrollment status
    subjects_data = []
    for subject in all_subjects:
        is_enrolled = subject.id in enrolled_subject_ids
        is_pending = subject.id in pending_subject_ids
        subjects_data.append({
            'subject': subject,
            'is_enrolled': is_enrolled,
            'is_pending': is_pending,
        })
    
    context = {
        'student': student,
        'subjects_data': subjects_data,
        'academic_year': academic_year,
        'semester': semester,
        'enrolled_count': len(enrolled_subject_ids),
        'total_count': all_subjects.count(),
    }
    return render(request, 'attendance/student_enroll_subjects.html', context)

@login_required
def student_logout(request):
    """Student logout view"""
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('student_login')

@login_required
def student_features_view(request):
    """Student features dashboard showing all available features and statistics"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "Student profile not found. Please contact administrator.")
        logout(request)
        return redirect('student_login')
    
    # Get all attendances for this student
    attendances = Attendance.objects.filter(student=student).select_related('subject').order_by('-date', '-time')
    
    # Today's attendance statistics
    today = timezone.now().date()
    today_attendance = attendances.filter(date=today)
    present_today = today_attendance.filter(status='PRESENT').count()
    absent_today = today_attendance.filter(status='ABSENT').count()
    late_today = today_attendance.filter(status='LATE').count()
    
    # Overall statistics
    total_attendances = attendances.count()
    total_present = attendances.filter(status='PRESENT').count()
    persisted_absent = attendances.filter(status='ABSENT').count()
    total_late = attendances.filter(status='LATE').count()

    # Compute virtual absences based on schedules and system semester range
    settings_obj = get_cached_settings()
    start_date = settings_obj.semester_start_date
    end_date = settings_obj.semester_end_date

    # Persisted attendances within semester range
    attendances_semester = attendances.filter(date__gte=start_date, date__lte=end_date)
    existing_keys = set(attendances_semester.values_list('subject_id', 'date'))

    # Cap virtual absence generation to today only after the configured class end time
    # This prevents today's sessions from being counted as ABSENT until the day has ended
    manila_now = get_manila_now()
    today_date = manila_now.date()
    # If the semester end is before or equal to today, use semester end; otherwise
    # only include today if current Manila time is on/after settings.class_end_time
    if end_date <= today_date:
        effective_end_for_absences = end_date
    else:
        try:
            if manila_now.time() >= settings_obj.class_end_time:
                effective_end_for_absences = today_date
            else:
                effective_end_for_absences = today_date - timedelta(days=1)
        except Exception:
            # Fallback: if any error, don't include today
            effective_end_for_absences = today_date - timedelta(days=1)

    # Determine academic year and semester defaults from SystemSettings
    # Academic year default: "{start_year}-{end_year}"
    # Semester default: split the semester range in half; dates on or before midpoint -> '1st Semester', otherwise '2nd Semester'
    start = settings_obj.semester_start_date
    end = settings_obj.semester_end_date
    try:
        academic_year_default = f"{start.year}-{end.year}"
    except Exception:
        academic_year_default = request.GET.get('academic_year', '2025-2026')

    try:
        today_date = timezone.now().date()
        midpoint = start + (end - start) / 2
        semester_default = '1st Semester' if today_date <= midpoint else '2nd Semester'
    except Exception:
        semester_default = request.GET.get('semester', '1st Semester')

    academic_year = request.GET.get('academic_year', academic_year_default)
    semester = request.GET.get('semester', semester_default)

    # Enrolled subjects for this student in the selected academic year/semester
    student_subjects = StudentSubject.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester
    ).select_related('subject')

    total_virtual_absent = 0
    subject_virtual_map = {}
    for ss in student_subjects:
        subj = ss.subject
        virtual_count = 0

        # Specific date schedules
        date_scheds = SubjectSchedule.objects.filter(subject=subj, date__isnull=False)
        for ds in date_scheds:
            sess_date = ds.date
            # Only count scheduled dates up to today (effective_end_for_absences)
            if start_date <= sess_date <= effective_end_for_absences:
                key = (subj.id, sess_date)
                if key not in existing_keys:
                    virtual_count += 1

        # Weekly schedules
        weekly_scheds = SubjectSchedule.objects.filter(subject=subj, date__isnull=True)
        day_map = set([s.day_of_week for s in weekly_scheds if s.day_of_week is not None])
        if day_map:
            current = start_date
            # Only iterate up to effective_end_for_absences to avoid future dates
            while current <= effective_end_for_absences:
                if current.weekday() in day_map:
                    key = (subj.id, current)
                    if key not in existing_keys:
                        virtual_count += 1
                current += timedelta(days=1)

        subject_virtual_map[subj.id] = virtual_count
        total_virtual_absent += virtual_count

    # Final totals include persisted absents + virtual absents
    total_absent = persisted_absent + total_virtual_absent

    # Compute attendance rate. Treat LATE as attended for rate calculations.
    attended_count = total_present + total_late
    total_expected = attended_count + total_absent
    attendance_rate = 0.0
    if total_expected > 0:
        attendance_rate = round((attended_count / total_expected) * 100, 2)
    
    # (student_subjects already initialized above using SystemSettings defaults)
    
    # Get pending enrollment requests
    pending_enrollments = EnrollmentRequest.objects.filter(
        student=student,
        academic_year=academic_year,
        semester=semester,
        status='PENDING'
    ).count()
    
    # Recent attendance (last 10)
    recent_attendance = attendances.select_related('subject').order_by('-date', '-time_in', '-time')[:10]
    
    # Subject-wise statistics
    subject_stats = []
    for ss in student_subjects:
        subject_attendances = attendances.filter(subject=ss.subject)
        subject_present = subject_attendances.filter(status='PRESENT').count()
        subject_late = subject_attendances.filter(status='LATE').count()
        subject_absent_persisted = subject_attendances.filter(status='ABSENT').count()
        subject_virtual = subject_virtual_map.get(ss.subject.id, 0)

        # Total expected sessions for the subject (persisted + virtual absents)
        subject_total_expected = subject_present + subject_late + subject_absent_persisted + subject_virtual
        # Rate treats LATE as attended
        subject_attended = subject_present + subject_late
        subject_rate = round((subject_attended / subject_total_expected * 100) if subject_total_expected > 0 else 0, 2)
        
        # Today's stats for this subject
        subject_today = today_attendance.filter(subject=ss.subject)
        subject_present_today = subject_today.filter(status='PRESENT').count()
        subject_absent_today = subject_today.filter(status='ABSENT').count()
        subject_late_today = subject_today.filter(status='LATE').count()
        
        subject_stats.append({
            'subject': ss.subject,
            'total': subject_total_expected,
            'present': subject_present,
            'absent': subject_absent_persisted + subject_virtual,
            'late': subject_late,
            'rate': subject_rate,
            'present_today': subject_present_today,
            'absent_today': subject_absent_today,
            'late_today': subject_late_today,
        })
    
    context = {
        'student': student,
        'total_attendances': total_attendances,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_late': total_late,
        'attendance_rate': attendance_rate,
        'present_today': present_today,
        'absent_today': absent_today,
        'late_today': late_today,
        'pending_enrollments': pending_enrollments,
        'recent_attendance': recent_attendance,
        'subject_stats': subject_stats,
        'enrolled_subjects_count': student_subjects.count(),
        'academic_year': academic_year,
        'semester': semester,
    }
    return render(request, 'attendance/student_features.html', context)

@login_required
def student_profile_view(request):
    """Student profile view with profile picture upload"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "Student profile not found. Please contact administrator.")
        logout(request)
        return redirect('student_login')
    
    if request.method == 'POST':
        if 'upload_picture' in request.POST:
            cropped_image_data = request.POST.get('cropped_image')
            profile_picture = request.FILES.get('profile_picture')

            # Prefer cropped image data if provided
            if cropped_image_data:
                try:
                    header, encoded = cropped_image_data.split(';base64,')
                    mime_type = header.replace('data:', '') or 'image/jpeg'
                    image_bytes = base64.b64decode(encoded)

                    if len(image_bytes) > 5 * 1024 * 1024:
                        messages.error(request, "Image size must be less than 5MB.")
                        profile_picture = None
                    else:
                        # Determine file extension based on MIME type
                        ext = 'jpg'
                        if 'png' in mime_type:
                            ext = 'png'
                        elif 'gif' in mime_type:
                            ext = 'gif'

                        profile_picture = SimpleUploadedFile(
                            f"profile_cropped_{student.id}.{ext}",
                            image_bytes,
                            content_type=mime_type
                        )
                except Exception as exc:
                    logger.exception("Failed to decode cropped image", exc_info=exc)
                    messages.error(request, "Could not process cropped image. Please try again.")
                    profile_picture = None

            if profile_picture:
                # Validate file size (max 5MB)
                if profile_picture.size > 5 * 1024 * 1024:
                    messages.error(request, "Image size must be less than 5MB.")
                else:
                    # Validate file type
                    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
                    if profile_picture.content_type not in allowed_types:
                        messages.error(request, "Please upload a valid image file (JPEG, PNG, or GIF).")
                    else:
                        # Delete old profile picture if exists
                        if student.profile_picture:
                            try:
                                os.remove(student.profile_picture.path)
                            except:
                                pass
                        
                        student.profile_picture = profile_picture
                        student.save()
                        messages.success(request, "Profile picture uploaded successfully!")
                        return redirect('student_profile')
            else:
                messages.error(request, "Please select an image file.")
        
        elif 'remove_picture' in request.POST:
            if student.profile_picture:
                try:
                    os.remove(student.profile_picture.path)
                except:
                    pass
                student.profile_picture = None
                student.save()
                messages.success(request, "Profile picture removed successfully!")
            return redirect('student_profile')
        
        elif 'update_profile' in request.POST:
            # Update user information
            request.user.first_name = request.POST.get('first_name', '')
            request.user.last_name = request.POST.get('last_name', '')
            request.user.email = request.POST.get('email', '')
            request.user.save()
            
            # Update student information
            student.name = request.POST.get('name', student.name)
            student.email = request.POST.get('email', student.email)
            student.email_opt_in = bool(request.POST.get('email_opt_in'))
            student.save()
            
            messages.success(request, "Profile updated successfully!")
            return redirect('student_profile')
        
        elif 'change_password' in request.POST:
            old_password = request.POST.get('old_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if not request.user.check_password(old_password):
                messages.error(request, "Old password is incorrect.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            elif len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters.")
            else:
                request.user.set_password(new_password)
                request.user.save()
                messages.success(request, "Password changed successfully! Please login again.")
                logout(request)
                return redirect('student_login')
    
    context = {
        'student': student,
    }
    return render(request, 'attendance/student_profile.html', context)

@login_required
def student_history(request):
    """Student history view showing time-in/time-out records organized by week"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "Student profile not found. Please contact administrator.")
        logout(request)
        return redirect('student_login')
    
    # Get filter parameters
    subject_id = request.GET.get('subject_id', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    attendances_qs = Attendance.objects.filter(student=student).select_related('subject')
    
    # Filter by subject if provided
    if subject_id:
        try:
            attendances_qs = attendances_qs.filter(subject_id=int(subject_id))
        except (ValueError, TypeError):
            pass
    
    # At this point `attendances_qs` contains any persisted Attendance records;
    # we will also compute scheduled sessions within the selected date range and
    # create virtual Attendance objects with status 'ABSENT' for missing sessions
    # so the student history shows absences according to schedules and system settings.
    # Determine effective date range for absence computation
    settings_obj = get_cached_settings()

    try:
        if date_from:
            start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        else:
            start_date = settings_obj.semester_start_date
    except Exception:
        start_date = settings_obj.semester_start_date

    try:
        if date_to:
            end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        else:
            end_date = settings_obj.semester_end_date
    except Exception:
        end_date = settings_obj.semester_end_date

    # Clip range to semester bounds
    if start_date < settings_obj.semester_start_date:
        start_date = settings_obj.semester_start_date
    if end_date > settings_obj.semester_end_date:
        end_date = settings_obj.semester_end_date

    # Determine today's date and cap the generation of virtual absences
    # to sessions that are on or before the configured end-of-day time.
    # Use Manila time for consistency with attendance timestamps.
    manila_now = get_manila_now()
    today_date = manila_now.date()
    if end_date <= today_date:
        effective_end_for_absences = end_date
    else:
        try:
            if manila_now.time() >= settings_obj.class_end_time:
                effective_end_for_absences = today_date
            else:
                effective_end_for_absences = today_date - timedelta(days=1)
        except Exception:
            effective_end_for_absences = today_date - timedelta(days=1)

    # Get persisted attendances in the date range and optional subject filter
    attendances_qs = attendances_qs.filter(date__gte=start_date, date__lte=end_date)
    if subject_id:
        try:
            attendances_qs = attendances_qs.filter(subject_id=int(subject_id))
        except (ValueError, TypeError):
            pass

    # Build set of existing (subject_id, date) for quick lookup
    existing_keys = set(attendances_qs.values_list('subject_id', 'date'))

    # Collect scheduled sessions for each subject the student is enrolled in
    scheduled_sessions = []  # tuples of (subject, session_date)

    student_subjects = StudentSubject.objects.filter(student=student).select_related('subject')
    for ss in student_subjects:
        subject = ss.subject
        # Specific date schedules
        date_schedules = SubjectSchedule.objects.filter(subject=subject, date__isnull=False)
        for ds in date_schedules:
            sess_date = ds.date
            # Only consider scheduled dates within the requested range
            # and not in the future (use effective_end_for_absences)
            if start_date <= sess_date <= effective_end_for_absences:
                # apply optional subject filter
                if subject_id:
                    try:
                        if int(subject_id) != subject.id:
                            continue
                    except Exception:
                        pass
                scheduled_sessions.append((subject, sess_date))

        # Weekly schedules (day_of_week)
        weekly_schedules = SubjectSchedule.objects.filter(subject=subject, date__isnull=True)
        if weekly_schedules.exists():
            # iterate dates in range and add if weekday matches any schedule
            day_map = set([s.day_of_week for s in weekly_schedules if s.day_of_week is not None])
            if day_map:
                current = start_date
                # Only iterate up to effective_end_for_absences to avoid future dates
                while current <= effective_end_for_absences:
                    if current.weekday() in day_map:
                        if subject_id:
                            try:
                                if int(subject_id) != subject.id:
                                    current += timedelta(days=1)
                                    continue
                            except Exception:
                                pass
                        scheduled_sessions.append((subject, current))
                    current += timedelta(days=1)
        else:
            # Fallback to Subject.schedule_time_start existence (non-scheduled subjects)
            if subject.schedule_time_start and subject.schedule_time_end:
                # If there are no weekly schedules, assume daily between semester range? Skip to avoid false absences.
                pass

    # Persist scheduled sessions missing persisted records as ABSENT in the DB
    # (only up to today to avoid marking future sessions)
    try:
        with transaction.atomic():
            for subject, sess_date in scheduled_sessions:
                key = (subject.id, sess_date)
                if sess_date > today_date:
                    continue
                if key not in existing_keys:
                    # Create attendance row for the absent session (don't send emails here)
                    try:
                        Attendance.objects.get_or_create(
                            student=student,
                            subject=subject,
                            date=sess_date,
                            defaults={'time_in': None, 'time_out': None, 'status': 'ABSENT'}
                        )
                    except Exception:
                        # Ignore individual create errors so history page still renders
                        logger.exception(f"Failed to persist absent for student {student.id} subject {subject.id} date {sess_date}")
        # Refresh persisted attendances queryset to include newly created ABSENT rows
        attendances_qs = Attendance.objects.filter(student=student, date__gte=start_date, date__lte=end_date).select_related('subject')
        if subject_id:
            try:
                attendances_qs = attendances_qs.filter(subject_id=int(subject_id))
            except (ValueError, TypeError):
                pass

    except Exception:
        # If the transaction fails for any reason, log and fall back to virtual absents
        logger.exception("Failed to persist virtual absences; falling back to virtual-only display.")
        # Create virtual absent Attendance objects for scheduled sessions missing persisted records
        virtual_absents = []
        for subject, sess_date in scheduled_sessions:
            key = (subject.id, sess_date)
            if sess_date > today_date:
                continue
            if key not in existing_keys:
                a = Attendance(
                    student=student,
                    subject=subject,
                    date=sess_date,
                    time_in=None,
                    time_out=None,
                    status='ABSENT'
                )
                virtual_absents.append(a)

        # Combine persisted attendances and virtual absents into a list for grouping
        attendances_list = list(attendances_qs) + virtual_absents
    else:
        # Use persisted attendances for rendering (no virtual absents necessary)
        attendances_list = list(attendances_qs)

    # Sort attendances_list by date desc, then time_in (None last)
    def _attendance_sort_key(a):
        time_in = a.time_in if getattr(a, 'time_in', None) is not None else (datetime.min.time())
        return (a.date, time_in)

    attendances_list.sort(key=_attendance_sort_key, reverse=True)

    # Group attendances by week
    from collections import OrderedDict

    weeks_dict = OrderedDict()

    for attendance in attendances_list:
        # Get ISO week number (year, week number, weekday)
        iso_calendar = attendance.date.isocalendar()
        week_key = (iso_calendar[0], iso_calendar[1])  # (year, week_number)
        
        # Calculate week start (Monday) and end (Sunday) dates
        days_since_monday = attendance.date.weekday()  # 0 = Monday, 6 = Sunday
        week_start = attendance.date - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)
        
        # Format week label
        week_label = f"Week {iso_calendar[1]}, {iso_calendar[0]}"
        week_range = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        
        if week_key not in weeks_dict:
            weeks_dict[week_key] = {
                'label': week_label,
                'range': week_range,
                'year': iso_calendar[0],
                'week_number': iso_calendar[1],
                'start_date': week_start,
                'end_date': week_end,
                'attendances': []
            }
        
        # Format time-in and time-out
        time_in_str = None
        if attendance.time_in:
            time_in_str = attendance.time_in.strftime('%I:%M %p')
        elif attendance.time:
            time_in_str = attendance.time.strftime('%I:%M %p')
        
        time_out_str = None
        if attendance.time_out:
            time_out_str = attendance.time_out.strftime('%I:%M %p')
        
        weeks_dict[week_key]['attendances'].append({
            'attendance': attendance,
            'time_in_formatted': time_in_str,
            'time_out_formatted': time_out_str,
        })
    
    # Convert to list for template (most recent weeks first)
    weeks_list = list(weeks_dict.values())
    
    # Get subjects for filter dropdown
    student_subjects = StudentSubject.objects.filter(
        student=student
    ).select_related('subject').order_by('subject__code')
    
    # Convert subject_id to int for template comparison
    selected_subject_id_int = None
    if subject_id:
        try:
            selected_subject_id_int = int(subject_id)
        except (ValueError, TypeError):
            pass
    
    context = {
        'student': student,
        'weeks': weeks_list,
        'subjects': [ss.subject for ss in student_subjects],
        'selected_subject_id': subject_id,
        'selected_subject_id_int': selected_subject_id_int,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'attendance/student_history.html', context)

def _send_enrollment_approval_email(enrollment_request, approver_user, notes='', silent=False):
    """
    Helper function to send enrollment approval email notification.
    
    Args:
        enrollment_request: EnrollmentRequest instance
        approver_user: User who approved the request
        notes: Optional notes from approver
        silent: If True, don't print to terminal (default: False)
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        settings = SystemSettings.get_settings()
        if not settings.email_notifications_enabled:
            return False
        
        # Determine who approved (adviser or admin)
        approver_name = "Administrator"
        if hasattr(approver_user, 'adviser_profile'):
            approver_name = approver_user.adviser_profile.name
        elif approver_user.get_full_name():
            approver_name = approver_user.get_full_name()
        elif approver_user.username:
            approver_name = approver_user.username
        
        # Determine if it's an adviser or admin
        is_adviser = hasattr(approver_user, 'adviser_profile')
        approver_type = "adviser" if is_adviser else "administrator"
        
        # Create email subject and message
        email_subject = f"Enrollment Approved: {enrollment_request.subject.code} - {enrollment_request.subject.name}"
        email_message = f"""Dear {enrollment_request.student.name},

The {approver_type} approved your subject enrollment.

Subject Details:
- Subject Code: {enrollment_request.subject.code}
- Subject Name: {enrollment_request.subject.name}
- Academic Year: {enrollment_request.academic_year}
- Semester: {enrollment_request.semester}
- Approved by: {approver_name}
"""
        if notes:
            email_message += f"\nNotes: {notes}\n"
        
        email_message += f"""
You are now enrolled in this subject. Please check your student dashboard for more details.

Best regards,
Attendance Management System
"""
        
        # Send email
        send_attendance_email(
            student=enrollment_request.student,
            email_to=enrollment_request.student.email,
            subject=email_subject,
            message_body=email_message,
            email_type='CUSTOM',
            silent=silent  # Control terminal output
        )
        return True
    except Exception as e:
        # Log error but don't fail the approval process
        logger.error(f"Failed to send enrollment approval email: {str(e)}")
        return False

# Adviser Enrollment Confirmation
@login_required
def adviser_enrollment_requests(request):
    """Adviser view to see and approve/reject enrollment requests"""
    # Get filter parameters
    academic_year = request.GET.get('academic_year', '')
    semester = request.GET.get('semester', '')
    student_search = request.GET.get('student_search', '').strip()
    instructor_filter = request.GET.get('instructor_filter', '').strip()
    
    # Start with all pending enrollment requests
    # If user is staff/superuser, show all. Otherwise, show requests for their assigned students
    if request.user.is_staff or request.user.is_superuser:
        # Staff/superuser can see all pending requests
        enrollment_requests = EnrollmentRequest.objects.filter(
            status='PENDING'
        ).select_related('student', 'subject').order_by('-requested_at')
    else:
        # Regular users (advisers): show enrollment requests only for subjects where instructor belongs to this adviser
        if hasattr(request.user, 'adviser_profile'):
            adviser = request.user.adviser_profile
            # Show requests where subject's instructor belongs to this adviser
            enrollment_requests = EnrollmentRequest.objects.filter(
                status='PENDING',
                subject__instructor__adviser=adviser
            ).select_related('student', 'subject', 'subject__instructor', 'subject__instructor__adviser').order_by('-requested_at')
        else:
            enrollment_requests = EnrollmentRequest.objects.none()
    
    # Apply additional filters
    if academic_year:
        enrollment_requests = enrollment_requests.filter(academic_year=academic_year)
    if semester:
        enrollment_requests = enrollment_requests.filter(semester=semester)
    if student_search:
        enrollment_requests = enrollment_requests.filter(
            Q(student__name__icontains=student_search) |
            Q(student__student_id__icontains=student_search) |
            Q(subject__code__icontains=student_search) |
            Q(subject__name__icontains=student_search)
        )
    if instructor_filter:
        try:
            instructor_id = int(instructor_filter)
            enrollment_requests = enrollment_requests.filter(subject__instructor_id=instructor_id)
        except (ValueError, TypeError):
            enrollment_requests = enrollment_requests.filter(subject__instructor__name__icontains=instructor_filter)
    
    # Handle approve/reject actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        # Handle bulk approval
        if action == 'bulk_approve':
            selected_ids = request.POST.getlist('selected_requests')
            bulk_notes = request.POST.get('bulk_notes', '').strip()
            
            if not selected_ids:
                messages.warning(request, "Please select at least one enrollment request to approve.")
                return redirect('adviser_enrollment_requests')
            
            # Get accessible enrollment requests based on user role
            if request.user.is_staff or request.user.is_superuser:
                accessible_requests = EnrollmentRequest.objects.filter(
                    id__in=selected_ids,
                    status='PENDING'
                )
            else:
                if hasattr(request.user, 'adviser_profile'):
                    adviser = request.user.adviser_profile
                    accessible_requests = EnrollmentRequest.objects.filter(
                        id__in=selected_ids,
                        status='PENDING',
                        subject__instructor__adviser=adviser
                    ).select_related('student', 'subject', 'subject__instructor', 'subject__instructor__adviser')
                else:
                    accessible_requests = EnrollmentRequest.objects.none()
            
            approved_count = 0
            failed_count = 0
            email_sent_count = 0
            email_failed_count = 0
            total_requests = accessible_requests.count()
            
            # Print bulk approval header
            print(f"\n{'='*70}")
            print(f"BULK ENROLLMENT APPROVAL - Processing {total_requests} request(s)")
            print(f"{'='*70}\n")
            
            for idx, enrollment_request in enumerate(accessible_requests, 1):
                try:
                    print(f"[{idx}/{total_requests}] Processing: {enrollment_request.student.name} - {enrollment_request.subject.code}")
                    
                    # Validate instructor relationship for non-staff users
                    # Request should be accessible if subject's instructor belongs to this adviser
                    if not (request.user.is_staff or request.user.is_superuser):
                        if hasattr(request.user, 'adviser_profile'):
                            adviser = request.user.adviser_profile
                            subject = enrollment_request.subject
                            # Check if subject's instructor belongs to this adviser
                            if not subject.instructor or subject.instructor.adviser != adviser:
                                print(f"  ✗ Error: Subject instructor does not belong to adviser {adviser.name}")
                                failed_count += 1
                                continue
                    
                    # Create the actual enrollment
                    StudentSubject.objects.get_or_create(
                        student=enrollment_request.student,
                        subject=enrollment_request.subject,
                        academic_year=enrollment_request.academic_year,
                        semester=enrollment_request.semester,
                    )
                    
                    # Update request status
                    enrollment_request.status = 'APPROVED'
                    enrollment_request.reviewed_at = timezone.now()
                    enrollment_request.reviewed_by = request.user
                    enrollment_request.notes = bulk_notes
                    enrollment_request.save()
                    
                    print(f"  ✓ Enrollment created successfully")
                    
                    # Send email notification to student (show progress in terminal)
                    print(f"  → Sending email notification to {enrollment_request.student.email}...")
                    email_sent = _send_enrollment_approval_email(
                        enrollment_request, 
                        request.user, 
                        bulk_notes, 
                        silent=False  # Show email sending process
                    )
                    
                    if email_sent:
                        email_sent_count += 1
                        print(f"  ✓ Email sent successfully\n")
                    else:
                        email_failed_count += 1
                        print(f"  ⚠ Email notification disabled or failed\n")
                    
                    approved_count += 1
                except Exception as e:
                    logger.error(f"Failed to approve enrollment request {enrollment_request.id}: {str(e)}")
                    print(f"  ✗ Error: {str(e)}\n")
                    failed_count += 1
            
            # Print summary
            print(f"{'='*70}")
            print(f"BULK APPROVAL SUMMARY")
            print(f"{'='*70}")
            print(f"Total Processed: {total_requests}")
            print(f"Approved: {approved_count}")
            print(f"Failed: {failed_count}")
            print(f"Emails Sent: {email_sent_count}")
            print(f"Emails Failed: {email_failed_count}")
            print(f"{'='*70}\n")
            
            if approved_count > 0:
                messages.success(request, f"Successfully approved {approved_count} enrollment request(s).")
            if failed_count > 0:
                messages.warning(request, f"Failed to approve {failed_count} enrollment request(s).")
            
            return redirect('adviser_enrollment_requests')
        
        # Handle single approve/reject
        request_id = request.POST.get('request_id')
        notes = request.POST.get('notes', '').strip()
        
        try:
            # For POST, allow staff/superuser to approve any, or match by adviser for regular users
            if request.user.is_staff or request.user.is_superuser:
                enrollment_request = EnrollmentRequest.objects.get(
                    id=request_id,
                    status='PENDING'
                )
            else:
                # For regular users (advisers), filter by subject's instructor's adviser
                if hasattr(request.user, 'adviser_profile'):
                    adviser = request.user.adviser_profile
                    enrollment_request = EnrollmentRequest.objects.filter(
                        id=request_id,
                        status='PENDING',
                        subject__instructor__adviser=adviser
                    ).select_related('student', 'subject', 'subject__instructor', 'subject__instructor__adviser').first()
                else:
                    enrollment_request = None
                
                if not enrollment_request:
                    raise EnrollmentRequest.DoesNotExist("Enrollment request not found or access denied.")
            
            if action == 'approve':
                
                # Create the actual enrollment
                # Create the actual enrollment
                StudentSubject.objects.get_or_create(
                    student=enrollment_request.student,
                    subject=enrollment_request.subject,
                    academic_year=enrollment_request.academic_year,
                    semester=enrollment_request.semester,
                )
                
                # Update request status
                enrollment_request.status = 'APPROVED'
                enrollment_request.reviewed_at = timezone.now()
                enrollment_request.reviewed_by = request.user
                enrollment_request.notes = notes
                enrollment_request.save()
                
                # Send email notification to student (silent for single approvals)
                _send_enrollment_approval_email(enrollment_request, request.user, notes, silent=True)
                
                messages.success(request, f"Approved enrollment: {enrollment_request.student.name} - {enrollment_request.subject.code}")
            
            elif action == 'reject':
                # Update request status
                enrollment_request.status = 'REJECTED'
                enrollment_request.reviewed_at = timezone.now()
                enrollment_request.reviewed_by = request.user
                enrollment_request.notes = notes
                enrollment_request.save()
                
                messages.success(request, f"Rejected enrollment: {enrollment_request.student.name} - {enrollment_request.subject.code}")
            
            return redirect('adviser_enrollment_requests')
        
        except EnrollmentRequest.DoesNotExist:
            messages.error(request, "Enrollment request not found or already processed.")
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
    
    # Get unique academic years and semesters for filters
    academic_years = EnrollmentRequest.objects.values_list('academic_year', flat=True).distinct().order_by('-academic_year')
    semesters = EnrollmentRequest.objects.values_list('semester', flat=True).distinct().order_by('semester')
    
    # Get instructors for filter dropdown
    if request.user.is_staff or request.user.is_superuser:
        # Staff/superuser can see all instructors
        all_instructors = Instructor.objects.filter(is_active=True).order_by('name')
    else:
        # Regular users: show only instructors belonging to their adviser
        if hasattr(request.user, 'adviser_profile'):
            all_instructors = Instructor.objects.filter(
                is_active=True,
                adviser=request.user.adviser_profile
            ).order_by('name')
        else:
            all_instructors = Instructor.objects.none()
    
    # Get statistics - show all if staff, otherwise filtered by subject's instructor's adviser
    if request.user.is_staff or request.user.is_superuser:
        stats_base = EnrollmentRequest.objects.all()
    else:
        if hasattr(request.user, 'adviser_profile'):
            adviser = request.user.adviser_profile
            stats_base = EnrollmentRequest.objects.filter(
                subject__instructor__adviser=adviser
            )
        else:
            stats_base = EnrollmentRequest.objects.none()
    
    total_pending = enrollment_requests.count()
    approved_count = stats_base.filter(status='APPROVED').count()
    rejected_count = stats_base.filter(status='REJECTED').count()
    
    # Get total pending count (all requests, not filtered)
    total_all_pending = EnrollmentRequest.objects.filter(status='PENDING').count()
    
    adviser_name = request.user.adviser_profile.name if hasattr(request.user, 'adviser_profile') else (request.user.get_full_name() or request.user.username)
    context = {
        'enrollment_requests': enrollment_requests,
        'adviser_name': adviser_name,
        'academic_year': academic_year,
        'semester': semester,
        'student_search': student_search,
        'instructor_filter': instructor_filter,
        'academic_years': academic_years,
        'semesters': semesters,
        'all_instructors': all_instructors,
        'total_pending': total_pending,
        'total_all_pending': total_all_pending,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'is_staff': request.user.is_staff or request.user.is_superuser,
    }
    return render(request, 'attendance/adviser_enrollment_requests.html', context)

@login_required
def adviser_features_view(request):
    """Adviser features dashboard showing all available features and statistics"""
    
    # Get students assigned to this adviser
    if request.user.is_staff or request.user.is_superuser:
        # Staff/superuser can see all students
        assigned_students = Student.objects.all()
        enrollment_requests_base = EnrollmentRequest.objects.all()
        attendance_base = Attendance.objects.all()
        adviser_name = "All Advisers"
    else:
        # Regular users: match by adviser profile
        if hasattr(request.user, 'adviser_profile'):
            adviser = request.user.adviser_profile
            assigned_students = Student.objects.filter(adviser=adviser)
            enrollment_requests_base = EnrollmentRequest.objects.filter(
                subject__instructor__adviser=adviser
            )
            adviser_name = adviser.name
        else:
            assigned_students = Student.objects.none()
            enrollment_requests_base = EnrollmentRequest.objects.none()
            adviser_name = request.user.get_full_name() or request.user.username
        attendance_base = Attendance.objects.filter(
            student__in=assigned_students
        )
    
    # Statistics
    total_students = assigned_students.count()
    pending_enrollments = enrollment_requests_base.filter(status='PENDING').count()
    approved_enrollments = enrollment_requests_base.filter(status='APPROVED').count()
    rejected_enrollments = enrollment_requests_base.filter(status='REJECTED').count()
    
    # Today's attendance statistics
    today = timezone.now().date()
    today_attendance = attendance_base.filter(date=today)
    present_today = today_attendance.filter(status='PRESENT').count()
    absent_today = today_attendance.filter(status='ABSENT').count()
    late_today = today_attendance.filter(status='LATE').count()
    
    # Recent enrollment requests (last 5)
    recent_requests = enrollment_requests_base.filter(status='PENDING').select_related('student', 'subject').order_by('-requested_at')[:5]
    
    # Recent attendance (last 10)
    recent_attendance = attendance_base.select_related('student', 'subject').order_by('-date', '-time_in', '-time')[:10]
    
    # For advisers: Only show subjects registered by instructors belonging to them
    # For staff/superuser: Show all subjects
    if request.user.is_staff or request.user.is_superuser:
        # Staff/superuser can see all subjects
        adviser_subjects = Subject.objects.all()
        # Get subjects where assigned students are enrolled
        student_subjects = StudentSubject.objects.filter(
            student__in=assigned_students
        ).select_related('subject', 'student').distinct()
        enrolled_students_count = StudentSubject.objects.values('student').distinct().count()
    else:
        # Regular users: match by adviser profile
        if hasattr(request.user, 'adviser_profile'):
            adviser = request.user.adviser_profile
            # Only show subjects where instructor__adviser matches this adviser
            adviser_subjects = Subject.objects.filter(
                instructor__adviser=adviser
            ).distinct()
            # Get subjects where assigned students are enrolled AND subject is registered by adviser's instructor
            student_subjects = StudentSubject.objects.filter(
                student__in=assigned_students,
                subject__in=adviser_subjects
            ).select_related('subject', 'student').distinct()
            # Count distinct students enrolled in subjects registered by adviser's instructors
            enrolled_students_count = StudentSubject.objects.filter(
                subject__instructor__adviser=adviser
            ).values('student').distinct().count()
        else:
            adviser_subjects = Subject.objects.none()
            student_subjects = StudentSubject.objects.none()
            enrolled_students_count = 0
    
    # Subject-wise statistics - only for subjects registered by adviser's instructors
    subject_stats = {}
    for subject in adviser_subjects:
        # Get enrollments for this subject
        subject_enrollments = StudentSubject.objects.filter(subject=subject)
        enrolled_count = subject_enrollments.count()
        
        # Get today's attendance for this subject
        subject_attendance_today = today_attendance.filter(subject=subject)
        present_today_count = subject_attendance_today.filter(status='PRESENT').count()
        absent_today_count = subject_attendance_today.filter(status='ABSENT').count()
        late_today_count = subject_attendance_today.filter(status='LATE').count()
        
        subject_stats[subject.code] = {
            'subject': subject,
            'enrolled_count': enrolled_count,
            'present_today': present_today_count,
            'absent_today': absent_today_count,
            'late_today': late_today_count,
        }
    
    context = {
        'adviser_name': adviser_name,
        'total_students': total_students,
        'enrolled_students_count': enrolled_students_count,
        'pending_enrollments': pending_enrollments,
        'approved_enrollments': approved_enrollments,
        'rejected_enrollments': rejected_enrollments,
        'present_today': present_today,
        'absent_today': absent_today,
        'late_today': late_today,
        'recent_requests': recent_requests,
        'recent_attendance': recent_attendance,
        'subject_stats': list(subject_stats.values()),
        'is_staff': request.user.is_staff or request.user.is_superuser,
    }
    return render(request, 'attendance/adviser_features.html', context)

@login_required
def adviser_subjects_monitor(request):
    """Monitor all subjects registered by adviser's instructors with enrolled students"""
    
    # Get adviser information
    if request.user.is_staff or request.user.is_superuser:
        adviser_name = "All Advisers"
        # Staff/superuser can see all subjects
        subjects = Subject.objects.all().select_related('instructor', 'instructor__adviser', 'course').prefetch_related(
            'schedules', 'students__student'
        ).annotate(
            enrolled_count=Count('students', distinct=True)
        ).order_by('code')
    else:
        if hasattr(request.user, 'adviser_profile'):
            adviser = request.user.adviser_profile
            adviser_name = adviser.name
            # Only show subjects where instructor__adviser matches this adviser
            subjects = Subject.objects.filter(
                instructor__adviser=adviser
            ).select_related('instructor', 'instructor__adviser', 'course').prefetch_related(
                'schedules', 'students__student'
            ).annotate(
                enrolled_count=Count('students', distinct=True)
            ).order_by('code')
        else:
            adviser_name = request.user.get_full_name() or request.user.username
            subjects = Subject.objects.none()
    
    # Search and filter functionality
    search_query = request.GET.get('search', '').strip()
    instructor_filter = request.GET.get('instructor', '').strip()
    
    if search_query:
        subjects = subjects.filter(
            Q(code__icontains=search_query) |
            Q(name__icontains=search_query)
        )
    
    if instructor_filter:
        subjects = subjects.filter(
            Q(instructor__name__icontains=instructor_filter) |
            Q(instructor__email__icontains=instructor_filter)
        )
    
    # Get unique instructors for filter dropdown
    if request.user.is_staff or request.user.is_superuser:
        instructors = Instructor.objects.filter(is_active=True).order_by('name')
    else:
        if hasattr(request.user, 'adviser_profile'):
            instructors = Instructor.objects.filter(
                is_active=True,
                adviser=request.user.adviser_profile
            ).order_by('name')
        else:
            instructors = Instructor.objects.none()
    
    # Get today's date for attendance stats
    today = timezone.now().date()
    
    # Add attendance statistics for each subject
    subjects_with_stats = []
    for subject in subjects:
        # Get enrolled students
        enrolled_students = StudentSubject.objects.filter(subject=subject).select_related('student')
        
        # Get today's attendance for this subject
        today_attendance = Attendance.objects.filter(
            subject=subject,
            date=today
        )
        
        present_today = today_attendance.filter(status='PRESENT').count()
        absent_today = today_attendance.filter(status='ABSENT').count()
        late_today = today_attendance.filter(status='LATE').count()
        
        subjects_with_stats.append({
            'subject': subject,
            'enrolled_students': enrolled_students,
            'enrolled_count': subject.enrolled_count,
            'present_today': present_today,
            'absent_today': absent_today,
            'late_today': late_today,
        })
    
    context = {
        'adviser_name': adviser_name,
        'subjects_with_stats': subjects_with_stats,
        'search_query': search_query,
        'instructor_filter': instructor_filter,
        'instructors': instructors,
        'today': today,
        'is_staff': request.user.is_staff or request.user.is_superuser,
    }
    return render(request, 'attendance/adviser_subjects_monitor.html', context)

@login_required
def section_list(request):
    """List all sections"""
    sections = Section.objects.all().order_by('code')
    search_query = request.GET.get('search', '').strip()
    
    if search_query:
        sections = sections.filter(
            Q(code__icontains=search_query) |
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    context = {
        'sections': sections,
        'search_query': search_query,
    }
    return render(request, 'attendance/section_list.html', context)

@login_required
def section_add(request):
    """Add a new section"""
    if request.method == 'POST':
        try:
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not code:
                messages.error(request, "Section code is required.")
                return redirect('section_add')
            
            if not name:
                name = f"Section {code}"
            
            # Check if section code already exists
            if Section.objects.filter(code=code).exists():
                messages.error(request, f"Section with code '{code}' already exists.")
                return redirect('section_add')
            
            section = Section.objects.create(
                code=code,
                name=name,
                description=description,
                is_active=is_active
            )
            messages.success(request, f"Section '{section.name}' added successfully!")
            return redirect('section_list')
        except Exception as e:
            messages.error(request, f"Error adding section: {str(e)}")
    
    return render(request, 'attendance/section_form.html', {'action': 'Add'})

@login_required
def section_edit(request, section_id):
    """Edit an existing section"""
    section = get_object_or_404(Section, id=section_id)
    
    if request.method == 'POST':
        try:
            code = request.POST.get('code', '').strip().upper()
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not code:
                messages.error(request, "Section code is required.")
                return redirect('section_edit', section_id=section_id)
            
            if not name:
                name = f"Section {code}"
            
            # Check if section code already exists (excluding current section)
            if Section.objects.filter(code=code).exclude(id=section_id).exists():
                messages.error(request, f"Section with code '{code}' already exists.")
                return redirect('section_edit', section_id=section_id)
            
            section.code = code
            section.name = name
            section.description = description
            section.is_active = is_active
            section.save()
            
            messages.success(request, f"Section '{section.name}' updated successfully!")
            return redirect('section_list')
        except Exception as e:
            messages.error(request, f"Error updating section: {str(e)}")
    
    return render(request, 'attendance/section_form.html', {
        'section': section,
        'action': 'Edit'
    })

@login_required
def section_delete(request, section_id):
    """Delete a section"""
    if request.method == 'POST':
        section = get_object_or_404(Section, id=section_id)
        
        # Check if section has students
        student_count = section.students.count()
        if student_count > 0:
            messages.error(request, f"Cannot delete section '{section.name}' because it has {student_count} student(s) assigned. Please reassign students to another section first.")
            return redirect('section_list')
        
        try:
            section_name = section.name
            section.delete()
            messages.success(request, f"Section '{section_name}' deleted successfully!")
        except Exception as e:
            messages.error(request, f"Error deleting section: {str(e)}")
    
    return redirect('section_list')

# API Endpoints for Form Dropdowns
@login_required
def api_courses(request):
    """API endpoint to get courses for dropdowns"""
    try:
        # Match the logic from student_add and student_list views
        # Advisers have full access to all courses (same as student_add view)
        if request.user.is_superuser or request.user.is_staff:
            courses = Course.objects.filter(is_active=True).order_by('code')
        elif hasattr(request.user, 'adviser_profile'):
            # Advisers have full access to all courses and all advisers
            courses = Course.objects.filter(is_active=True).order_by('code')
        else:
            # For other users, use restrictive filtering
            accessible_courses = get_user_accessible_courses(request.user)
            courses = accessible_courses.order_by('code')
        
        courses_data = []
        for course in courses:
            courses_data.append({
                'id': course.id,
                'code': course.code,
                'name': course.name,
                'display': f"{course.code} - {course.name}"
            })
        
        username = getattr(request.user, 'username', 'unknown')
        logger.info(f"api_courses: Returning {len(courses_data)} courses for user {username}")
        return JsonResponse({'success': True, 'courses': courses_data})
    except Exception as e:
        username = getattr(request.user, 'username', 'unknown')
        logger.error(f"Error in api_courses for user {username}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def api_student_subjects(request, student_id):
    """Return JSON list of subjects the student is enrolled in, with a flag if the subject has a schedule today."""
    try:
        student = get_object_or_404(Student, id=student_id)

        # Security: ensure requester can view this student's info
        accessible_courses = get_user_accessible_courses(request.user)
        if not (request.user.is_superuser or request.user.is_staff) and not hasattr(request.user, 'adviser_profile'):
            if student.course not in accessible_courses:
                return JsonResponse({'success': False, 'error': "Permission denied."}, status=403)

        today = get_manila_now().date()
        day_of_week = today.weekday()

        subjects = StudentSubject.objects.filter(student=student).select_related('subject')
        data = []
        for ss in subjects:
            subject = ss.subject
            # Check if subject has a schedule for today (specific date or weekly)
            has_schedule = SubjectSchedule.objects.filter(
                subject=subject,
            ).filter(
                Q(date=today) | Q(date__isnull=True, day_of_week=day_of_week)
            ).exists()

            data.append({
                'id': subject.id,
                'code': subject.code,
                'name': subject.name,
                'display': f"{subject.code} - {subject.name}",
                'has_schedule_today': has_schedule,
            })

        return JsonResponse({'success': True, 'subjects': data})
    except Exception as e:
        logger.error(f"Error in api_student_subjects: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def api_sections(request):
    """API endpoint to get sections for dropdowns"""
    try:
        sections = Section.objects.filter(is_active=True).order_by('code')
        
        sections_data = [{
            'id': section.id,
            'code': section.code,
            'name': section.name,
            'display': f"{section.name} ({section.code})"
        } for section in sections]
        
        username = getattr(request.user, 'username', 'unknown')
        logger.info(f"api_sections: Returning {len(sections_data)} sections for user {username}")
        return JsonResponse({'success': True, 'sections': sections_data})
    except Exception as e:
        username = getattr(request.user, 'username', 'unknown')
        logger.error(f"Error in api_sections for user {username}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def api_advisers(request):
    """API endpoint to get advisers for dropdowns"""
    try:
        # For adding students, show all advisers to all logged-in users
        # The permission check happens when actually saving the student
        advisers = Adviser.objects.all().order_by('name')
        
        advisers_data = []
        for adviser in advisers:
            advisers_data.append({
                'id': adviser.id,
                'name': adviser.name,
                'email': adviser.email,
                'display': f"{adviser.name} ({adviser.email})"
            })
        
        username = getattr(request.user, 'username', 'unknown')
        logger.info(f"api_advisers: Returning {len(advisers_data)} advisers for user {username}")
        return JsonResponse({'success': True, 'advisers': advisers_data})
    except Exception as e:
        username = getattr(request.user, 'username', 'unknown')
        logger.error(f"Error in api_advisers for user {username}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def api_instructors(request):
    """API endpoint to get instructors for dropdowns"""
    try:
        instructors = filter_instructors_by_user(request.user)
        instructors = instructors.filter(is_active=True).order_by('name')
        
        instructors_data = [{
            'id': instructor.id,
            'name': instructor.name,
            'email': instructor.email if hasattr(instructor, 'email') else '',
            'display': instructor.name
        } for instructor in instructors]
        
        return JsonResponse({'success': True, 'instructors': instructors_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
