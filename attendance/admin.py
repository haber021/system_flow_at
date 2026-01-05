from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib import messages
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Student, Subject, Attendance, SystemSettings, StudentSubject, EmailLog, SubjectSchedule, Adviser, Course, Instructor, Section

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active', 'student_count', 'created_at']
    search_fields = ['code', 'name', 'description']
    list_filter = ['is_active', 'created_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
    )
    
    def student_count(self, obj):
        """Display the number of students in this section"""
        return obj.students.count()
    student_count.short_description = 'Students'

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'is_active', 'student_count', 'adviser_count', 'created_at']
    search_fields = ['code', 'name', 'description']
    list_filter = ['is_active', 'created_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'description', 'is_active')
        }),
    )
    
    def student_count(self, obj):
        """Display the number of students in this course"""
        return obj.students.count()
    student_count.short_description = 'Students'
    
    def adviser_count(self, obj):
        """Display the number of advisers for this course"""
        return obj.advisers.count()
    adviser_count.short_description = 'Advisers'

class AdviserAdminForm(forms.ModelForm):
    """Custom form for Adviser admin with password fields"""
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        required=False,
        help_text='Enter password to create a new user account or update existing account password. Leave blank to keep current password.'
    )
    password2 = forms.CharField(
        label='Password confirmation',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        required=False,
        help_text='Enter the same password as above, for verification.'
    )
    
    class Meta:
        model = Adviser
        fields = '__all__'
        exclude = ['user']
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Only validate passwords if at least one is provided
        if password1 or password2:
            if password1 != password2:
                raise ValidationError("The two password fields didn't match.")
            if len(password1) < 8:
                raise ValidationError("Password must be at least 8 characters long.")
        
        return cleaned_data

