# Student Absence Process - System Flow Documentation

## Overview
This document explains how the system processes and tracks student absences in the RFID Attendance Monitoring System.

## Absence Status Types

The system recognizes three attendance statuses:
- **PRESENT**: Student scanned RFID card on time
- **LATE**: Student scanned RFID card after the grace period
- **ABSENT**: Student did not scan RFID card or was manually marked absent

---

## How Absence is Determined

### 1. **Automatic Absence Marking (Primary Method)**

When viewing **Attendance Logs** for a specific date and subject, the system automatically marks students as ABSENT:

**Process Flow:**
```
1. User views Attendance Logs for a specific date and subject
   ↓
2. System retrieves all enrolled students for that subject
   ↓
3. System checks which students have attendance records (PRESENT/LATE) for that date
   ↓
4. System identifies students WITHOUT any attendance record
   ↓
5. System automatically creates ABSENT records for those students
   ↓
6. System checks if warning email should be sent (if threshold reached)
```

**Code Location:** `attendance/views.py` - `attendance_logs()` function (lines 2496-2510)

**Key Logic:**
```python
# Get all enrolled students
all_students = Student.objects.filter(id__in=enrolled_student_ids)

# Find students who are present (have attendance records)
present_student_ids = attendances.values_list('student_id', flat=True)

# Students without attendance records are marked as ABSENT
absent_students = all_students.exclude(id__in=present_student_ids)

# Create ABSENT records
for student in absent_students:
    attendance, created = Attendance.objects.get_or_create(
        student=student,
        subject_id=subject_id,
        date=filter_date,
        defaults={'status': 'ABSENT'}
    )
```

---

### 2. **Manual Absence Entry**

Administrators/Advisers can manually mark students as ABSENT through the Manual Entry form.

**Process Flow:**
```
1. Admin/Adviser navigates to Manual Entry page
   ↓
2. Selects student, subject, date, and status (ABSENT)
   ↓
3. System validates the entry (unless validation is skipped)
   ↓
4. System creates/updates attendance record with ABSENT status
   ↓
5. System checks if warning email should be sent
```

**Code Location:** `attendance/views.py` - `manual_entry()` function (lines 2308-2424)

**Key Features:**
- Can set status directly to "ABSENT"
- Optional time validation (can be skipped by admin)
- Prevents duplicate records (one record per student/subject/date)

---

### 3. **RFID Scanning Process**

During RFID scanning, students are NOT automatically marked as ABSENT. Instead:

**Process Flow:**
```
1. Student taps RFID card
   ↓
2. System validates:
   - Student is enrolled in the subject
   - Time is within valid attendance window
   - Date matches class schedule
   ↓
3. If valid, student is marked as:
   - PRESENT (if on time)
   - LATE (if after grace period)
   ↓
4. If student doesn't scan, they remain unmarked
   ↓
5. Absence is determined later when viewing Attendance Logs
```

**Code Location:** `attendance/views.py` - `scan_view()` function (lines 1944-2305)

**Important:** The scanning process only creates PRESENT or LATE records. ABSENT records are created separately when viewing attendance logs.

---

## Absence Tracking and Reporting

### Database Model

**Attendance Model** (`attendance/models.py` - lines 222-257):
```python
class Attendance(models.Model):
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
    ]
    
    student = ForeignKey(Student)
    subject = ForeignKey(Subject)
    date = DateField()
    time_in = TimeField(null=True, blank=True)
    time_out = TimeField(null=True, blank=True)
    status = CharField(choices=STATUS_CHOICES, default='PRESENT')
    
    # Constraints: Only ONE record per student/subject/date
    UniqueConstraint(fields=['student', 'subject', 'date'])
```

**Key Points:**
- One attendance record per student per subject per day
- ABSENT records may not have `time_in` or `time_out` values
- Status is stored as 'ABSENT' string

---

## Warning Email System

### Automatic Warning Emails

When a student is marked as ABSENT, the system checks if they've reached the warning threshold.

**Process Flow:**
```
1. Student is marked as ABSENT (automatic or manual)
   ↓
2. System counts total ABSENT records for that student/subject
   ↓
3. System checks if count >= warning threshold (default: 3)
   ↓
4. System checks if warning was sent recently (within 7 days)
   ↓
5. If threshold reached AND no recent warning:
   - Send warning email to student
   - Log email in EmailLog table
```

**Code Location:** `attendance/views.py` - `check_and_send_warning_email()` function (lines 1778-1857)

