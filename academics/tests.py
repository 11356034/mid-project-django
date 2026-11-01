from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import CompletedCourse


class CreditProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='credit_student', password='test-pass-123')
        self.client.login(username='credit_student', password='test-pass-123')

    def test_student_can_add_completed_course(self):
        response = self.client.post(reverse('academics:credits'), {
            'course_name': 'Python 程式設計', 'credits': 3,
            'category': 'REQUIRED', 'semester': '114-1', 'grade': 90,
        })
        self.assertRedirects(response, reverse('academics:credits'))
        self.assertEqual(CompletedCourse.objects.filter(user=self.user).count(), 1)

    def test_student_only_sees_own_records(self):
        other = User.objects.create_user(username='other_student', password='test-pass-123')
        CompletedCourse.objects.create(user=other, course_name='別人的課', credits=3, category='ELECTIVE', semester='114-1')
        response = self.client.get(reverse('academics:credits'))
        self.assertNotContains(response, '別人的課')

    def test_delete_is_post_only_and_owner_scoped(self):
        other = User.objects.create_user(username='other_student', password='test-pass-123')
        record = CompletedCourse.objects.create(user=other, course_name='別人的課', credits=3, category='ELECTIVE', semester='114-1')
        response = self.client.post(reverse('academics:delete_credit', args=[record.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(CompletedCourse.objects.filter(pk=record.pk).exists())
