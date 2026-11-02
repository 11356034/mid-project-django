from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Course(models.Model):
    CATEGORY_CHOICES = [
        ('REQUIRED', '必修'),
        ('ELECTIVE', '選修'),
    ]

    DAY_CHOICES = [
        (1, '星期一'),
        (2, '星期二'),
        (3, '星期三'),
        (4, '星期四'),
        (5, '星期五'),
    ]

    CLASS_CHOICES = [
        ('資管一甲', '資管一甲'),
        ('資管二甲', '資管二甲'),
        ('資管三甲', '資管三甲'),
        ('ALL', '全系/不限班級'),
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name="課程代碼")
    name = models.CharField(max_length=100, verbose_name="課程名稱")
    teacher = models.CharField(max_length=50, verbose_name="授課教師")
    teacher_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='taught_courses', verbose_name="授課教師帳號")
    classroom = models.CharField(max_length=50, verbose_name="上課教室")
    credits = models.PositiveIntegerField(default=2, verbose_name="學分數")
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='ELECTIVE', verbose_name="課程屬性")
    target_class = models.CharField(max_length=20, choices=CLASS_CHOICES, default='資管一甲', verbose_name="開課班級")
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES, default=1, verbose_name="上課星期")
    start_period = models.PositiveSmallIntegerField(default=1, verbose_name="開始節次")
    end_period = models.PositiveSmallIntegerField(default=1, verbose_name="結束節次")
    is_open_for_enrollment = models.BooleanField(default=True, verbose_name="開放學生選修")
    max_students = models.PositiveIntegerField(default=50, verbose_name="選課人數上限")
    description = models.TextField(blank=True, default="", verbose_name="課程描述")
    color_tag = models.CharField(max_length=30, default="indigo", verbose_name="代表顏色")

    class Meta:
        ordering = ['day_of_week', 'start_period', 'code']
        verbose_name = "課程"
        verbose_name_plural = "課程列表"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.name} ({self.get_day_of_week_display()} 第{self.start_period}-{self.end_period}節)"

    @property
    def periods_list(self):
        return list(range(self.start_period, self.end_period + 1))

    @property
    def period_display(self):
        day_str = dict(self.DAY_CHOICES).get(self.day_of_week, '')
        if self.start_period == self.end_period:
            return f"{day_str} 第 {self.start_period} 節"
        return f"{day_str} 第 {self.start_period}~{self.end_period} 節"

    @property
    def current_enrolled_count(self):
        return self.enrollments.count()

    @property
    def display_teacher_username(self):
        """若有綁定 teacher_user 則顯示其 username，若尚未綁定但同名教師帳號存在則自動對應"""
        if self.teacher_user:
            return self.teacher_user.username
        if self.teacher:
            match = User.objects.filter(first_name=self.teacher, profile__role='TEACHER').first()
            if match:
                return match.username
        return ""


class Enrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments', verbose_name="選課學生")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments', verbose_name="選修課程")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="選課時間")

    class Meta:
        unique_together = ('user', 'course')
        verbose_name = "選課紀錄"
        verbose_name_plural = "選課紀錄列表"

    def __str__(self):
        return f"{self.user.username} -> {self.course.name}"


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ('M', '男'),
        ('F', '女'),
        ('O', '其他'),
    ]

    ROLE_CHOICES = [
        ('STUDENT', '學生'),
        ('TEACHER', '教師'),
        ('ADMIN', '教務管理員'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', verbose_name="使用者帳號")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STUDENT', verbose_name="身分角色")
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, default='M', verbose_name="性別")
    student_id = models.CharField(max_length=20, blank=True, default="", verbose_name="學號")
    student_class = models.CharField(max_length=50, default="資管一甲", verbose_name="班級")
    avatar = models.FileField(upload_to='avatars/', blank=True, null=True, verbose_name="個人頭像")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="最後更新時間")

    class Meta:
        verbose_name = "個人設定"
        verbose_name_plural = "個人設定列表"

    def __str__(self):
        return f"{self.user.username} 的個人檔案"

    @property
    def avatar_url(self):
        if self.avatar:
            try:
                return self.avatar.url
            except Exception:
                pass
        return '/static/image/preview.webp'


@receiver(post_save, sender=User)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)