@admin.register(Adviser)
class AdviserAdmin(admin.ModelAdmin):
    form = AdviserAdminForm
    list_display = ['name', 'email', 'employee_id', 'department', 'course_count', 'has_user_account']
    search_fields = ['name', 'email', 'employee_id', 'department']
    list_filter = ['department', 'courses']
    filter_horizontal = ['courses']
    actions = ['create_user_accounts', 'set_password']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'email', 'employee_id', 'department', 'courses')
        }),
        ('Login Account', {
            'fields': ('password1', 'password2'),
            'description': 'Set a password to create a user account for this adviser to access the dashboard. If the adviser already has an account, entering a new password will update it. Leave blank to keep the current password or skip account creation.'
        }),
    )
    
    def course_count(self, obj):
        """Display the number of courses assigned to this adviser"""
        return obj.courses.count()
    course_count.short_description = 'Courses'
    
    def has_user_account(self, obj):
        return obj.user is not None
    has_user_account.boolean = True
    has_user_account.short_description = 'Has Login Account'
    
    def create_user_accounts(self, request, queryset):
        """Create user accounts for selected advisers"""
        created = 0
        skipped = 0
        errors = []
        
        for adviser in queryset:
            if adviser.user:
                skipped += 1
                continue
            
            try:
                # Generate username from employee_id or email prefix
                username = adviser.employee_id or adviser.email.split('@')[0]
                if not username:
                    errors.append(f"{adviser.name}: No employee ID or email")
                    continue
                
                # Check if username already exists
                if User.objects.filter(username=username).exists():
                    # Try with email prefix and name
                    username = f"{adviser.email.split('@')[0]}_{adviser.name.split()[0]}".lower()
                    if User.objects.filter(username=username).exists():
                        errors.append(f"{adviser.name}: Username already exists")
                        continue
                
                # Create user with default password (adviser should change it)
                user = User.objects.create_user(
                    username=username,
                    email=adviser.email,
                    password='adviser123',  # Default password - should be changed
                    first_name=adviser.name.split()[0] if adviser.name.split() else '',
                    last_name=' '.join(adviser.name.split()[1:]) if len(adviser.name.split()) > 1 else '',
                )
                
                # Link adviser to user
                adviser.user = user
                adviser.save()
                created += 1
            except Exception as e:
                errors.append(f"{adviser.name}: {str(e)}")
        
        message = f"Created {created} user account(s)."
        if skipped > 0:
            message += f" Skipped {skipped} (already have accounts)."
        if errors:
            message += f" Errors: {len(errors)}"
            for error in errors[:5]:  # Show first 5 errors
                messages.warning(request, error)
        
        messages.success(request, message)
    
    create_user_accounts.short_description = "Create login accounts for selected advisers"
    
    def set_password(self, request, queryset):
        """Reset password to default for selected advisers"""
        updated = 0
        skipped = 0
        errors = []
        default_password = 'adviser123'
        
        for adviser in queryset:
            if not adviser.user:
                skipped += 1
                errors.append(f"{adviser.name}: No user account. Create account first.")
                continue
            
            try:
                adviser.user.set_password(default_password)
                adviser.user.save()
                updated += 1
            except Exception as e:
                errors.append(f"{adviser.name}: {str(e)}")
        
        message = f"Reset password to default ('{default_password}') for {updated} adviser(s)."
        if skipped > 0:
            message += f" Skipped {skipped} (no user account)."
        if errors:
            for error in errors[:5]:
                messages.warning(request, error)
        
        messages.success(request, message)
        messages.info(request, "Note: To set a custom password, edit the User account directly in the Users admin section.")
    
    set_password.short_description = "Reset password to default for selected advisers"
    
    def save_model(self, request, obj, form, change):
        """Save the adviser and create user account if password is provided"""
        # Handle password and user account creation before saving
        password = form.cleaned_data.get('password1')
        
        # Save the adviser first
        super().save_model(request, obj, form, change)
        
        if password:
            try:
                if obj.user:
                    # Update existing user password
                    obj.user.set_password(password)
                    obj.user.save()
                    messages.success(request, f"Password updated for {obj.name}'s user account.")
                else:
                    # Generate username from employee_id or email prefix
                    username = obj.employee_id or obj.email.split('@')[0]
                    if not username:
                        messages.warning(request, f"Could not create user account for {obj.name}: No employee ID or email prefix available.")
                        return
                    
                    # Check if username already exists (excluding current user if any)
                    existing_user = User.objects.filter(username=username).first()
                    if existing_user and existing_user != obj.user:
                        # Try with email prefix and name
                        username = f"{obj.email.split('@')[0]}_{obj.name.split()[0]}".lower()
                        existing_user = User.objects.filter(username=username).first()
                        if existing_user and existing_user != obj.user:
                            messages.warning(request, f"Could not create user account for {obj.name}: Username already exists. Please create the account manually.")
                            return
                    
                    # Create new user account
                    user = User.objects.create_user(
                        username=username,
                        email=obj.email,
                        password=password,
                        first_name=obj.name.split()[0] if obj.name.split() else '',
                        last_name=' '.join(obj.name.split()[1:]) if len(obj.name.split()) > 1 else '',
                    )
                    obj.user = user
                    obj.save()
                    messages.success(request, f"User account created for {obj.name} with username: {username}")
            except Exception as e:
                messages.error(request, f"Error creating/updating user account for {obj.name}: {str(e)}")

