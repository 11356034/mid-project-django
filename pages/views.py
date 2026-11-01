import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.db.models import Q

from django.core.cache import cache

from .models import Course, Enrollment, UserProfile
from .utils import init_demo_data, create_student_account, create_teacher_account

# 登入資安防護常數：連續登入失敗 5 次，鎖定 5 分鐘（300 秒）
LOGIN_MAX_FAILED_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 300

def _get_client_ip(request):
    """獲取客戶端真實 IP 位址（支援反向代理）"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip

# 依據圖片第二張完整時段排程
PERIOD_INFO = [
    {'period': 1, 'time': '08:10 - 09:00', 'name': '第一節'},
    {'period': 2, 'time': '09:10 - 10:00', 'name': '第二節'},
    {'period': 3, 'time': '10:10 - 11:00', 'name': '第三節'},
    {'period': 4, 'time': '11:10 - 12:00', 'name': '第四節'},
    {'period': 5, 'time': '13:30 - 14:20', 'name': '第五節'},
    {'period': 6, 'time': '14:25 - 15:15', 'name': '第六節'},
    {'period': 7, 'time': '15:25 - 16:15', 'name': '第七節'},
    {'period': 8, 'time': '16:20 - 17:10', 'name': '第八節'},
    {'period': 9, 'time': '17:15 - 18:05', 'name': '第九節'},
]

DAYS_INFO = [
    {'day': 1, 'name': '一', 'full_name': '星期一'},
    {'day': 2, 'name': '二', 'full_name': '星期二'},
    {'day': 3, 'name': '三', 'full_name': '星期三'},
    {'day': 4, 'name': '四', 'full_name': '星期四'},
    {'day': 5, 'name': '五', 'full_name': '星期五'},
]

def check_time_conflict(course_a, course_b):
    """檢查兩門課是否有時間衝堂"""
    if course_a.id == course_b.id:
        return False
    if course_a.day_of_week != course_b.day_of_week:
        return False
    return max(course_a.start_period, course_b.start_period) <= min(course_a.end_period, course_b.end_period)


def index(request, tab=None):
    """選課系統首頁 / 課表與維護入口"""
    # 確保基本示範資料存在
    if not User.objects.filter(username__in=['admin', 'student']).exists() or not Course.objects.exists():
        init_demo_data()

    # 未登入者一律強制重導向至 /login/
    if not request.user.is_authenticated:
        return redirect('pages:login')

    is_admin = request.user.is_staff or request.user.username == 'admin'
    user_role = getattr(request.user.profile, 'role', 'STUDENT')
    is_teacher = (user_role == 'TEACHER')
    is_student = not is_admin and not is_teacher
    student_class = getattr(request.user.profile, 'student_class', '資管一甲')

    # 若使用舊式 query string ?tab=...，自動 302 重新導向至乾淨語意化目錄路徑 (Clean Directory URLs)
    query_tab = request.GET.get('tab')
    if query_tab:
        tab_redirect_map = {
            'enrolled': 'pages:enrolled',
            'electives': 'pages:electives',
            'timetable': 'pages:timetable',
            'admin_courses': 'pages:manage_courses',
            'students_roster': 'pages:students_roster',
            'teacher_courses': 'pages:teacher_courses',
        }
        if query_tab in tab_redirect_map:
            return redirect(tab_redirect_map[query_tab])

    if not tab:
        if is_admin:
            active_tab = 'admin_courses'
        elif is_teacher:
            active_tab = 'teacher_courses'
        else:
            active_tab = 'timetable'
    else:
        active_tab = tab

    # 取得所有課程與選課紀錄（含授課教師關聯與修課學生）
    all_courses = Course.objects.all().select_related('teacher_user').prefetch_related('enrollments__user__profile')

    # 學生已選課程
    if is_student:
        user_enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
        enrolled_courses = [e.course for e in user_enrollments]
        enrolled_course_ids = {c.id for c in enrolled_courses}
    else:
        enrolled_courses = []
        enrolled_course_ids = set()

    # 班級課表切換 (資管一甲、資管二甲、資管三甲)
    CLASS_LIST = ['資管一甲', '資管二甲', '資管三甲']
    selected_class = request.GET.get('class_name', '').strip()
    if not selected_class:
        if is_student and student_class in CLASS_LIST:
            selected_class = student_class
        else:
            selected_class = '資管一甲'
    if selected_class not in CLASS_LIST:
        selected_class = '資管一甲'

    # 建立課表網格 [period][day]
    timetable = {p['period']: {d['day']: None for d in DAYS_INFO} for p in PERIOD_INFO}

    if is_student and selected_class == student_class:
        courses_to_plot = enrolled_courses
    else:
        courses_to_plot = [c for c in all_courses if c.target_class == selected_class and c.category == 'REQUIRED']

    for course in courses_to_plot:
        day = course.day_of_week
        start_p = course.start_period
        end_p = course.end_period
        span = end_p - start_p + 1

        if start_p in timetable and day in timetable[start_p]:
            timetable[start_p][day] = {
                'type': 'course',
                'course': course,
                'rowspan': span,
                'is_start': True,
            }
            # 將跨節次的後續格子標記為 occupied
            for p in range(start_p + 1, end_p + 1):
                if p in timetable and day in timetable[p]:
                    timetable[p][day] = {'type': 'occupied'}

    # 學生選修課程清單處理（計算衝堂狀態、選課狀態、班級相符狀態）
    elective_courses_data = []
    for c in all_courses:
        is_enrolled = c.id in enrolled_course_ids
        conflict_with = None
        if not is_enrolled and is_student:
            for ec in enrolled_courses:
                if check_time_conflict(c, ec):
                    conflict_with = ec
                    break

        is_class_match = (c.target_class in ['ALL', student_class])
        elective_courses_data.append({
            'course': c,
            'is_enrolled': is_enrolled,
            'is_open': c.is_open_for_enrollment,
            'conflict_with': conflict_with,
            'is_full': c.current_enrolled_count >= c.max_students,
            'target_class': c.target_class,
            'is_class_match': is_class_match,
        })

    # 學分統計（學生端）
    total_credits = sum(c.credits for c in enrolled_courses)
    required_credits = sum(c.credits for c in enrolled_courses if c.category == 'REQUIRED')
    elective_credits = sum(c.credits for c in enrolled_courses if c.category == 'ELECTIVE')

    # 管理員端統計數據（總課程數、開放選修中課程數）
    total_courses_count = all_courses.count()
    open_courses_count = all_courses.filter(is_open_for_enrollment=True).count()

    # 取得現有所有教師帳號與教師清單
    all_teacher_users = User.objects.filter(profile__role='TEACHER').select_related('profile').order_by('username')
    default_teachers = [
        '黃燕萍', '李俞麟', '唐日新', '林俊杰', '丁慧瑩',
        '謝文欽', '陳秋良', '許佩玉', '顏嬿真', '王嬿惠',
        '葉明貴', '郭怡君', '陳麒文'
    ]
    db_teachers = list(Course.objects.values_list('teacher', flat=True).distinct())
    teacher_user_names = list(all_teacher_users.values_list('first_name', flat=True))
    teachers_list = sorted(list({t.strip() for t in (default_teachers + db_teachers + teacher_user_names) if t and t.strip()}))

    # 教師端：自己開的課程與修課學生清單
    teacher_courses = []
    if is_teacher or is_admin:
        if is_teacher:
            t_courses_query = all_courses.filter(
                Q(teacher_user=request.user) | Q(teacher=request.user.first_name, teacher_user__isnull=True)
            )
        else:
            t_courses_query = all_courses

        for tc in t_courses_query:
            enrolled_stus = []
            for enr in tc.enrollments.all():
                enrolled_stus.append({
                    'user': enr.user,
                    'profile': getattr(enr.user, 'profile', None),
                    'enrolled_at': enr.created_at,
                })
            teacher_courses.append({
                'course': tc,
                'enrolled_students': enrolled_stus,
                'student_count': len(enrolled_stus),
            })

    # 學生名冊與教師名冊（管理員端查看與管理）
    students_list = []
    teachers_admin_list = []
    if is_admin:
        students_query = User.objects.filter(is_staff=False, profile__role='STUDENT').select_related('profile').prefetch_related('enrollments__course').order_by('username')
        for stu in students_query:
            enr_courses = [e.course for e in stu.enrollments.all()]
            req_c = sum(c.credits for c in enr_courses if c.category == 'REQUIRED')
            elec_c = sum(c.credits for c in enr_courses if c.category == 'ELECTIVE')
            students_list.append({
                'user': stu,
                'profile': getattr(stu, 'profile', None),
                'total_credits': req_c + elec_c,
                'required_credits': req_c,
                'elective_credits': elec_c,
                'course_count': len(enr_courses),
                'enrolled_courses': enr_courses,
            })

        for tu in all_teacher_users:
            taught = [c for c in all_courses if c.teacher_user_id == tu.id or (c.teacher == tu.first_name and c.teacher_user_id is None)]
            teachers_admin_list.append({
                'user': tu,
                'profile': getattr(tu, 'profile', None),
                'taught_courses': taught,
                'courses_count': len(taught),
            })

    context = {
        'is_admin': is_admin,
        'is_teacher': is_teacher,
        'is_student': is_student,
        'student_class': student_class,
        'class_list': CLASS_LIST,
        'selected_class': selected_class,
        'period_info': PERIOD_INFO,
        'days_info': DAYS_INFO,
        'timetable': timetable,
        'all_courses': all_courses,
        'enrolled_courses': enrolled_courses,
        'elective_courses_data': elective_courses_data,
        'teacher_courses': teacher_courses,
        'total_credits': total_credits,
        'required_credits': required_credits,
        'elective_credits': elective_credits,
        'course_count': len(enrolled_courses),
        'total_courses_count': total_courses_count,
        'open_courses_count': open_courses_count,
        'teachers_list': teachers_list,
        'all_teacher_users': all_teacher_users,
        'teachers_admin_list': teachers_admin_list,
        'students_list': students_list,
        'tab': active_tab,
    }
    return render(request, 'index.html', context)


def login_view(request):
    """使用者登入（具備防暴力破解頻率限制與資訊安全防護）"""
    # 若已登入直接轉至首頁
    if request.user.is_authenticated:
        return redirect('pages:index')

    if request.method == 'POST':
        client_ip = _get_client_ip(request)
        uname = request.POST.get('username', '').strip()
        pwd = request.POST.get('password', '').strip()

        # 防暴力破解：鎖定鍵（同時針對 IP 與帳號進行頻率限制）
        ip_lock_key = f'login_fail_ip:{client_ip}'
        user_lock_key = f'login_fail_user:{uname.lower()}' if uname else None

        ip_attempts = cache.get(ip_lock_key, 0)
        user_attempts = cache.get(user_lock_key, 0) if user_lock_key else 0

        if ip_attempts >= LOGIN_MAX_FAILED_ATTEMPTS or user_attempts >= LOGIN_MAX_FAILED_ATTEMPTS:
            messages.error(request, "登入失敗次數過多，為維護帳號資訊安全，系統已暫時限制登入，請於 5 分鐘後再試。")
            return render(request, 'login.html')

        if not uname or not pwd:
            messages.error(request, "請輸入使用者帳號與密碼。")
            return render(request, 'login.html')

        user = authenticate(request, username=uname, password=pwd)
        if user and user.is_active:
            # 登入成功：清除失敗次數計數器
            cache.delete(ip_lock_key)
            if user_lock_key:
                cache.delete(user_lock_key)

            login(request, user)
            display_name = user.first_name if user.first_name else user.username
            messages.success(request, f"登入成功！歡迎 {display_name} 進入系統。")
            if user.is_staff or user.username == 'admin':
                return redirect('pages:manage_courses')
            elif getattr(user.profile, 'role', '') == 'TEACHER':
                return redirect('pages:teacher_courses')
            else:
                return redirect('pages:timetable')
        else:
            # 登入失敗：累計失敗次數
            cache.set(ip_lock_key, ip_attempts + 1, LOGIN_LOCK_SECONDS)
            if user_lock_key:
                cache.set(user_lock_key, user_attempts + 1, LOGIN_LOCK_SECONDS)

            messages.error(request, "帳號或密碼輸入錯誤，請重新確認後再試。")

    return render(request, 'login.html')


def logout_view(request):
    """登出帳號並返回登入頁"""
    logout(request)
    messages.info(request, "您已成功登出系統。")
    return redirect('pages:login')


@login_required
@require_POST
def enroll_course(request, course_id):
    """學生加選額外課程"""
    course = get_object_or_404(Course, id=course_id)

    # 檢查身分：僅學生可自主選課
    user_role = getattr(request.user.profile, 'role', 'STUDENT')
    if user_role == 'TEACHER' or request.user.is_staff:
        messages.error(request, "僅學生身分可進行自主選修課程！")
        return redirect('pages:electives')

    # 檢查是否開放選修
    if not course.is_open_for_enrollment:
        messages.error(request, f"選課失敗：【{course.name}】目前授課教師或教務端未開放學生選修！")
        return redirect('pages:electives')

    # 檢查班級限制：學生只能選自己班級（或 ALL 全系開放）的課程
    user_class = getattr(request.user.profile, 'student_class', '資管一甲')
    if course.target_class not in ['ALL', user_class]:
        messages.error(request, f"選課失敗：【{course.name}】為【{course.target_class}】限定選修課程，您所屬班級為【{user_class}】無法加選！")
        return redirect('pages:electives')

    # 檢查是否已經選修
    if Enrollment.objects.filter(user=request.user, course=course).exists():
        messages.warning(request, f"您已經選修過【{course.name}】囉！")
        return redirect('pages:electives')

    # 檢查人數上限
    if course.current_enrolled_count >= course.max_students:
        messages.error(request, f"選課失敗：【{course.name}】修課人數已額滿（上限 {course.max_students} 人）！")
        return redirect('pages:electives')

    # 檢查時間衝突 (衝堂)
    current_enrolled = [e.course for e in Enrollment.objects.filter(user=request.user).select_related('course')]
    for ec in current_enrolled:
        if check_time_conflict(course, ec):
            messages.error(
                request,
                f"選課失敗：【{course.name}】（{course.period_display}）與您已選的【{ec.name}】（{ec.period_display}）時段衝突！"
            )
            return redirect('pages:electives')

    # 建立選課紀錄
    Enrollment.objects.create(user=request.user, course=course)
    messages.success(request, f"成功加選【{course.name}】（{course.credits} 學分），已排入您的週課表！")
    return redirect('pages:timetable')


@login_required
@require_POST
def drop_course(request, course_id):
    """學生退選課程"""
    course = get_object_or_404(Course, id=course_id)

    # 限制必修課不可由學生自行退選
    if course.category == 'REQUIRED':
        messages.error(request, f"退選失敗：【{course.name}】為資管一甲班級必修課程，學生端無法退選！")
        return redirect('pages:timetable')

    enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
    if enrollment:
        enrollment.delete()
        messages.success(request, f"已成功退選【{course.name}】（已釋出 {course.credits} 學分）。")
    else:
        messages.warning(request, f"您尚未選修【{course.name}】。")

    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('pages:timetable')


@login_required
@require_POST
def toggle_course_status(request, course_id):
    """管理員或授課教師切換課程是否開放選修"""
    course = get_object_or_404(Course, id=course_id)
    is_admin = request.user.is_staff or request.user.username == 'admin'
    user_role = getattr(request.user.profile, 'role', 'STUDENT')
    is_course_teacher = (user_role == 'TEACHER') and (
        course.teacher_user == request.user or (course.teacher == request.user.first_name and course.teacher_user is None)
    )

    if not (is_admin or is_course_teacher):
        return HttpResponseForbidden("僅教務管理員或該課程之授課教師可調整課程開放狀態。")

    course.is_open_for_enrollment = not course.is_open_for_enrollment
    course.save()

    status_str = "【開放學生選修】" if course.is_open_for_enrollment else "【未開放選修】"
    messages.success(request, f"已更新課程【{course.name}】狀態為：{status_str}")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url:
        return redirect(next_url)
    if is_course_teacher and not is_admin:
        return redirect('pages:teacher_courses')
    return redirect('pages:manage_courses')


@login_required
@require_POST
def add_course(request):
    """管理員或授課教師新增課程"""
    is_admin = request.user.is_staff or request.user.username == 'admin'
    user_role = getattr(request.user.profile, 'role', 'STUDENT')
    is_teacher = (user_role == 'TEACHER')

    if not (is_admin or is_teacher):
        return HttpResponseForbidden("僅教務管理員或授課教師可新增課程。")

    code = request.POST.get('code', '').strip().upper()
    name = request.POST.get('name', '').strip()
    next_url = request.POST.get('next', '').strip()
    default_redirect = 'pages:teacher_courses' if (is_teacher and not is_admin) else 'pages:manage_courses'

    target_class = request.POST.get('target_class', '資管一甲').strip()
    if target_class not in ['資管一甲', '資管二甲', '資管三甲', 'ALL']:
        target_class = '資管一甲'

    classroom = request.POST.get('classroom', '').strip()
    credits = int(request.POST.get('credits', 2))
    category = request.POST.get('category', 'ELECTIVE')
    day_of_week = int(request.POST.get('day_of_week', 1))
    start_period = int(request.POST.get('start_period', 1))
    end_period = int(request.POST.get('end_period', 1))
    is_open = request.POST.get('is_open_for_enrollment') == 'on'
    max_students = int(request.POST.get('max_students', 50))
    description = request.POST.get('description', '').strip()
    color_tag = request.POST.get('color_tag', 'indigo')

    if not code or not name:
        messages.error(request, "新增失敗：課程代碼與名稱為必填項目！")
        return redirect(next_url or default_redirect)

    if end_period < start_period:
        messages.error(request, "新增失敗：結束節次不能小於開始節次！")
        return redirect(next_url or default_redirect)

    if Course.objects.filter(code=code).exists():
        messages.error(request, f"新增失敗：課程代碼【{code}】已存在！")
        return redirect(next_url or default_redirect)

    if is_teacher and not is_admin:
        teacher_user = request.user
        teacher = request.user.first_name or request.user.username
    else:
        teacher = request.POST.get('teacher', '').strip()
        teacher_user_id = request.POST.get('teacher_user_id', '').strip()
        teacher_user = None
        if teacher_user_id:
            teacher_user = User.objects.filter(id=teacher_user_id).first()
            if teacher_user:
                teacher = teacher_user.first_name or teacher_user.username
        elif teacher:
            teacher_user = User.objects.filter(first_name=teacher, profile__role='TEACHER').first()

    Course.objects.create(
        code=code,
        name=name,
        teacher=teacher or "未指定",
        teacher_user=teacher_user,
        target_class=target_class,
        classroom=classroom or "未指定",
        credits=credits,
        category=category,
        day_of_week=day_of_week,
        start_period=start_period,
        end_period=end_period,
        is_open_for_enrollment=is_open,
        max_students=max_students,
        description=description,
        color_tag=color_tag
    )

    messages.success(
        request,
        f"成功新增課程：【{name}】（代碼: {code}，授課教師: {teacher}，開課班級: {target_class}）！課程資訊已即時同步至全體學生選課專區及教務管理總表。"
    )
    return redirect(next_url or default_redirect)


@login_required
@require_POST
def edit_course(request, course_id):
    """管理員或授課教師編輯課程內容與節次"""
    course = get_object_or_404(Course, id=course_id)
    is_admin = request.user.is_staff or request.user.username == 'admin'
    user_role = getattr(request.user.profile, 'role', 'STUDENT')
    is_teacher_owner = (user_role == 'TEACHER') and (
        course.teacher_user == request.user or (course.teacher == request.user.first_name and course.teacher_user is None)
    )

    if not (is_admin or is_teacher_owner):
        return HttpResponseForbidden("僅教務管理員或該課程之授課教師可編輯課程。")

    name = request.POST.get('name', '').strip()
    next_url = request.POST.get('next', '').strip()
    default_redirect = 'pages:teacher_courses' if (is_teacher_owner and not is_admin) else 'pages:manage_courses'

    target_class = request.POST.get('target_class', course.target_class).strip()
    if target_class not in ['資管一甲', '資管二甲', '資管三甲', 'ALL']:
        target_class = '資管一甲'

    classroom = request.POST.get('classroom', '').strip()
    credits = int(request.POST.get('credits', course.credits))
    category = request.POST.get('category', course.category)
    day_of_week = int(request.POST.get('day_of_week', course.day_of_week))
    start_period = int(request.POST.get('start_period', course.start_period))
    end_period = int(request.POST.get('end_period', course.end_period))
    is_open = request.POST.get('is_open_for_enrollment') == 'on'
    max_students = int(request.POST.get('max_students', course.max_students))
    description = request.POST.get('description', '').strip()
    color_tag = request.POST.get('color_tag', course.color_tag)

    if not name:
        messages.error(request, "編輯失敗：課程名稱不能為空！")
        return redirect(next_url or default_redirect)

    if end_period < start_period:
        messages.error(request, "編輯失敗：結束節次不能小於開始節次！")
        return redirect(next_url or default_redirect)

    if is_admin:
        teacher = request.POST.get('teacher', '').strip()
        teacher_user_id = request.POST.get('teacher_user_id', '').strip()
        if teacher_user_id:
            teacher_user = User.objects.filter(id=teacher_user_id).first()
            if teacher_user:
                course.teacher_user = teacher_user
                course.teacher = teacher_user.first_name or teacher_user.username
        elif 'teacher_user_id' in request.POST and not teacher_user_id:
            course.teacher_user = None
            if teacher:
                course.teacher = teacher
        else:
            if teacher:
                course.teacher = teacher
                if not course.teacher_user:
                    course.teacher_user = User.objects.filter(first_name=teacher, profile__role='TEACHER').first()

    course.name = name
    course.target_class = target_class
    course.classroom = classroom or course.classroom
    course.credits = credits
    course.category = category
    course.day_of_week = day_of_week
    course.start_period = start_period
    course.end_period = end_period
    course.is_open_for_enrollment = is_open
    course.max_students = max_students
    course.description = description
    course.color_tag = color_tag
    course.save()

    messages.success(request, f"已成功更新課程【{course.name}】的資料與時段！")
    return redirect(next_url or default_redirect)


@login_required
@require_POST
def delete_course(request, course_id):
    """管理員或授課教師刪除課程"""
    course = get_object_or_404(Course, id=course_id)
    is_admin = request.user.is_staff or request.user.username == 'admin'
    user_role = getattr(request.user.profile, 'role', 'STUDENT')
    is_teacher_owner = (user_role == 'TEACHER') and (
        course.teacher_user == request.user or (course.teacher == request.user.first_name and course.teacher_user is None)
    )

    if not (is_admin or is_teacher_owner):
        return HttpResponseForbidden("僅教務管理員或該課程之授課教師可刪除課程。")

    cname = course.name
    course.delete()
    messages.success(request, f"課程【{cname}】已成功刪除。")
    if is_admin and not (is_teacher_owner and request.POST.get('from_teacher')):
        return redirect('pages:manage_courses')
    return redirect('pages:teacher_courses')


@login_required
@require_POST
def reset_database(request):
    """一鍵重設示範資料為資管一甲標準課表"""
    if not (request.user.is_staff or request.user.username == 'admin'):
        return HttpResponseForbidden("僅教務管理員可重置系統資料。")

    init_demo_data()
    messages.success(request, "已成功重置為資管一甲標準課表！")
    return redirect('pages:manage_courses')


@login_required
def profile_settings(request):
    """使用者個人設定：修改姓名、上傳頭像、重設密碼（需輸入兩次確認）"""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    is_admin = user.is_staff or user.username == 'admin'

    if request.method == 'POST':
        name = request.POST.get('first_name', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        avatar_file = request.FILES.get('avatar')

        # 1. 姓名與性別更新
        if name:
            user.first_name = name
            user.save()

        gender = request.POST.get('gender', '').strip()
        if gender in ['M', 'F', 'O']:
            profile.gender = gender
            profile.save()

        # 2. 頭像更新
        if avatar_file:
            profile.avatar = avatar_file
            profile.save()

        # 3. 密碼更新 (若有填寫任一欄位)
        password_changed = False
        if new_password or confirm_password:
            if not new_password:
                messages.error(request, "設定失敗：請輸入新密碼！")
                return render(request, 'profile_settings.html', {'profile': profile, 'is_admin': is_admin})
            if new_password != confirm_password:
                messages.error(request, "設定失敗：兩次輸入的密碼不相符，請重新確認！")
                return render(request, 'profile_settings.html', {'profile': profile, 'is_admin': is_admin})
            if len(new_password) < 4:
                messages.error(request, "設定失敗：新密碼長度至少需 4 個字元以上！")
                return render(request, 'profile_settings.html', {'profile': profile, 'is_admin': is_admin})

            user.set_password(new_password)
            user.save()
            update_session_auth_hash(request, user)
            password_changed = True

        if password_changed:
            messages.success(request, "個人資料與登入密碼已成功更新！")
        else:
            messages.success(request, "個人設定已成功更新！")

        return redirect('pages:profile_settings')

    return render(request, 'profile_settings.html', {'profile': profile, 'is_admin': is_admin})


@login_required
@require_POST
def add_student(request):
    """教務管理員新增學生帳號（可指定資管一甲至三甲）"""
    if not (request.user.is_staff or request.user.username == 'admin'):
        return HttpResponseForbidden("僅教務管理員可新增學生帳號。")

    username = request.POST.get('username', '').strip()
    name = request.POST.get('name', '').strip()
    student_class = request.POST.get('student_class', '資管一甲').strip()
    if student_class not in ['資管一甲', '資管二甲', '資管三甲']:
        student_class = '資管一甲'
    gender = request.POST.get('gender', 'M').strip()
    if gender not in ['M', 'F', 'O']:
        gender = 'M'
    password = request.POST.get('password', '').strip() or 'student123'
    student_id = request.POST.get('student_id', '').strip() or username

    if not username or not name:
        messages.error(request, "新增失敗：學生帳號與姓名為必填項目！")
        return redirect('pages:students_roster')

    if User.objects.filter(username=username).exists():
        messages.error(request, f"新增失敗：帳號【{username}】已被使用，請更換帳號或學號！")
        return redirect('pages:students_roster')

    student_user = create_student_account(
        username=username,
        name=name,
        gender=gender,
        password=password,
        student_id=student_id,
        student_class=student_class
    )

    gender_display = student_user.profile.get_gender_display()
    messages.success(
        request,
        f"成功新增學生：【{name}】（帳號: {username}，班級: {student_class}，性別: {gender_display}）！已完成帳號與必修課表建立。"
    )
    return redirect('pages:students_roster')


@login_required
@require_POST
def edit_student_id(request, user_id):
    """教務管理員修改學生學號與所屬班級"""
    if not (request.user.is_staff or request.user.username == 'admin'):
        return HttpResponseForbidden("僅教務管理員可修改學生資料。")

    target_user = get_object_or_404(User, id=user_id)
    new_student_id = request.POST.get('student_id', '').strip()
    new_student_class = request.POST.get('student_class', '').strip()

    if not new_student_id:
        messages.error(request, "修改失敗：學生學號不可為空白！")
        return redirect('pages:students_roster')

    if len(new_student_id) > 20:
        messages.error(request, "修改失敗：學生學號長度不得超過 20 個字元！")
        return redirect('pages:students_roster')

    # 檢查學號是否與其他學生重複
    if UserProfile.objects.filter(student_id=new_student_id).exclude(user=target_user).exists():
        messages.error(request, f"修改失敗：學號【{new_student_id}】已被其他學生使用，請確認後重新輸入！")
        return redirect('pages:students_roster')

    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.student_id = new_student_id
    if new_student_class in ['資管一甲', '資管二甲', '資管三甲']:
        profile.student_class = new_student_class
    profile.save()

    student_name = target_user.first_name if target_user.first_name else target_user.username
    messages.success(
        request,
        f"成功將學生【{student_name}】（帳號: {target_user.username}）的資料更新為：學號【{new_student_id}】、班級【{profile.student_class}】！"
    )
    return redirect('pages:students_roster')


@login_required
@require_POST
def add_teacher(request):
    """教務管理員新增教師帳號"""
    if not (request.user.is_staff or request.user.username == 'admin'):
        return HttpResponseForbidden("僅教務管理員可新增教師帳號。")

    username = request.POST.get('username', '').strip()
    name = request.POST.get('name', '').strip()
    gender = request.POST.get('gender', 'M').strip()
    if gender not in ['M', 'F', 'O']:
        gender = 'M'
    password = request.POST.get('password', '').strip() or 'teacher123'

    if not username or not name:
        messages.error(request, "新增失敗：教師帳號與姓名為必填項目！")
        return redirect('pages:students_roster')

    if User.objects.filter(username=username).exists():
        messages.error(request, f"新增失敗：帳號【{username}】已被使用，請更換帳號！")
        return redirect('pages:students_roster')

    teacher_user = create_teacher_account(
        username=username,
        name=name,
        gender=gender,
        password=password
    )

    # 自動關聯現有由該教師授課之課程
    Course.objects.filter(teacher=name, teacher_user__isnull=True).update(teacher_user=teacher_user)

    messages.success(
        request,
        f"成功新增教師：【{name}】（帳號: {username}）！已可指派授課課程或由教師登入系統管理開課。"
    )
    return redirect('pages:students_roster')


@login_required
@require_POST
def delete_user(request):
    """教務管理員刪除帳號（需指定原因：已退學、已畢業、其他:請說明）"""
    if not (request.user.is_staff or request.user.username == 'admin'):
        return HttpResponseForbidden("僅教務管理員可刪除帳號。")

    user_id = request.POST.get('user_id', '').strip()
    reason_type = request.POST.get('reason_type', '').strip()
    reason_other = request.POST.get('reason_other', '').strip()

    if not user_id:
        messages.error(request, "刪除失敗：未指定欲刪除之帳號！")
        return redirect('pages:students_roster')

    target_user = get_object_or_404(User, id=user_id)

    # 禁止刪除自身、admin 或具管理員權限者
    if target_user.id == request.user.id or target_user.username == 'admin' or target_user.is_superuser or target_user.is_staff:
        messages.error(request, "刪除失敗：無法刪除管理員帳號！")
        return redirect('pages:students_roster')

    target_role = "學生"
    if hasattr(target_user, 'profile') and target_user.profile.role == 'TEACHER':
        target_role = "教師"

    # 原因驗證（學生：已退學、已畢業；教師：退休、離職；或皆可選其他）
    valid_reasons = ['已退學', '已畢業', '退休', '離職', '其他']
    if reason_type not in valid_reasons:
        messages.error(request, "刪除失敗：請選擇合法的刪除原因（學生：已退學、已畢業；教師：退休、離職；或其他）！")
        return redirect('pages:students_roster')

    if reason_type == '其他' and not reason_other:
        messages.error(request, "刪除失敗：若選擇「其他」，請填寫詳細說明！")
        return redirect('pages:students_roster')

    reason_str = f"其他（{reason_other}）" if reason_type == '其他' else reason_type
    target_name = target_user.first_name or target_user.username
    target_username = target_user.username

    # 若為教師，解除其開課綁定，避免刪除課程本身
    Course.objects.filter(teacher_user=target_user).update(teacher_user=None)

    # 執行刪除
    target_user.delete()

    messages.success(
        request,
        f"已成功刪除{target_role}帳號【{target_name}】（帳號: {target_username}），原因：{reason_str}。"
    )
    return redirect('pages:students_roster')



