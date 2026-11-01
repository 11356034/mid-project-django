from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.shortcuts import redirect, render

# 重設後的預設密碼（與 pages/utils.py 建立學生帳號時的預設值一致）
DEFAULT_STUDENT_PASSWORD = 'student123'

# 失敗次數限制：同一個帳號輸入錯誤 5 次，鎖定 10 分鐘（防止亂猜學號與姓名）
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 600


def _norm(text):
    """去除所有空白（含全形空白）並忽略大小寫，避免多打空格造成核對失敗。"""
    return ''.join((text or '').split()).casefold()


def _find_matching_student(username, student_id, name):
    """帳號、學號、姓名三項全部相符才回傳該學生，否則回傳 None。
    教務管理員、教師、停用帳號一律不允許使用本功能。"""
    user = User.objects.filter(username=username).select_related('profile').first()
    if user is None:
        return None
    if not user.is_active or user.is_staff or user.is_superuser or user.username == 'admin':
        return None

    profile = getattr(user, 'profile', None)
    if profile is None or profile.role != 'STUDENT':
        return None
    if not _norm(profile.student_id):
        return None

    if _norm(profile.student_id) != _norm(student_id):
        return None
    if _norm(user.first_name) != _norm(name):
        return None
    return user


def forgot_password(request):
    """忘記密碼：輸入使用者名稱 + 學號 + 姓名，三項都正確就把密碼重設為預設值。"""
    if request.user.is_authenticated:
        return redirect('pages:index')

    context = {'default_password': DEFAULT_STUDENT_PASSWORD}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        student_id = request.POST.get('student_id', '').strip()
        name = request.POST.get('name', '').strip()
        context.update({'username': username, 'student_id': student_id, 'name': name})

        if not (username and student_id and name):
            messages.error(request, '請完整填寫使用者名稱、學號與姓名。')
            return render(request, 'recovery/forgot_password.html', context)

        lock_key = f'pwreset-fail:{username.lower()}'
        if cache.get(lock_key, 0) >= MAX_FAILED_ATTEMPTS:
            messages.error(request, '嘗試次數過多，請 10 分鐘後再試，或洽教務處協助。')
            return render(request, 'recovery/forgot_password.html', context)

        user = _find_matching_student(username, student_id, name)
        if user is None:
            # 不透露是哪一項錯誤，也不透露帳號是否存在
            cache.set(lock_key, cache.get(lock_key, 0) + 1, LOCK_SECONDS)
            messages.error(request, '資料核對失敗，請確認使用者名稱、學號與姓名皆正確。')
            return render(request, 'recovery/forgot_password.html', context)

        # 只更新密碼欄位，不動任何選課、課程或個人檔案資料
        user.set_password(DEFAULT_STUDENT_PASSWORD)
        user.save(update_fields=['password'])
        cache.delete(lock_key)
        context['done'] = True
        context['display_name'] = user.first_name or user.username
        return render(request, 'recovery/forgot_password.html', context)

    return render(request, 'recovery/forgot_password.html', context)
