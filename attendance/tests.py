from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from .models import Adviser, Instructor, Student, Subject, StudentSubject, Course, Section, FeatureSuggestion
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