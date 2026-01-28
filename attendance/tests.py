from django.test import TestCase, RequestFactory
from django.urls import reverse
from unittest.mock import patch
from datetime import datetime, date, time
import pytz
from django.contrib.auth.models import User
from .models import Adviser, Instructor, Student, Subject, StudentSubject, Course, Section, FeatureSuggestion
from .models import SubjectSchedule, Attendance, SystemSettings
from .views import filter_subjects_by_user

from django.test import Client


class FeatureSuggestionTest(TestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(username='student2', password='password', email='student2@example.com')
        self.course = Course.objects.create(code='BSIT', name='Bachelor of Science in IT')
        self.section = Section.objects.create(code='S1', name='Section 1')
        self.student = Student.objects.create(user=self.student_user, name='Feature Student', course=self.course, section=self.section, email='student2@example.com')
        self.client = Client()

    def test_student_can_submit_feature_suggestion(self):
        self.client.login(username='student2', password='password')
        response = self.client.post('/student/suggest/', {'title': 'Improve UI', 'description': 'Please add dark mode.'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(FeatureSuggestion.objects.filter(student=self.student, title='Improve UI').exists())

class SubjectFilterTest(TestCase):
    def setUp(self):
        # Create users
        self.adviser_user = User.objects.create_user(username='adviseruser', password='password')
        self.instructor_user = User.objects.create_user(username='instructoruser', password='password')
        self.student_user = User.objects.create_user(username='studentuser', password='password')

        # Create course and section
        self.course = Course.objects.create(code='BSCS', name='Bachelor of Science in Computer Science')
        self.section = Section.objects.create(code='CS-101', name='Computer Science 101')

        # Create adviser
        self.adviser = Adviser.objects.create(user=self.adviser_user, name='Dr. Adviser')
        self.adviser.courses.add(self.course)


        # Create instructor and assign to adviser
        self.instructor = Instructor.objects.create(name='Mr. Instructor', adviser=self.adviser)

        # Create student
        self.student = Student.objects.create(
            user=self.student_user,
            name='Test Student',
            course=self.course,
            section=self.section,
            adviser=self.adviser 
        )

        # Create a subject taught by the instructor
        self.subject_by_instructor = Subject.objects.create(
            code='PROG101',
            name='Programming 101',
            instructor=self.instructor,
            course=self.course
        )

        # Create a subject assigned to the adviser directly
        self.subject_by_adviser = Subject.objects.create(
            code='ETHICS101',
            name='Ethics 101',
            adviser=self.adviser,
            course=self.course
        )

        # Create a subject where the adviser's student is enrolled
        self.other_adviser = Adviser.objects.create(name='Other Adviser', email='other@example.com')
        self.other_instructor = Instructor.objects.create(name='Other Instructor', adviser=self.other_adviser)
        self.subject_with_student = Subject.objects.create(
            code='MATH101',
            name='Mathematics 101',
            instructor=self.other_instructor,
            course=self.course
        )
        StudentSubject.objects.create(student=self.student, subject=self.subject_with_student)
        
        # Create a subject with no relation to the adviser
        self.unrelated_subject = Subject.objects.create(
            code='ART101',
            name='Art Appreciation',
            instructor=self.other_instructor,
            course=self.course
        )


    def test_filter_subjects_by_user_for_adviser(self):
        """
        Test that an adviser can see subjects taught by their instructors,
        subjects assigned to them directly, and subjects their students are enrolled in.
        """
        # Get the filtered subjects for the adviser
        filtered_subjects = filter_subjects_by_user(self.adviser_user)

        # Check that the subject taught by the adviser's instructor is in the queryset
        self.assertIn(self.subject_by_instructor, filtered_subjects)

        # Check that the subject assigned directly to the adviser is in the queryset
        self.assertIn(self.subject_by_adviser, filtered_subjects)

        # Check that the subject where the adviser's student is enrolled is in the queryset
        self.assertIn(self.subject_with_student, filtered_subjects)
        
        # Check that the unrelated subject is not in the queryset
        self.assertNotIn(self.unrelated_subject, filtered_subjects)

        # Check the total count
        self.assertEqual(filtered_subjects.count(), 3)


class ScanStrictScheduleTest(TestCase):
    def setUp(self):
        # Create staff user to bypass adviser/instructor filtering in scan_view
        self.staff_user = User.objects.create_user(username='staff', password='password', is_staff=True)
        self.client = Client()
        self.client.login(username='staff', password='password')

        # Settings covering today
        self.settings = SystemSettings.get_settings()
        today = datetime.now().date()
        self.settings.semester_start_date = today
        self.settings.semester_end_date = today
        self.settings.enable_time_validation = True
        self.settings.save()

        # Base course/section
        self.course = Course.objects.create(code='BSIT', name='Bachelor of Science in IT')
        self.section = Section.objects.create(code='SEC-A', name='Section A')

        # Subjects
        self.subject_a = Subject.objects.create(code='SUBJ-A', name='Subject A', course=self.course, is_active=True)
        self.subject_a.sections.add(self.section)
        self.subject_b = Subject.objects.create(code='SUBJ-B', name='Subject B', course=self.course, is_active=True)
        self.subject_b.sections.add(self.section)

        # Today-specific schedules
        self.today = today
        SubjectSchedule.objects.create(subject=self.subject_a, date=self.today, time_start=time(8, 0), time_end=time(9, 0))
        SubjectSchedule.objects.create(subject=self.subject_b, date=self.today, time_start=time(9, 0), time_end=time(10, 0))

        # Student enrolled in subject A
        self.student = Student.objects.create(
            rfid_id='RFID-001',
            student_id='S-001',
            name='Scan Student',
            course=self.course,
            section=self.section,
            email='scan@example.com'
        )
        StudentSubject.objects.create(student=self.student, subject=self.subject_a)

    def _manila_dt(self, h, m):
        tz = pytz.timezone('Asia/Manila')
        naive = datetime(self.today.year, self.today.month, self.today.day, h, m, 0)
        return tz.localize(naive)

    @patch('attendance.views.get_manila_now')
    def test_auto_selection_strict_active_subject(self, mock_now):
        # At 08:30, Subject A should be strictly active
        mock_now.return_value = self._manila_dt(8, 30)
        resp = self.client.get(reverse('scan'))
        self.assertEqual(resp.status_code, 200)
        # Confirm auto-selected subject is Subject A
        self.assertEqual(resp.context['subject'].id, self.subject_a.id)
        self.assertTrue(resp.context['auto_selected'])

    def test_scan_post_reject_outside_exact_window(self):
        # 07:59 is outside strict window for Subject A
        resp = self.client.post(reverse('scan'), {
            'rfid_id': 'RFID-001',
            'subject_id': str(self.subject_a.id),
            'manual_time': '07:59'
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        # No attendance should be created
        self.assertFalse(Attendance.objects.filter(student=self.student, subject=self.subject_a, date=self.today).exists())
        # Check error message
        messages = list(resp.context['messages'])
        self.assertTrue(any('not allowed' in m.message.lower() or 'no active schedule' in m.message.lower() for m in messages))

    def test_scan_post_success_inside_exact_window(self):
        # 08:05 is inside Subject A's strict window
        resp = self.client.post(reverse('scan'), {
            'rfid_id': 'RFID-001',
            'subject_id': str(self.subject_a.id),
            'manual_time': '08:05'
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        att = Attendance.objects.filter(student=self.student, subject=self.subject_a, date=self.today).first()
        self.assertIsNotNone(att)
        self.assertIsNotNone(att.time_in)
        self.assertIsNotNone(att.schedule)