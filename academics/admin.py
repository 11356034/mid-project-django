from django.contrib import admin
from .models import CompletedCourse, CourseGradingPolicy, StudentGrade

admin.site.register(CompletedCourse)
admin.site.register(CourseGradingPolicy)
admin.site.register(StudentGrade)
