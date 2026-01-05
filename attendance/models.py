from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import os

class SystemSettings(models.Model):
    """System-wide settings"""
    semester_start_date = models.DateField(default=timezone.now)
    semester_end_date = models.DateField(default=timezone.now)
    class_start_time = models.TimeField(default='08:00:00')
    class_end_time = models.TimeField(default='17:00:00')
    grace_period_minutes = models.IntegerField(default=15, validators=[MinValueValidator(0)])
    late_threshold_minutes = models.IntegerField(default=30, validators=[MinValueValidator(0)])
    absent_threshold_percent = models.IntegerField(default=50, validators=[MinValueValidator(0), MaxValueValidator(100)])
    # Time validation settings
    enable_time_validation = models.BooleanField(default=True, help_text="Enable strict date/time validation for attendance")
    early_attendance_minutes = models.IntegerField(default=30, validators=[MinValueValidator(0)], help_text="Allow attendance this many minutes before class starts")
    late_attendance_minutes = models.IntegerField(default=60, validators=[MinValueValidator(0)], help_text="Allow attendance this many minutes after class ends")
    email_notifications_enabled = models.BooleanField(default=True)
    auto_send_reports = models.BooleanField(default=True)
    send_warnings_after = models.IntegerField(default=3, validators=[MinValueValidator(1)])
    auto_backup_enabled = models.BooleanField(default=True)
    data_retention_years = models.IntegerField(default=5, validators=[MinValueValidator(1)])
    last_sync = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "System Settings"
    
    def save(self, *args, **kwargs):
        # Ensure only one settings instance exists
        self.pk = 1
        super().save(*args, **kwargs)
        # Invalidate cache after saving (lazy import to avoid circular dependencies)
        try:
            from django.core.cache import cache
            cache.delete('system_settings')
        except ImportError:
            pass
    
    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

class Course(models.Model):
    """Course model for organizing students and subjects by academic program"""
    code = models.CharField(max_length=50, unique=True, help_text="Course code (e.g., BSIT, BSCS)")
    name = models.CharField(max_length=200, help_text="Full course name (e.g., Bachelor of Science in Information Technology)")
    description = models.TextField(blank=True, default='', help_text="Optional course description")
    is_active = models.BooleanField(default=True, help_text="Whether this course is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    class Meta:
        ordering = ['code']
        verbose_name_plural = "Courses"
        indexes = [
            models.Index(fields=['code', 'is_active']),
        ]

class Adviser(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, default='')
    courses = models.ManyToManyField('Course', related_name='advisers', blank=True, help_text="Courses this adviser manages")
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='adviser_profile')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.email})"
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = "Advisers"

class Instructor(models.Model):
    """Instructor model - instructors are designated to advisers"""
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True, null=True, blank=True)
    employee_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    adviser = models.ForeignKey('Adviser', on_delete=models.CASCADE, related_name='instructors', help_text="Adviser this instructor is designated to")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (Assigned to: {self.adviser.name})"
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = "Instructors"
        indexes = [
            models.Index(fields=['adviser', 'is_active']),
        ]

class Section(models.Model):
    """Section model for organizing students into sections (A, B, C, etc.)"""
    code = models.CharField(max_length=20, unique=True, help_text="Section code (e.g., A, B, C)")
    name = models.CharField(max_length=100, help_text="Section name (e.g., Section A)")
    description = models.TextField(blank=True, default='', help_text="Optional section description")
    is_active = models.BooleanField(default=True, help_text="Whether this section is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['code']
        verbose_name_plural = "Sections"
        indexes = [
            models.Index(fields=['code', 'is_active']),
        ]

def student_profile_picture_path(instance, filename):
    """Generate path for student profile pictures"""
    ext = filename.split('.')[-1]
    filename = f"profile_{instance.id}_{instance.rfid_id}.{ext}"
    return os.path.join('student_profiles', filename)

class Student(models.Model):
    rfid_id = models.CharField(max_length=50, unique=True, db_index=True)
    student_id = models.CharField(max_length=50, unique=True, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=100)
    course = models.ForeignKey('Course', on_delete=models.PROTECT, related_name='students', help_text="Student's enrolled course")
    section = models.ForeignKey('Section', on_delete=models.PROTECT, related_name='students', null=True, blank=True, help_text="Student's section (A, B, C, etc.)")
    email = models.EmailField()
    adviser = models.ForeignKey(Adviser, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='student_profile')
    profile_picture = models.ImageField(upload_to=student_profile_picture_path, null=True, blank=True, help_text="Student profile picture")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.rfid_id})"
    
    def get_profile_picture_url(self):
        """Optimized method to get profile picture URL"""
        if self.profile_picture:
            return self.profile_picture.url
        return None
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['rfid_id']),
        ]

