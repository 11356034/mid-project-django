import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from pages.models import Course, Enrollment, UserProfile
from .models import CourseGradingPolicy, StudentGrade
from .gpa import calc_gpa, score_to_letter_gp

# 學校正式畢業學分門檻
GRADUATION_CREDITS = 128
REQUIRED_TARGET = 80
ELECTIVE_TARGET = 48


def get_current_date(request=None):
    """
    取得判定日期。
    若 session 或 GET 帶有 simulated_date，允許進行日期模擬測試（供測試 11/1 未開放、11/6 期中開放、1/8 期末開放效果）。
    """
    if request:
        sim = request.GET.get('simulated_date') or request.session.get('simulated_date')
        if sim:
            if sim == 'reset':
                if 'simulated_date' in request.session:
                    del request.session['simulated_date']
            else:
                try:
                    parts = [int(p) for p in sim.split('-')]
                    d = datetime.date(parts[0], parts[1], parts[2])
                    request.session['simulated_date'] = sim
                    return d
                except Exception:
                    pass
    return datetime.date.today()


def is_midterm_entry_open(today=None):
    """
    期中成績只能在期中後填寫。
    期中時間：每年 11/6 號後和 11/23 號後（皆含當天）。
    """
    if today is None:
        today = datetime.date.today()
    m, d = today.month, today.day

    # 每年 11/6（含）或 11/23（含）起至學期結束
    if (m == 11 and d >= 6) or (m == 12) or (m == 1 and d < 8):
        return True
    if (m == 11 and d >= 23):
        return True
    # 第二學期相應期中週（如 4/23 起）
    if (m == 4 and d >= 23) or (m == 5) or (m == 6 and d < 29):
        return True
    return False


def is_final_entry_open(today=None):
    """
    期末成績只能在期末後填寫。
    期末時間：每年 1/8 後和 6/29 號後（皆含當天）。
    """
    if today is None:
        today = datetime.date.today()
    m, d = today.month, today.day

    # 第一學期期末：每年 1/8（含）起
    if (m == 1 and d >= 8) or (m == 2):
        return True
    # 第二學期期末：每年 6/29（含）起
    if (m == 6 and d >= 29) or (m == 7) or (m == 8):
        return True
    return False


@login_required
def credit_progress(request):
    """
    學生「學分&成績」頁面（當前學期學分與成績總表）：
    呈現當前學期總修讀學分、已過關學分、必選修分配與各科目平時/小考/期中期末考成績。
    """
    user_role = getattr(request.user.profile, 'role', 'STUDENT')

    if request.method == 'POST':
        messages.error(request, '學分與成績已全面對接任課教師評分系統，無法由學生手動新增或修改。')
        return redirect('academics:credits')

    # 取得登入學生當前學期所有已選修之課程紀錄
    enrollments = Enrollment.objects.filter(user=request.user).select_related('course').order_by('course__category', 'course__code')

    course_items = []
    total_enrolled_credits = 0
    passed_credits = 0
    required_enrolled = 0
    required_passed = 0
    elective_enrolled = 0
    elective_passed = 0
    in_progress_credits = 0
    required_count = 0
    elective_count = 0

    gpa_items = []

    for enr in enrollments:
        c = enr.course
        grade_obj, _ = StudentGrade.objects.get_or_create(user=request.user, course=c)
        reg_score = grade_obj.get_regular_score()
        tot_score = grade_obj.get_total_score()
        passed = grade_obj.is_passed

        total_enrolled_credits += c.credits
        if c.category == 'REQUIRED':
            required_enrolled += c.credits
            required_count += 1
            if passed is True:
                required_passed += c.credits
        else:
            elective_enrolled += c.credits
            elective_count += 1
            if passed is True:
                elective_passed += c.credits

        if passed is True:
            earned = c.credits
            passed_credits += earned
        else:
            earned = 0
            if passed is None:
                in_progress_credits += c.credits

        policy = getattr(c, 'grading_policy', None)

        # 只有已評定（及格或不及格）的課程才納入 GPA，修讀中不計
        letter, gp = score_to_letter_gp(tot_score) if passed is not None else (None, None)
        if passed is not None:
            gpa_items.append((tot_score, c.credits))

        course_items.append({
            'letter': letter,
            'gp': gp,
            'course': c,
            'grade': grade_obj,
            'policy': policy,
            'regular_score': reg_score,
            'attendance_score': grade_obj.attendance_score,
            'attitude_score': grade_obj.attitude_score,
            'assignment_score': grade_obj.assignment_score,
            'quiz_score': grade_obj.quiz_score,
            'midterm_score': grade_obj.midterm_score,
            'final_score': grade_obj.final_score,
            'total_score': tot_score,
            'is_passed': passed,
            'status_display': grade_obj.status_display,
            'earned_credits': earned,
        })

    percent = min(round(passed_credits / total_enrolled_credits * 100), 100) if total_enrolled_credits else 0

    context = {
        'courses': course_items,
        'semester_name': '114 學年度 第 1 學期',
        'total_enrolled_credits': total_enrolled_credits,
        'passed_credits': passed_credits,
        'required_enrolled_credits': required_enrolled,
        'required_passed_credits': required_passed,
        'elective_enrolled_credits': elective_enrolled,
        'elective_passed_credits': elective_passed,
        'required_course_count': required_count,
        'elective_course_count': elective_count,
        'in_progress_credits': in_progress_credits,
        'progress_percent': percent,
        'gpa': calc_gpa(gpa_items),
        'gpa_course_count': len(gpa_items),
        'user_role': user_role,
        # 相容歷史變數名稱
        'total_credits': passed_credits,
        'required_credits': required_passed,
        'elective_credits': elective_passed,
    }
    return render(request, 'academics/credits.html', context)


