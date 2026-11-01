from django.contrib import admin
from .models import CompletedCourse


@admin.register(CompletedCourse)
class CompletedCourseAdmin(admin.ModelAdmin):
    list_display = ('course_name', 'user', 'credits', 'category', 'semester', 'grade')
    list_filter = ('category', 'semester')
    search_fields = ('course_name', 'user__username', 'user__first_name')