class Subject(models.Model):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    instructor = models.ForeignKey('Instructor', on_delete=models.PROTECT, related_name='subjects', null=True, blank=True, help_text="Instructor assigned to this subject")
    adviser = models.ForeignKey(Adviser, on_delete=models.CASCADE, related_name='subjects', null=True, blank=True, help_text="Adviser who created/owns this subject")
    course = models.ForeignKey('Course', on_delete=models.PROTECT, related_name='subjects', null=True, blank=True, help_text="Course this subject belongs to (optional for general subjects)")
    course_code = models.CharField(max_length=50, blank=True, default='', help_text="Course code (e.g., BSIT, BSCS)")
    course_number = models.CharField(max_length=50, blank=True, default='', help_text="Course number (e.g., 101, 201)")
    schedule_days = models.CharField(max_length=50, blank=True, default='', help_text="e.g., Mon,Wed,Fri")
    schedule_time_start = models.TimeField(null=True, blank=True)
    schedule_time_end = models.TimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"
    
    class Meta:
        ordering = ['code']
        # Allow same code for different advisers, but unique per adviser
        unique_together = [['code', 'adviser']]

class SubjectSchedule(models.Model):
    """Weekly schedule entries for a subject (day of week and time)"""
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAY_CHOICES, null=True, blank=True, help_text="Day of the week (0=Monday, 6=Sunday)")
    time_start = models.TimeField()
    time_end = models.TimeField()
    date = models.DateField(null=True, blank=True, help_text="Optional: Specific date override (for backward compatibility)")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        day_name = dict(self.DAY_CHOICES).get(self.day_of_week, 'Unknown')
        if self.date:
            return f"{self.subject.code} - {self.date} ({self.time_start} - {self.time_end})"
        return f"{self.subject.code} - {day_name} ({self.time_start} - {self.time_end})"
    
    def get_day_name(self):
        return dict(self.DAY_CHOICES).get(self.day_of_week, 'Unknown')
    
    class Meta:
        ordering = ['day_of_week', 'time_start']
        unique_together = ['subject', 'day_of_week', 'time_start']

class StudentSubject(models.Model):
    """Many-to-many relationship between students and subjects"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='students')
    academic_year = models.CharField(max_length=20, default='2025-2026')
    semester = models.CharField(max_length=20, default='1st Semester')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['student', 'subject', 'academic_year', 'semester']
        ordering = ['subject__code']

class Attendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    time = models.TimeField(null=True, blank=True, help_text="Legacy field - use time_in instead")
    time_in = models.TimeField(null=True, blank=True, help_text="Time when student checked in")
    time_out = models.TimeField(null=True, blank=True, help_text="Time when student checked out")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PRESENT')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.student.name} - {self.subject.code} - {self.date} - {self.status}"
    
    class Meta:
        # Prevent duplicate attendance records - only one record per student, subject, and date
        # This ensures no redundant time_in or time_out data
        ordering = ['-date', '-time_in']
        indexes = [
            models.Index(fields=['student', 'subject', 'date']),
            models.Index(fields=['date', 'status']),
        ]
        constraints = [
            # Prevent ALL duplicate attendance records for same student, subject, and date
            # This ensures no redundant time_in or time_out data regardless of time_out status
            models.UniqueConstraint(
                fields=['student', 'subject', 'date'],
                name='unique_attendance_per_day'
            ),
        ]

class EmailLog(models.Model):
    STATUS_CHOICES = [
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('PENDING', 'Pending'),
    ]
    
    TYPE_CHOICES = [
        ('SEMESTER', 'Semester Report'),
        ('WARNING', 'Warning'),
        ('DAILY', 'Daily Report'),
        ('CUSTOM', 'Custom'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='email_logs')
    email_to = models.EmailField()
    email_cc = models.EmailField(blank=True)
    email_bcc = models.EmailField(blank=True)
    subject = models.CharField(max_length=200)
    message_body = models.TextField()
    email_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='SEMESTER')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['student', 'email_type']),
        ]
    
    def __str__(self):
        return f"{self.student.name} - {self.email_type} - {self.status}"

class EnrollmentRequest(models.Model):
    """Enrollment requests that need adviser confirmation"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollment_requests')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='enrollment_requests')
    academic_year = models.CharField(max_length=20, default='2025-2026')
    semester = models.CharField(max_length=20, default='1st Semester')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_enrollments')
    notes = models.TextField(blank=True, default='', help_text="Optional notes from adviser")
    
    class Meta:
        ordering = ['-requested_at']
        # Only one pending request per student-subject-academic_year-semester combination
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'subject', 'academic_year', 'semester'],
                condition=models.Q(status='PENDING'),
                name='unique_pending_enrollment'
            )
        ]
        indexes = [
            models.Index(fields=['status', 'requested_at']),
            models.Index(fields=['student', 'status']),
        ]
    
    def __str__(self):
        return f"{self.student.name} - {self.subject.code} - {self.status}"