@login_required
@require_POST
def delete_completed_course(request, record_id):
    """舊版刪除接口；現行系統已停用學生自填刪除功能"""
    messages.error(request, '正式成績由任課教師評定，學生無權限刪除修課成績紀錄。')
    return redirect('academics:credits')


@login_required
def teacher_grades(request):
    """
    授課教師登記學生成績與配分管理：
    1. 選擇自己開的課程後，選擇班級（如資管一甲至三甲或全部）。
    2. 平時成績（50%）由老師自己分配百分比（點名、上課態度、課堂作業、小考）。
    3. 考試成績（50%）分為期中考 25%、期末考 25%。
    4. 期中成績僅於每年 11/6 與 11/23 起開放填寫；期末成績僅於每年 1/8 與 6/29 起開放填寫。
    5. 自動計算平時成績總分、期中期末加權分、總成績與過關（>= 60 分）判定。
    """
    is_admin = request.user.is_staff or request.user.username == 'admin'
    user_role = getattr(request.user.profile, 'role', '')
    if not (is_admin or user_role == 'TEACHER'):
        return HttpResponseForbidden("僅授課教師與教務處管理員可登記學生成績。")

    # 取得當前教師所有開課清單
    if is_admin:
        taught_courses = Course.objects.all().order_by('code')
    else:
        taught_courses = Course.objects.filter(
            Q(teacher_user=request.user) | Q(teacher=request.user.first_name, teacher_user__isnull=True)
        ).order_by('code')

    if not taught_courses.exists():
        messages.warning(request, "目前尚無您開設的授課課程，請先至開課管理新增課程。")
        return redirect('pages:teacher_courses')

    # 選擇目前要評分的課程
    course_id = request.GET.get('course_id') or request.POST.get('course_id')
    selected_course = None
    if course_id:
        try:
            selected_course = taught_courses.get(id=course_id)
        except Course.DoesNotExist:
            selected_course = taught_courses.first()
    else:
        selected_course = taught_courses.first()

    # 取得或初始化平時成績配分
    policy, _ = CourseGradingPolicy.objects.get_or_create(course=selected_course)

    # 取得該課程修課學生所屬的所有班級選項
    all_enrollments = Enrollment.objects.filter(course=selected_course).select_related('user', 'user__profile').order_by('user__username')
    enrolled_classes = sorted(list(set(
        e.user.profile.student_class for e in all_enrollments
        if getattr(e.user, 'profile', None) and e.user.profile.student_class
    )))
    if not enrolled_classes:
        enrolled_classes = ['資管一甲', '資管二甲', '資管三甲']

    selected_class = request.GET.get('student_class') or request.POST.get('student_class') or 'ALL'

    # 依選擇之班級篩選學生
    if selected_class != 'ALL':
        target_enrollments = [e for e in all_enrollments if getattr(e.user, 'profile', None) and e.user.profile.student_class == selected_class]
    else:
        target_enrollments = list(all_enrollments)

    # 日期檢查
    current_date = get_current_date(request)
    midterm_open = is_midterm_entry_open(current_date)
    final_open = is_final_entry_open(current_date)

    # 處理教師儲存表單
    if request.method == 'POST':
        action = request.POST.get('action', 'save_all')

        # 1. 儲存平時成績配分權重
        try:
            w_att = int(request.POST.get('attendance_weight', policy.attendance_weight))
            w_atti = int(request.POST.get('attitude_weight', policy.attitude_weight))
            w_asg = int(request.POST.get('assignment_weight', policy.assignment_weight))
            w_qz = int(request.POST.get('quiz_weight', policy.quiz_weight))
        except (ValueError, TypeError):
            w_att, w_atti, w_asg, w_qz = 25, 25, 25, 25

        weight_sum = w_att + w_atti + w_asg + w_qz
        if weight_sum != 100:
            messages.warning(request, f"平時成績配分比例加總應為 100%（目前加總為 {weight_sum}%），系統已自動依權重比例分配計算。")

        policy.attendance_weight = max(0, min(100, w_att))
        policy.attitude_weight = max(0, min(100, w_atti))
        policy.assignment_weight = max(0, min(100, w_asg))
        policy.quiz_weight = max(0, min(100, w_qz))
        policy.save()

        # 2. 儲存每位修課學生成績
        date_warning = []
        updated_count = 0

        for enr in target_enrollments:
            stu = enr.user
            grade_obj, _ = StudentGrade.objects.get_or_create(user=stu, course=selected_course)

            # 解析浮點數輔助函數
            def _parse_score(val_str):
                if val_str is None:
                    return None
                val_str = val_str.strip()
                if val_str == '':
                    return None
                try:
                    s = float(val_str)
                    return max(0.0, min(100.0, round(s, 1)))
                except ValueError:
                    return None

            # 平時成績（隨時開放填寫）
            grade_obj.attendance_score = _parse_score(request.POST.get(f'attendance_{grade_obj.id}'))
            grade_obj.attitude_score = _parse_score(request.POST.get(f'attitude_{grade_obj.id}'))
            grade_obj.assignment_score = _parse_score(request.POST.get(f'assignment_{grade_obj.id}'))
            grade_obj.quiz_score = _parse_score(request.POST.get(f'quiz_{grade_obj.id}'))

            # 期中考成績（僅於期中開放期間允許新填寫或變更）
            mid_input = _parse_score(request.POST.get(f'midterm_{grade_obj.id}'))
            if mid_input is not None and mid_input != grade_obj.midterm_score:
                if midterm_open:
                    grade_obj.midterm_score = mid_input
                else:
                    date_warning.append("期中考")

            # 期末考成績（僅於期末開放期間允許新填寫或變更）
            fin_input = _parse_score(request.POST.get(f'final_{grade_obj.id}'))
            if fin_input is not None and fin_input != grade_obj.final_score:
                if final_open:
                    grade_obj.final_score = fin_input
                else:
                    date_warning.append("期末考")

            grade_obj.save()
            updated_count += 1

        if date_warning:
            if "期中考" in date_warning and not midterm_open:
                messages.error(request, "【期中成績未開放】期中成績僅於每年 11/6 與 11/23 起（含當天）開放填寫，已略過期中成績變更。")
            if "期末考" in date_warning and not final_open:
                messages.error(request, "【期末成績未開放】期末成績僅於每年 1/8 與 6/29 起（含當天）開放填寫，已略過期末成績變更。")

        class_text = f"（班級：{selected_class}）" if selected_class != 'ALL' else "（全體班級）"
        messages.success(request, f"成功儲存【{selected_course.name}】{class_text} 共 {updated_count} 位學生的成績與配分！")
        return redirect(f"{request.path}?course_id={selected_course.id}&student_class={selected_class}")

    # 組合學生資料與即時成績
    students_data = []
    passed_count = 0
    failed_count = 0
    in_progress_count = 0

    for enr in target_enrollments:
        stu = enr.user
        grade_obj, _ = StudentGrade.objects.get_or_create(user=stu, course=selected_course)
        reg_score = grade_obj.get_regular_score()
        tot_score = grade_obj.get_total_score()
        passed = grade_obj.is_passed

        if passed is True:
            passed_count += 1
        elif passed is False:
            failed_count += 1
        else:
            in_progress_count += 1

        students_data.append({
            'enrollment': enr,
            'student': stu,
            'profile': getattr(stu, 'profile', None),
            'grade': grade_obj,
            'regular_score': reg_score,
            'total_score': tot_score,
            'is_passed': passed,
            'status_display': grade_obj.status_display,
        })

    context = {
        'taught_courses': taught_courses,
        'selected_course': selected_course,
        'policy': policy,
        'enrolled_classes': enrolled_classes,
        'selected_class': selected_class,
        'students_data': students_data,
        'student_count': len(students_data),
        'passed_count': passed_count,
        'failed_count': failed_count,
        'in_progress_count': in_progress_count,
        'current_date': current_date,
        'simulated_date_str': request.session.get('simulated_date', ''),
        'midterm_open': midterm_open,
        'final_open': final_open,
    }
    return render(request, 'academics/teacher_grades.html', context)


@login_required
def simulate_date(request):
    """供評分或功能展示時模擬特定日期（例如 11/6 期中開放或 1/8 期末開放）"""
    date_val = request.GET.get('date', '').strip()
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/academics/teacher/grades/'
    if date_val == 'reset':
        if 'simulated_date' in request.session:
            del request.session['simulated_date']
        messages.info(request, "已重設為系統真實日期。")
    elif date_val:
        request.session['simulated_date'] = date_val
        messages.info(request, f"已啟用日期模擬測試：{date_val}。")
    return redirect(next_url)