@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'employee_id', 'adviser', 'is_active', 'subject_count', 'created_at']
    search_fields = ['name', 'email', 'employee_id', 'adviser__name']
    list_filter = ['is_active', 'adviser', 'created_at']
    autocomplete_fields = ['adviser']
    
    def subject_count(self, obj):
        """Display the number of subjects assigned to this instructor"""
        return obj.subjects.count()
    subject_count.short_description = 'Subjects'

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['rfid_id', 'student_id', 'name', 'course', 'section', 'email', 'adviser', 'has_user_account']
    search_fields = ['rfid_id', 'student_id', 'name', 'course__code', 'course__name', 'section__code', 'section__name', 'email', 'adviser__name', 'adviser__email']
    list_filter = ['course', 'section', 'adviser']
    autocomplete_fields = ['adviser', 'course', 'section']
    exclude = ['user']
    actions = ['create_user_accounts']
    
    def has_user_account(self, obj):
        return obj.user is not None
    has_user_account.boolean = True
    has_user_account.short_description = 'Has Login Account'
    
    def create_user_accounts(self, request, queryset):
        """Create user accounts for selected students"""
        created = 0
        skipped = 0
        errors = []
        
        for student in queryset:
            if student.user:
                skipped += 1
                continue
            
            try:
                # Generate username from student_id or rfid_id
                username = student.student_id or student.rfid_id
                if not username:
                    errors.append(f"{student.name}: No student ID or RFID ID")
                    continue
                
                # Check if username already exists
                if User.objects.filter(username=username).exists():
                    # Try with email prefix
                    username = student.email.split('@')[0]
                    if User.objects.filter(username=username).exists():
                        errors.append(f"{student.name}: Username already exists")
                        continue
                
                # Create user with default password (student should change it)
                user = User.objects.create_user(
                    username=username,
                    email=student.email,
                    password='student123',  # Default password - should be changed
                    first_name=student.name.split()[0] if student.name.split() else '',
                    last_name=' '.join(student.name.split()[1:]) if len(student.name.split()) > 1 else '',
                )
                
                # Link student to user
                student.user = user
                student.save()
                created += 1
            except Exception as e:
                errors.append(f"{student.name}: {str(e)}")
        
        message = f"Created {created} user account(s)."
        if skipped > 0:
            message += f" Skipped {skipped} (already have accounts)."
        if errors:
            message += f" Errors: {len(errors)}"
            for error in errors[:5]:  # Show first 5 errors
                messages.warning(request, error)
        
        messages.success(request, message)
    
    create_user_accounts.short_description = "Create login accounts for selected students"

class SubjectScheduleInline(admin.TabularInline):
    model = SubjectSchedule
    extra = 1
    fields = ['day_of_week', 'time_start', 'time_end']
    verbose_name = "Schedule Entry"
    verbose_name_plural = "Schedule Entries"
    
    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Customize the form to show day names in a more readable way
        return formset

