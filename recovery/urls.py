from django.urls import path
from . import views

app_name = 'recovery'

urlpatterns = [
    path('forgot-password/', views.forgot_password, name='forgot_password'),
]
