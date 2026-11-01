from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CompletedCourseForm
from .models import CompletedCourse

# 可依照學校正式畢業門檻調整；目前先使用示範值。
GRADUATION_CREDITS = 128
REQUIRED_CREDITS = 80
ELECTIVE_CREDITS = 48


@login_required

def credit_progress(request):
    """顯示登入者自己的已完成課程與學分統計。"""
    records = CompletedCourse.objects.filter(user=request.user)

    if request.method == 'POST':
        form = CompletedCourseForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.user = request.user
            record.save()
            messages.success(request, '已新增修課紀錄。')
            return redirect('academics:credits')
    else:
        form = CompletedCourseForm()

    total = records.aggregate(value=Sum('credits'))['value'] or 0
    required = records.filter(category='REQUIRED').aggregate(value=Sum('credits'))['value'] or 0
    elective = records.filter(category='ELECTIVE').aggregate(value=Sum('credits'))['value'] or 0
    percent = min(round(total / GRADUATION_CREDITS * 100), 100) if GRADUATION_CREDITS else 0

    context = {
        'form': form,
        'records': records,
        'total_credits': total,
        'required_credits': required,
        'elective_credits': elective,
        'graduation_credits': GRADUATION_CREDITS,
        'required_target': REQUIRED_CREDITS,
        'elective_target': ELECTIVE_CREDITS,
        'progress_percent': percent,
    }
    return render(request, 'academics/credits.html', context)


@login_required
@require_POST
def delete_completed_course(request, record_id):
    record = get_object_or_404(CompletedCourse, pk=record_id, user=request.user)
    record.delete()
    messages.success(request, '已刪除該筆修課紀錄。')
    return redirect('academics:credits')
