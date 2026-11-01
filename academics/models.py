from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class CourseGradingPolicy(models.Model):
    """
    任課教師自訂平時成績配分比例。
    平時成績佔總成績 50%，考試成績佔 50%（期中考 25%、期末考 25%）。
    平時成績可選項目百分比（點名、上課態度、課堂作業、小考），由老師自己分配。
    """
    course = models.OneToOneField(
        'pages.Course',
        on_delete=models.CASCADE,
        related_name='grading_policy',
        verbose_name='課程',
    )
    attendance_weight = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='點名比例 (%)',
    )
    attitude_weight = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='上課態度比例 (%)',
    )
    assignment_weight = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='課堂作業比例 (%)',
    )
    quiz_weight = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='小考比例 (%)',
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新時間')

    class Meta:
        verbose_name = '課程評分配分'
        verbose_name_plural = '課程評分配分列表'

    def __str__(self):
        return f"{self.course.name} 配分: 點名{self.attendance_weight}%, 態度{self.attitude_weight}%, 作業{self.assignment_weight}%, 小考{self.quiz_weight}%"


class StudentGrade(models.Model):
    """
    修課學生成績紀錄：由任課老師手動輸入個別分數。
    - 平時成績（佔 50%）：點名、上課態度、課堂作業、小考（依老師自訂比例計算）
    - 考試成績（佔 50%）：期中考（佔 25%）、期末考（佔 25%）
    - 總成績達 60 分（含）以上為及格過關，計入通過學分。
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_grades',
        verbose_name='學生',
    )
    course = models.ForeignKey(
        'pages.Course',
        on_delete=models.CASCADE,
        related_name='student_grades',
        verbose_name='修讀課程',
    )

    # 平時成績細項（0-100 分）
    attendance_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='點名成績',
    )
    attitude_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='上課態度成績',
    )
    assignment_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='課堂作業成績',
    )
    quiz_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='小考成績',
    )

    # 考試成績（各佔總成績 25%）
    midterm_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='期中考成績 (25%)',
    )
    final_score = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='期末考成績 (25%)',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='建立時間')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新時間')

    class Meta:
        unique_together = ('user', 'course')
        verbose_name = '學生修課成績'
        verbose_name_plural = '學生修課成績列表'

    def __str__(self):
        return f"{self.user.username} - {self.course.name}"

    def get_regular_score(self):
        """
        依該課程教師設定之配分比例計算平時成績總分（滿分 100 分）。
        若尚未填寫任何平時項目則回傳 None。
        """
        policy = getattr(self.course, 'grading_policy', None)
        w_att = policy.attendance_weight if policy else 25
        w_atti = policy.attitude_weight if policy else 25
        w_asg = policy.assignment_weight if policy else 25
        w_qz = policy.quiz_weight if policy else 25

        items = [
            (self.attendance_score, w_att),
            (self.attitude_score, w_atti),
            (self.assignment_score, w_asg),
            (self.quiz_score, w_qz),
        ]
        valid_items = [(s, w) for s, w in items if s is not None and w > 0]
        if not valid_items:
            return None

        total_weight = sum(w for _, w in valid_items)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(s * w for s, w in valid_items)
        return round(weighted_sum / total_weight, 1)

    def get_total_score(self):
        """
        計算總成績：平時成績 50% + 期中考 25% + 期末考 25%。
        """
        reg = self.get_regular_score()
        mid = self.midterm_score
        fin = self.final_score

        if reg is None and mid is None and fin is None:
            return None

        score = 0.0
        if reg is not None:
            score += reg * 0.5
        if mid is not None:
            score += mid * 0.25
        if fin is not None:
            score += fin * 0.25

        return round(score, 1)

    @property
    def is_passed(self):
        """
        統計該課程是否過關（及格）：
        - 總成績達 60 分（含）以上為 True（過關）。
        - 若期末考已輸入且總成績未滿 60 分為 False（不及格）。
        - 若期末考尚未輸入且目前未達 60 分為 None（修讀中 / 評分中）。
        """
        tot = self.get_total_score()
        if tot is None:
            return None
        if tot >= 60.0:
            return True
        if self.final_score is not None:
            return False
        return None

    @property
    def status_display(self):
        passed = self.is_passed
        if passed is True:
            return '及格（通過）'
        elif passed is False:
            return '不及格（未通過）'
        return '修讀中'


class CompletedCourse(models.Model):
    """舊版已完成課程紀錄（已由 StudentGrade 取代，保留模型相容）"""
    CATEGORY_CHOICES = [
        ('REQUIRED', '必修'),
        ('ELECTIVE', '選修'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='completed_courses',
        verbose_name='學生',
    )
    course_name = models.CharField(max_length=120, verbose_name='課程名稱')
    credits = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name='學分數',
    )
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, verbose_name='課程類別')
    semester = models.CharField(max_length=30, verbose_name='修課學期', help_text='例如：114-1')
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='成績',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='建立時間')

    class Meta:
        ordering = ['-semester', 'course_name']
        verbose_name = '已完成課程'
        verbose_name_plural = '已完成課程紀錄'

    def __str__(self):
        return f'{self.user.username} - {self.course_name} ({self.credits} 學分)'
