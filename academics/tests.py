import datetime
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from pages.models import Course, Enrollment, UserProfile
from pages.utils import create_student_account, create_teacher_account
from academics.models import CourseGradingPolicy, StudentGrade
from academics.views import is_midterm_entry_open, is_final_entry_open


class AcademicsGradingTests(TestCase):
    def setUp(self):
        # 建立學生
        self.student = create_student_account(
            username='stu_test', name='林小豪', student_class='資管一甲'
        )
        # 建立教師
        self.teacher = create_teacher_account(
            username='tea_chen', name='陳老師'
        )
        # 建立課程
        self.course = Course.objects.create(
            code='IM999',
            name='高階程式設計',
            teacher='陳老師',
            teacher_user=self.teacher,
            classroom='電708',
            credits=3,
            category='REQUIRED',
            target_class='資管一甲',
            day_of_week=1,
            start_period=2,
            end_period=4,
        )
        # 學生選課
        self.enrollment = Enrollment.objects.create(
            user=self.student,
            course=self.course,
        )

    def test_student_cannot_manually_add_credit(self):
        """學生禁止手動新增或修改已完成課程（資安規範與功能刪除驗證）"""
        self.client.force_login(self.student)
        res = self.client.post(reverse('academics:credits'), {
            'course_name': '假課程',
            'credits': 3,
            'category': 'REQUIRED',
            'grade': 99,
        })
        self.assertEqual(res.status_code, 302)
        # 不應有任何 CompletedCourse 被建立
        self.assertFalse(self.student.completed_courses.filter(course_name='假課程').exists())

    def test_student_view_credit_progress_and_grades(self):
        """學生學分進度頁面正確顯示已選課程、小考、期中期末考與學分"""
        # 建立已評分之成績
        policy = CourseGradingPolicy.objects.create(
            course=self.course,
            attendance_weight=20,
            attitude_weight=20,
            assignment_weight=30,
            quiz_weight=30,
        )
        grade = StudentGrade.objects.create(
            user=self.student,
            course=self.course,
            attendance_score=90,
            attitude_score=90,
            assignment_score=80,
            quiz_score=80,
            midterm_score=80,
            final_score=80,
        )
        # 平時分 = (90*20 + 90*20 + 80*30 + 80*30) / 100 = 84.0
        # 總成績 = 84*0.5 + 80*0.25 + 80*0.25 = 42 + 20 + 20 = 82.0 (>= 60 過關)
        self.assertEqual(grade.get_regular_score(), 84.0)
        self.assertEqual(grade.get_total_score(), 82.0)
        self.assertTrue(grade.is_passed)

        self.client.force_login(self.student)
        res = self.client.get(reverse('academics:credits'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '高階程式設計')
        self.assertContains(res, 'IM999')
        self.assertContains(res, '及格通過')
        # 通過此 3 學分
        self.assertEqual(res.context['passed_credits'], 3)
        self.assertEqual(res.context['required_credits'], 3)

    def test_failed_course_does_not_award_credits(self):
        """總成績不及格（< 60）不採計學分"""
        grade = StudentGrade.objects.create(
            user=self.student,
            course=self.course,
            attendance_score=50,
            attitude_score=50,
            assignment_score=50,
            quiz_score=50,
            midterm_score=40,
            final_score=40,
        )
        # 總分 = 50*0.5 + 40*0.25 + 40*0.25 = 45.0 (< 60 不及格)
        self.assertEqual(grade.get_total_score(), 45.0)
        self.assertFalse(grade.is_passed)

        self.client.force_login(self.student)
        res = self.client.get(reverse('academics:credits'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '未通過')
        self.assertEqual(res.context['passed_credits'], 0)

    def test_date_restriction_rules(self):
        """驗證期中（每年11/6與11/23起）與期末（每年1/8與6/29起）時間限制"""
        # 11/1: 期中未開放、期末未開放
        d_1101 = datetime.date(2026, 11, 1)
        self.assertFalse(is_midterm_entry_open(d_1101))
        self.assertFalse(is_final_entry_open(d_1101))

        # 11/6: 期中開放、期末未開放
        d_1106 = datetime.date(2026, 11, 6)
        self.assertTrue(is_midterm_entry_open(d_1106))
        self.assertFalse(is_final_entry_open(d_1106))

        # 11/23: 期中開放
        d_1123 = datetime.date(2026, 11, 23)
        self.assertTrue(is_midterm_entry_open(d_1123))

        # 1/7: 期末未開放
        d_0107 = datetime.date(2027, 1, 7)
        self.assertFalse(is_final_entry_open(d_0107))

        # 1/8: 期末開放
        d_0108 = datetime.date(2027, 1, 8)
        self.assertTrue(is_final_entry_open(d_0108))

        # 6/29: 期末開放
        d_0629 = datetime.date(2027, 6, 29)
        self.assertTrue(is_final_entry_open(d_0629))

    def test_teacher_can_manage_grades_and_policy(self):
        """授課教師可選擇課程、選擇班級、自訂平時配分與登記學生成績"""
        self.client.force_login(self.teacher)
        # 造訪評分頁面
        res = self.client.get(reverse('academics:teacher_grades'), {'course_id': self.course.id})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '高階程式設計')
        self.assertContains(res, '林小豪')

        grade_obj, _ = StudentGrade.objects.get_or_create(user=self.student, course=self.course)

        # 提交平時成績與自訂配分 (點名 20%, 態度 20%, 作業 30%, 小考 30%)
        post_data = {
            'course_id': self.course.id,
            'student_class': 'ALL',
            'attendance_weight': 20,
            'attitude_weight': 20,
            'assignment_weight': 30,
            'quiz_weight': 30,
            f'attendance_{grade_obj.id}': 95,
            f'attitude_{grade_obj.id}': 90,
            f'assignment_{grade_obj.id}': 85,
            f'quiz_{grade_obj.id}': 88,
        }
        res_post = self.client.post(reverse('academics:teacher_grades'), post_data, follow=True)
        self.assertEqual(res_post.status_code, 200)

        grade_obj.refresh_from_db()
        self.assertEqual(grade_obj.attendance_score, 95.0)
        self.assertEqual(grade_obj.attitude_score, 90.0)
        self.assertEqual(grade_obj.assignment_score, 85.0)
        self.assertEqual(grade_obj.quiz_score, 88.0)

        policy = self.course.grading_policy
        self.assertEqual(policy.attendance_weight, 20)
        self.assertEqual(policy.quiz_weight, 30)
