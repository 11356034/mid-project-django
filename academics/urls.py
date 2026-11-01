from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    path('credits/', views.credit_progress, name='credits'),
    path('credits/<int:record_id>/delete/', views.delete_completed_course, name='delete_credit'),
]
