from django import forms
from .models import CompletedCourse


class CompletedCourseForm(forms.ModelForm):
    class Meta:
        model = CompletedCourse
        fields = ['course_name', 'credits', 'category', 'semester', 'grade']
        widgets = {
            'course_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：Python 程式設計'}),
            'credits': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'semester': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：114-1'}),
            'grade': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100, 'placeholder': '可留空'}),
        }
        labels = {
            'course_name': '課程名稱', 'credits': '學分數', 'category': '課程類別',
            'semester': '修課學期', 'grade': '成績（選填）',
        }
