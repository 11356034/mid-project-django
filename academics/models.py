from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class CompletedCourse(models.Model):
    """學生已完成的課程紀錄；獨立於 Enrollment，避免影響現有選課資料。"""
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
