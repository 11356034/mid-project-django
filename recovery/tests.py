from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .views import DEFAULT_STUDENT_PASSWORD, MAX_FAILED_ATTEMPTS


class ForgotPasswordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse('recovery:forgot_password')

        self.student = User.objects.create_user(
            username='tester01', password='old-password-1', first_name='王小明'
        )
        self.student.profile.role = 'STUDENT'
        self.student.profile.student_id = 'B11300001'
        self.student.profile.save()

        self.teacher = User.objects.create_user(
            username='teacher01', password='old-password-2', first_name='李老師'
        )
        self.teacher.profile.role = 'TEACHER'
        self.teacher.profile.student_id = 'T0001'
        self.teacher.profile.save()

        self.admin = User.objects.create_user(
            username='admin', password='old-password-3', first_name='管理員', is_staff=True
        )
        self.admin.profile.role = 'ADMIN'
        self.admin.profile.student_id = 'A0001'
        self.admin.profile.save()

    def post(self, username, student_id, name):
        return self.client.post(self.url, {
            'username': username, 'student_id': student_id, 'name': name,
        })

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_success_resets_password_to_default(self):
        response = self.post('tester01', 'B11300001', '王小明')
        self.assertContains(response, DEFAULT_STUDENT_PASSWORD)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(DEFAULT_STUDENT_PASSWORD))

    def test_input_is_normalized(self):
        """學號大小寫、姓名多餘空白不影響核對"""
        self.post('tester01', 'b11300001', ' 王 小明 ')
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(DEFAULT_STUDENT_PASSWORD))

    def test_wrong_student_id_does_not_reset(self):
        self.post('tester01', 'B99999999', '王小明')
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('old-password-1'))

    def test_wrong_name_does_not_reset(self):
        self.post('tester01', 'B11300001', '別人')
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('old-password-1'))

    def test_unknown_username_shows_generic_error(self):
        response = self.post('nobody', 'B11300001', '王小明')
        self.assertContains(response, '資料核對失敗')

    def test_teacher_cannot_use_feature(self):
        self.post('teacher01', 'T0001', '李老師')
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password('old-password-2'))

    def test_admin_cannot_use_feature(self):
        self.post('admin', 'A0001', '管理員')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('old-password-3'))

    def test_lockout_after_too_many_failures(self):
        for _ in range(MAX_FAILED_ATTEMPTS):
            self.post('tester01', 'B99999999', '王小明')
        # 已鎖定：即使這次資料全對也不會重設
        response = self.post('tester01', 'B11300001', '王小明')
        self.assertContains(response, '嘗試次數過多')
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('old-password-1'))

    def test_only_password_changes(self):
        """重設密碼不影響學號、姓名等個人資料"""
        self.post('tester01', 'B11300001', '王小明')
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, '王小明')
        self.assertEqual(self.student.profile.student_id, 'B11300001')