**Settings:**
- **Warning Threshold**: `SystemSettings.send_warnings_after` (default: 3 absences)
- **Email Notifications**: `SystemSettings.email_notifications_enabled` (default: True)
- **Duplicate Prevention**: No duplicate warnings within 24 hours

**Warning Email Content:**
- Student name
- Subject code and name
- Number of absences accumulated
- Warning threshold
- Instructions to contact instructor

---

## System Settings Related to Absence

### Absent Threshold Percentage
- **Setting**: `SystemSettings.absent_threshold_percent`
- **Default**: 50%
- **Purpose**: Used for reporting and determining if student has excessive absences
- **Location**: System Settings page

### Grace Period
- **Setting**: `SystemSettings.grace_period_minutes`
- **Default**: 15 minutes
- **Purpose**: Time window before student is marked as LATE instead of PRESENT

### Late Threshold
- **Setting**: `SystemSettings.late_threshold_minutes`
- **Default**: 30 minutes
- **Purpose**: Maximum time after class start to still allow attendance

---

## Attendance Logs View - Key Features

### Automatic Absence Creation

When viewing attendance logs (`attendance_logs` view):

1. **Filters Applied:**
   - Date filter (defaults to today)
   - Subject filter (optional)
   - Adviser/User access restrictions

2. **Absence Detection:**
   - Compares enrolled students vs. students with attendance records
   - Creates ABSENT records for missing students
   - Updates statistics (Present/Absent/Late counts)

3. **Statistics Display:**
   ```python
   stats = {
       'present': attendances.filter(status='PRESENT').count(),
       'absent': attendances.filter(status='ABSENT').count(),
       'late': attendances.filter(status='LATE').count(),
       'total': attendances.count(),
   }
   ```

---

## Student Dashboard - Absence Display

Students can view their absence records through:
- **Student Dashboard**: Shows total absences and today's status
- **Student History**: Detailed attendance history with ABSENT records highlighted
- **Subject Summary**: Per-subject absence counts

**Visual Indicators:**
- ABSENT records are displayed with red badges/icons
- Absence count is prominently displayed
- Warning messages shown if threshold is reached

---

## Best Practices

### For Administrators/Advisers:

1. **Regular Monitoring:**
   - Review Attendance Logs daily
   - System automatically creates ABSENT records when viewing logs
   - Check for students approaching warning threshold

2. **Manual Corrections:**
   - Use Manual Entry to correct attendance if needed
   - Can mark students as ABSENT retroactively
   - Can update status from ABSENT to PRESENT if error occurred

3. **Email Notifications:**
   - Ensure email notifications are enabled in settings
   - Monitor Email Logs to verify warnings are being sent
   - Check for failed email deliveries

### For Students:

1. **RFID Scanning:**
   - Always scan RFID card when attending class
   - Scan within the valid time window
   - Check student dashboard regularly for attendance status

2. **Absence Prevention:**
   - Attend all scheduled classes
   - Contact instructor if absence is unavoidable
   - Review attendance policy in course syllabus

---

## Technical Implementation Details

### Database Queries

**Finding Absent Students:**
```python
# Get enrolled students
enrolled_students = StudentSubject.objects.filter(
    subject_id=subject_id
).values_list('student_id', flat=True)

# Get students with attendance records
present_student_ids = Attendance.objects.filter(
    subject_id=subject_id,
    date=filter_date
).values_list('student_id', flat=True)

# Absent students = enrolled - present
absent_students = Student.objects.filter(
    id__in=enrolled_students
).exclude(id__in=present_student_ids)
```

### Preventing Duplicates

The system uses database constraints to prevent duplicate attendance records:
```python
UniqueConstraint(
    fields=['student', 'subject', 'date'],
    name='unique_attendance_per_day'
)
```

This ensures only ONE attendance record exists per student/subject/date, preventing duplicate ABSENT records.

---

## Summary

**The absence process works as follows:**

1. **During Class:** Students scan RFID cards → marked as PRESENT or LATE
2. **After Class:** When viewing Attendance Logs → system automatically marks non-scanned students as ABSENT
3. **Warning System:** If absences reach threshold → warning email sent automatically
4. **Manual Override:** Administrators can manually mark students as ABSENT through Manual Entry

**Key Takeaway:** Absence is determined by the **absence of a PRESENT/LATE record**, not by a direct "absent scan". The system creates ABSENT records automatically when reviewing attendance logs for a specific date and subject.

