from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('credits/', views.credit_progress, name='credits'),
    path('credits/<int:record_id>/delete/', views.delete_completed_course, name='delete_credit'),
    path('teacher/grades/', views.teacher_grades, name='teacher_grades'),
    path('teacher/grades/simulate_date/', views.simulate_date, name='simulate_date'),
]
