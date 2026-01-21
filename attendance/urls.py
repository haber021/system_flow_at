from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('reset-password/<str:token>/', views.reset_password_view, name='reset_password'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Student Management
    path('students/', views.student_list, name='student_list'),
    path('students/add/', views.student_add, name='student_add'),
    path('students/<int:student_id>/edit/', views.student_edit, name='student_edit'),
    path('students/<int:student_id>/delete/', views.student_delete, name='student_delete'),
    path('students/import-csv/', views.student_import_csv, name='student_import_csv'),
    path('students/export-csv/', views.student_export_csv, name='student_export_csv'),
    
    # Subject Management
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/add/', views.subject_add, name='subject_add'),
    path('subjects/<int:subject_id>/edit/', views.subject_edit, name='subject_edit'),
    path('subjects/<int:subject_id>/delete/', views.subject_delete, name='subject_delete'),
    path('subjects/<int:subject_id>/assign-students/', views.assign_students_to_subject, name='assign_students'),
    
    # Section Management
    path('sections/', views.section_list, name='section_list'),
    path('sections/add/', views.section_add, name='section_add'),
    path('sections/<int:section_id>/edit/', views.section_edit, name='section_edit'),
    path('sections/<int:section_id>/delete/', views.section_delete, name='section_delete'),
    
    # RFID Attendance Scan
    path('scan/', views.scan_view, name='scan'),
    path('scan/manual-entry/', views.manual_entry, name='manual_entry'),
    
    # Attendance Logs
    path('attendance-logs/', views.attendance_logs, name='attendance_logs'),
    path('attendance-logs/export-csv/', views.attendance_logs_export_csv, name='attendance_logs_export_csv'),
    
    # Student Attendance Summary
    path('student-summary/', views.student_attendance_summary, name='student_summary'),
    path('student-summary/<int:student_id>/', views.student_attendance_summary, name='student_summary_detail'),
    path('bulk-send-emails/', views.bulk_send_emails, name='bulk_send_emails'),
    path('student-summary/send-adviser-pdf/', views.send_student_summary_pdf_to_adviser, name='send_student_summary_pdf_to_adviser'),
    
    # Semester Report
    path('semester-report/<int:student_id>/', views.semester_report, name='semester_report'),
    
    # Email
    path('email-preview/<int:student_id>/', views.email_preview, name='email_preview'),
    path('email-logs/', views.email_logs, name='email_logs'),
    path('email-logs/export/', views.email_logs_export_csv, name='email_logs_export_csv'),
    path('email-logs/<int:log_id>/resend/', views.email_resend, name='email_resend'),
    
    # Settings
    path('settings/', views.settings_view, name='settings'),
    path('settings/semester-reset/', views.semester_reset, name='semester_reset'),
    
    # Profile
    path('profile/', views.profile_view, name='profile'),
    
    # Real-time Monitoring
    path('live-monitor/', views.live_monitor, name='live_monitor'),
    path('api/live-monitor/', views.live_monitor_api, name='live_monitor_api'),
    
    # Mobile View
    path('mobile/', views.mobile_scan, name='mobile_scan'),
    
    # Public Student View
    path('student-view/', views.student_view, name='student_view'),
    
    # Student Login and Dashboard
    path('student/register/', views.student_register, name='student_register'),
    path('student/login/', views.student_login, name='student_login'),
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/absences/', views.student_absences, name='student_absences'),
    path('student/enroll-subjects/', views.student_enroll_subjects, name='student_enroll_subjects'),
    path('student/features/', views.student_features_view, name='student_features'),
    path('student/suggest/', views.student_suggest_feature, name='student_suggest_feature'),
    path('student/profile/', views.student_profile_view, name='student_profile'),
    path('student/history/', views.student_history, name='student_history'),
    path('student/logout/', views.student_logout, name='student_logout'),
    
    # Adviser Enrollment Confirmation
    path('adviser/enrollment-requests/', views.adviser_enrollment_requests, name='adviser_enrollment_requests'),
    path('adviser/features/', views.subject_list, name='adviser_features'),  # Redirects to subject_list which shows features for advisers
    path('adviser/subjects-monitor/', views.adviser_subjects_monitor, name='adviser_subjects_monitor'),
    path('adviser/absences/', views.adviser_absent_students, name='adviser_absent_students'),
    path('adviser/absences/mark-present/', views.adviser_mark_absences_present, name='adviser_mark_absences_present'),
    path('api/enrollment-requests-count/', views.enrollment_requests_count_api, name='enrollment_requests_count_api'),
    
    # API Endpoints for Form Dropdowns
    path('api/courses/', views.api_courses, name='api_courses'),
    path('api/sections/', views.api_sections, name='api_sections'),
    path('api/subjects/', views.api_subjects, name='api_subjects'),
    path('api/advisers/', views.api_advisers, name='api_advisers'),
    path('api/student-subjects/<int:student_id>/', views.api_student_subjects, name='api_student_subjects'),
    path('api/instructors/', views.api_instructors, name='api_instructors'),
    # Calendar views and API
    path('calendar/', views.calendar_events_view, name='calendar_events'),
    path('events/create/', views.events_create_api, name='events_create_api'),
    path('events/list/', views.events_list_api, name='events_list_api'),
    path('events/<int:event_id>/update/', views.events_update_api, name='events_update_api'),
    path('events/<int:event_id>/delete/', views.events_delete_api, name='events_delete_api'),
    path('events/cleanup-holiday-absences/', views.cleanup_holiday_absences, name='cleanup_holiday_absences'),
    path('subject/<int:subject_id>/sections/', views.get_subject_sections_api, name='get_subject_sections_api'),
]