class SubjectAdminForm(forms.ModelForm):
    """Custom form to handle adviser auto-assignment from instructor"""
    class Meta:
        model = Subject
        fields = '__all__'
        widgets = {
            'adviser': forms.HiddenInput(),  # Hide adviser field, it's auto-set
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide adviser field completely
        if 'adviser' in self.fields:
            self.fields['adviser'].widget = forms.HiddenInput()
            self.fields['adviser'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        code = cleaned_data.get('code')
        instructor = cleaned_data.get('instructor')
        
        # Determine the adviser that will be used (same logic as in save_model)
        adviser = None
        if instructor:
            # Access adviser from instructor - ensure it's loaded
            if hasattr(instructor, 'adviser') and instructor.adviser:
                adviser = instructor.adviser
            elif instructor.pk:
                # If adviser not loaded, fetch it
                try:
                    instructor_obj = Instructor.objects.select_related('adviser').get(pk=instructor.pk)
                    if instructor_obj.adviser:
                        adviser = instructor_obj.adviser
                except Instructor.DoesNotExist:
                    pass
        
        # If no adviser from instructor, check if instance has one (for editing)
        if not adviser and self.instance and self.instance.pk:
            if self.instance.adviser:
                adviser = self.instance.adviser
        
        # Validate unique constraint if we have both code and adviser
        if code and adviser:
            # Check if another subject with same code and adviser exists
            existing_subjects = Subject.objects.filter(code=code, adviser=adviser)
            # Exclude current instance if editing
            if self.instance and self.instance.pk:
                existing_subjects = existing_subjects.exclude(pk=self.instance.pk)
            
            if existing_subjects.exists():
                existing_subject = existing_subjects.first()
                raise ValidationError(
                    f"A subject with code '{code}' already exists for adviser '{adviser.name}'. "
                    f"Existing subject: {existing_subject.name} (ID: {existing_subject.pk}). "
                    "Please choose a different code or assign a different instructor/adviser."
                )
        
        return cleaned_data

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    form = SubjectAdminForm
    list_display = ['code', 'name', 'get_instructor_display', 'get_adviser_display', 'course', 'is_active', 'schedule_count']
    search_fields = ['code', 'name', 'instructor__name', 'instructor__adviser__name', 'instructor__adviser__email', 'course__code', 'course__name']
    list_filter = ['is_active', 'instructor', 'course', 'instructor__adviser']
    autocomplete_fields = ['course', 'instructor']
    inlines = [SubjectScheduleInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('code', 'name', 'instructor', 'course', 'is_active'),
            'description': 'The adviser is automatically determined from the instructor. Select an instructor to assign the subject to their adviser.'
        }),
        ('General Schedule (Fallback)', {
            'fields': ('schedule_days', 'schedule_time_start', 'schedule_time_end'),
            'description': 'These fields are used as fallback when no specific schedule entries exist. Use Schedule Entries below for proper date identification.'
        }),
    )
    
    def get_queryset(self, request):
        """Filter subjects so advisers only see their own subjects (based on instructor)"""
        qs = super().get_queryset(request).select_related('instructor', 'instructor__adviser', 'adviser')
        if request.user.is_superuser:
            return qs
        # Check if user is an adviser
        if hasattr(request.user, 'adviser_profile'):
            # Filter by instructor's adviser OR direct adviser field (for backward compatibility)
            return qs.filter(
                Q(instructor__adviser=request.user.adviser_profile) | 
                Q(adviser=request.user.adviser_profile)
            )
        # For staff users without adviser profile, show all
        if request.user.is_staff:
            return qs
        return qs.none()
    
    def get_readonly_fields(self, request, obj=None):
        """No readonly fields needed since adviser is auto-set from instructor"""
        return []
    
    def get_fieldsets(self, request, obj=None):
        """Return fieldsets without adviser field"""
        return self.fieldsets
    
    def save_model(self, request, obj, form, change):
        """Automatically set adviser from instructor's adviser"""
        # Set adviser from instructor if instructor is assigned
        if obj.instructor:
            # Ensure we have the latest instructor with adviser relationship loaded
            if obj.instructor.pk:
                try:
                    instructor_obj = Instructor.objects.select_related('adviser').get(pk=obj.instructor.pk)
                    if instructor_obj.adviser:
                        obj.adviser = instructor_obj.adviser
                except Instructor.DoesNotExist:
                    pass
            elif hasattr(obj.instructor, 'adviser') and obj.instructor.adviser:
                obj.adviser = obj.instructor.adviser
        
        # Fallback: if no instructor but user is an adviser, set from user's adviser profile
        if not obj.adviser and hasattr(request.user, 'adviser_profile'):
            obj.adviser = request.user.adviser_profile
        
        # Final validation check before saving (as a safety net, form validation should catch most cases)
        if obj.code and obj.adviser:
            existing_subjects = Subject.objects.filter(code=obj.code, adviser=obj.adviser)
            # Exclude current instance if editing
            if change and obj.pk:
                existing_subjects = existing_subjects.exclude(pk=obj.pk)
            
            if existing_subjects.exists():
                existing_subject = existing_subjects.first()
                from django.contrib import messages
                messages.error(
                    request,
                    f"Cannot save: A subject with code '{obj.code}' already exists for adviser '{obj.adviser.name}'. "
                    f"Existing subject: {existing_subject.name} (ID: {existing_subject.pk}). "
                    "Please choose a different code or assign a different instructor/adviser."
                )
                raise ValidationError(
                    f"A subject with code '{obj.code}' already exists for adviser '{obj.adviser.name}'."
                )
        
        super().save_model(request, obj, form, change)
    
    def get_instructor_display(self, obj):
        """Display the instructor name clearly"""
        if obj.instructor:
            return obj.instructor.name
        return "—"
    get_instructor_display.short_description = "Instructor"
    get_instructor_display.admin_order_field = 'instructor__name'
    
    def get_adviser_display(self, obj):
        """Display the adviser name from instructor or direct adviser field"""
        # Prefer adviser from instructor
        if obj.instructor and obj.instructor.adviser:
            return obj.instructor.adviser.name
        # Fallback to direct adviser field
        if obj.adviser:
            return obj.adviser.name
        return "—"
    get_adviser_display.short_description = "Adviser"
    get_adviser_display.admin_order_field = 'instructor__adviser__name'
    
    def schedule_count(self, obj):
        """Display the number of schedule entries"""
        count = obj.schedules.count()
        return f"{count} schedule(s)"
    schedule_count.short_description = "Schedules"

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'get_adviser_display', 'date', 'time', 'status']
    list_filter = ['status', 'date', 'subject', 'subject__adviser']
    search_fields = ['student__name', 'student__rfid_id', 'subject__code', 'subject__adviser__name']
    date_hierarchy = 'date'
    
    def get_queryset(self, request):
        """Filter attendance records so advisers only see their own attendance records"""
        qs = super().get_queryset(request).select_related('student', 'subject', 'subject__adviser', 'subject__instructor', 'subject__instructor__adviser')
        if request.user.is_superuser or request.user.is_staff:
            return qs
        # Check if user is an adviser
        if hasattr(request.user, 'adviser_profile'):
            adviser = request.user.adviser_profile
            # Get subjects where:
            # 1. Subject's adviser matches this adviser, OR
            # 2. Subject's instructor belongs to this adviser
            adviser_subject_ids = Subject.objects.filter(
                Q(adviser=adviser) | Q(instructor__adviser=adviser)
            ).values_list('id', flat=True)
            # Also get subjects where adviser's assigned students are enrolled AND subject's instructor belongs to this adviser
            adviser_student_ids = Student.objects.filter(adviser=adviser).values_list('id', flat=True)
            enrolled_subject_ids = StudentSubject.objects.filter(
                student_id__in=adviser_student_ids
            ).values_list('subject_id', flat=True).distinct()
            # Filter enrolled subjects to only those where instructor belongs to this adviser or subject's adviser matches
            valid_enrolled_subject_ids = Subject.objects.filter(
                id__in=enrolled_subject_ids
            ).filter(
                Q(instructor__adviser=adviser) | Q(adviser=adviser)
            ).values_list('id', flat=True)
            # Combine both: attendance for subjects created by adviser OR subjects their students are enrolled in with valid instructor
            all_subject_ids = list(adviser_subject_ids) + list(valid_enrolled_subject_ids)
            return qs.filter(subject_id__in=all_subject_ids).distinct()
        # For other users, show no attendance records
        return qs.none()
    
    def get_adviser_display(self, obj):
        """Display the adviser name for the subject"""
        if obj.subject and obj.subject.adviser:
            return obj.subject.adviser.name
        return "—"
    get_adviser_display.short_description = "Adviser"
    get_adviser_display.admin_order_field = 'subject__adviser__name'

@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(StudentSubject)
class StudentSubjectAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'academic_year', 'semester']
    list_filter = ['academic_year', 'semester', 'subject']
    search_fields = ['student__name', 'subject__code']

@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ['student', 'email_to', 'email_type', 'status', 'sent_at', 'created_at']
    list_filter = ['status', 'email_type', 'created_at']
    search_fields = ['student__name', 'email_to', 'subject']
    readonly_fields = ['created_at', 'sent_at']

@admin.register(SubjectSchedule)
class SubjectScheduleAdmin(admin.ModelAdmin):
    list_display = ['subject', 'get_day_name', 'time_start', 'time_end', 'created_at']
    list_filter = ['subject', 'day_of_week']
    search_fields = ['subject__code', 'subject__name']
    fields = ['subject', 'day_of_week', 'time_start', 'time_end']
    
    def get_day_name(self, obj):
        """Display day name instead of number"""
        if obj.day_of_week is not None:
            return dict(SubjectSchedule.DAY_CHOICES).get(obj.day_of_week, 'Unknown')
        return 'N/A'
    get_day_name.short_description = 'Day'
