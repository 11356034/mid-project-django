from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from pages.models import Course, Enrollment, UserProfile
from pages.utils import init_demo_data, create_student_account, create_teacher_account

from django.core.cache import cache

class CourseSelectionTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin_user, self.student_user = init_demo_data()

    def test_demo_initialization(self):
        """驗證預設帳號與課程建立"""
        self.assertTrue(User.objects.filter(username='admin').exists())
        self.assertTrue(User.objects.filter(username='student').exists())
        self.assertTrue(User.objects.filter(username='chenkw').exists())
        self.assertFalse(User.objects.filter(username__in=['chenkw1', 'chenkw2']).exists())
        self.assertEqual(self.student_user.first_name, '張家豪')
        self.assertGreaterEqual(Course.objects.count(), 10)
        # 課表必修科目數為 10 門
        self.assertEqual(Course.objects.filter(category='REQUIRED').count(), 10)

    def test_unauthenticated_redirects_to_login(self):
        """未登入使用者造訪首頁時應自動跳轉至 /login/"""
        response = self.client.get(reverse('pages:index'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('pages:login')))

    def test_student_login_and_enroll_open_course(self):
        """學生登入並成功加選開放中的選修課程 (如 Linux基礎教學)"""
        login_res = self.client.post(reverse('pages:login'), {'username': 'student', 'password': 'student123'}, follow=True)
        self.assertEqual(login_res.status_code, 200)

        # EL201 Linux基礎教學 (葉明貴老師)
        linux_course = Course.objects.get(code='EL201')
        self.assertEqual(linux_course.teacher, '葉明貴')
        self.assertTrue(linux_course.is_open_for_enrollment)

        response = self.client.post(reverse('pages:enroll_course', args=[linux_course.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=linux_course).exists())

    def test_student_cannot_enroll_closed_course(self):
        """學生無法選修管理員關閉中的課程 (如 EL205 人工智慧通識導論)"""
        self.client.force_login(self.student_user)
        ai_course = Course.objects.get(code='EL205')
        self.assertFalse(ai_course.is_open_for_enrollment)

        response = self.client.post(reverse('pages:enroll_course', args=[ai_course.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Enrollment.objects.filter(user=self.student_user, course=ai_course).exists())

    def test_student_time_conflict_prevention(self):
        """學生選課若與現有時段衝堂應被阻擋"""
        self.client.force_login(self.student_user)
        # 建立一門與週一 2-4 節（資訊管理導論）衝堂的選修課
        conflict_course = Course.objects.create(
            code='CONF01',
            name='衝堂測試課',
            teacher='測試師',
            classroom='電708',
            credits=2,
            category='ELECTIVE',
            day_of_week=1,
            start_period=3,
            end_period=4,
            is_open_for_enrollment=True,
            max_students=30
        )
        response = self.client.post(reverse('pages:enroll_course', args=[conflict_course.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Enrollment.objects.filter(user=self.student_user, course=conflict_course).exists())

    def test_student_drop_course(self):
        """學生退選選修課程"""
        self.client.force_login(self.student_user)
        # 加選後退選
        c = Course.objects.get(code='EL202')
        Enrollment.objects.create(user=self.student_user, course=c)
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=c).exists())

        response = self.client.post(reverse('pages:drop_course', args=[c.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Enrollment.objects.filter(user=self.student_user, course=c).exists())

    def test_student_cannot_drop_required_course(self):
        """學生不可退選資管一甲必修課程"""
        self.client.force_login(self.student_user)
        req_course = Course.objects.filter(category='REQUIRED').first()
        response = self.client.post(reverse('pages:drop_course', args=[req_course.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        # 依然存在
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=req_course).exists())

    def test_admin_toggle_course_status(self):
        """管理員切換課程是否開放選修"""
        self.client.force_login(self.admin_user)
        ai_course = Course.objects.get(code='EL205')
        self.assertFalse(ai_course.is_open_for_enrollment)

        # 切換為開放
        response = self.client.post(reverse('pages:toggle_course_status', args=[ai_course.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        ai_course.refresh_from_db()
        self.assertTrue(ai_course.is_open_for_enrollment)

        # 再切換回關閉
        response = self.client.post(reverse('pages:toggle_course_status', args=[ai_course.id]), follow=True)
        ai_course.refresh_from_db()
        self.assertFalse(ai_course.is_open_for_enrollment)

    def test_admin_add_course(self):
        """管理員新增課程"""
        self.client.force_login(self.admin_user)
        data = {
            'code': 'NEW101',
            'name': '人工智慧商務應用',
            'teacher': '黃教授',
            'classroom': '管401',
            'credits': 3,
            'category': 'ELECTIVE',
            'day_of_week': 3,
            'start_period': 7,
            'end_period': 8,
            'is_open_for_enrollment': 'on',
            'max_students': 40,
            'description': 'AI 商業實例解析',
            'color_tag': 'emerald',
        }
        response = self.client.post(reverse('pages:add_course'), data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Course.objects.filter(code='NEW101').exists())

    def test_admin_edit_course(self):
        """管理員編輯課程資訊與節次"""
        self.client.force_login(self.admin_user)
        c = Course.objects.get(code='EL201')
        data = {
            'name': '進階Linux雲端伺服器架設',
            'teacher': '葉明貴',
            'classroom': '電708(承曦樓)',
            'credits': 3,
            'category': 'ELECTIVE',
            'day_of_week': 5,
            'start_period': 5,
            'end_period': 7,
            'is_open_for_enrollment': 'on',
            'max_students': 50,
            'description': 'Linux 伺服器進階應用',
            'color_tag': 'emerald',
        }
        response = self.client.post(reverse('pages:edit_course', args=[c.id]), data, follow=True)
        self.assertEqual(response.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.name, '進階Linux雲端伺服器架設')
        self.assertEqual(c.credits, 3)
        self.assertEqual(c.end_period, 7)

    def test_teachers_list_in_index_context(self):
        """驗證管理員首頁提供教師名單供選取與自動補全"""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('pages:index'))
        self.assertEqual(response.status_code, 200)
        teachers_list = response.context['teachers_list']
        self.assertIn('葉明貴', teachers_list)
        self.assertIn('黃燕萍', teachers_list)
        self.assertIn('丁慧瑩', teachers_list)
        self.assertNotIn('丁慧堂', teachers_list)
        self.assertNotIn('佐藤愛子', teachers_list)
        # 驗證模板中包含 teacherOptionsList datalist 與下拉選單
        content = response.content.decode('utf-8')
        self.assertIn('id="teacherOptionsList"', content)
        self.assertIn('id="addTeacherInput"', content)
        self.assertIn('id="editTeacher"', content)
        self.assertIn('▼ 快速選擇', content)

    def test_semantic_directory_urls_and_tab_redirect(self):
        """驗證語意化目錄路徑（/enrolled/、/electives/、/timetable/）與舊式 ?tab= 重導向"""
        self.client.force_login(self.student_user)

        # 1. 直接造訪 /enrolled/
        res_enrolled = self.client.get(reverse('pages:enrolled'))
        self.assertEqual(res_enrolled.status_code, 200)
        self.assertEqual(res_enrolled.context['tab'], 'enrolled')
        self.assertIn('/enrolled/', res_enrolled.content.decode('utf-8'))

        # 2. 直接造訪 /electives/
        res_electives = self.client.get(reverse('pages:electives'))
        self.assertEqual(res_electives.status_code, 200)
        self.assertEqual(res_electives.context['tab'], 'electives')

        # 3. 直接造訪 /timetable/
        res_timetable = self.client.get(reverse('pages:timetable'))
        self.assertEqual(res_timetable.status_code, 200)
        self.assertEqual(res_timetable.context['tab'], 'timetable')

        # 4. 造訪舊式 ?tab=enrolled，應自動 302 導向至 /enrolled/
        res_legacy = self.client.get('/?tab=enrolled')
        self.assertEqual(res_legacy.status_code, 302)
        self.assertEqual(res_legacy.url, reverse('pages:enrolled'))

        # 5. 管理員造訪 /manage/courses/
        self.client.force_login(self.admin_user)
        res_admin = self.client.get(reverse('pages:manage_courses'))
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.context['tab'], 'admin_courses')

    def test_student_gender_and_add_student_feature(self):
        """驗證張家豪為男生、性別欄位存在，以及管理員新增資管一甲學生帳號功能"""
        # 1. 驗證張家豪性別為男，班級為資管一甲
        profile = self.student_user.profile
        self.assertEqual(profile.gender, 'M')
        self.assertEqual(profile.get_gender_display(), '男')
        self.assertEqual(profile.student_class, '資管一甲')

        # 2. 測試管理員新增資管一甲學生帳號 (例如: 林美美, 女生)
        self.client.force_login(self.admin_user)
        new_student_data = {
            'username': 'student2',
            'name': '林美美',
            'gender': 'F',
            'student_id': 'B11305002',
            'password': 'student123',
        }
        response = self.client.post(reverse('pages:add_student'), new_student_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # 驗證新學生已建立
        new_stu = User.objects.get(username='student2')
        self.assertEqual(new_stu.first_name, '林美美')
        self.assertEqual(new_stu.profile.gender, 'F')
        self.assertEqual(new_stu.profile.get_gender_display(), '女')
        self.assertEqual(new_stu.profile.student_class, '資管一甲')

        # 驗證新學生自動預載資管一甲的 10 門必修課
        enrolled_required_count = Enrollment.objects.filter(user=new_stu, course__category='REQUIRED').count()
        self.assertEqual(enrolled_required_count, 10)

        # 3. 測試非管理員無法新增學生
        self.client.force_login(self.student_user)
        res_forbidden = self.client.post(reverse('pages:add_student'), new_student_data)
        self.assertEqual(res_forbidden.status_code, 403)

    def test_admin_edit_student_id_feature(self):
        """驗證管理員可成功修改學生學號、權限校驗與重複/空白學號之防護機制"""
        # 1. 驗證張家豪原始學號
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.student_id, 'B11305001')

        # 2. 管理員成功修改學號為 B11305088
        self.client.force_login(self.admin_user)
        url = reverse('pages:edit_student_id', args=[self.student_user.id])
        response = self.client.post(url, {'student_id': 'B11305088'}, follow=True)
        self.assertEqual(response.status_code, 200)

        # 驗證資料庫已更新
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.student_id, 'B11305088')

        # 驗證學生登入後首頁即時顯示新學號
        self.client.force_login(self.student_user)
        res_index = self.client.get(reverse('pages:index'))
        self.assertContains(res_index, 'B11305088')

        # 3. 測試管理員不能將學號改為空白
        self.client.force_login(self.admin_user)
        res_empty = self.client.post(url, {'student_id': '   '}, follow=True)
        self.assertContains(res_empty, '學生學號不可為空白')
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.student_id, 'B11305088')

        # 4. 測試防止學號與其他學生重複
        # 先建立另一名學生 student2 (學號: B11305002)
        create_student_account(
            username='student2',
            name='李小明',
            gender='M',
            password='student123',
            student_id='B11305002'
        )
        res_dup = self.client.post(url, {'student_id': 'B11305002'}, follow=True)
        self.assertContains(res_dup, '已被其他學生使用')
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.student_id, 'B11305088')

        # 5. 測試非管理員(一般學生)無法修改他人學號
        self.client.force_login(self.student_user)
        res_forbidden = self.client.post(url, {'student_id': 'B11305999'})
        self.assertEqual(res_forbidden.status_code, 403)
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.student_id, 'B11305088')

    def test_admin_create_teacher_account(self):
        """教務管理員可建立教師帳號，一般學生不可建立"""
        self.client.force_login(self.admin_user)
        add_url = reverse('pages:add_teacher')

        # 管理員成功新增教師帳號
        res = self.client.post(add_url, {
            'username': 'prof_wang',
            'name': '王大明',
            'gender': 'M',
            'password': 'teacher123'
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        # 驗證資料庫建立成功且角色為 TEACHER
        teacher_user = User.objects.get(username='prof_wang')
        self.assertEqual(teacher_user.first_name, '王大明')
        self.assertEqual(teacher_user.profile.role, 'TEACHER')
        self.assertTrue(teacher_user.check_password('teacher123'))

        # 學生嘗試新增教師帳號應被禁止 403
        self.client.force_login(self.student_user)
        res_forbidden = self.client.post(add_url, {
            'username': 'prof_hacker',
            'name': '黑客',
            'gender': 'M',
            'password': 'pass'
        })
        self.assertEqual(res_forbidden.status_code, 403)
        self.assertFalse(User.objects.filter(username='prof_hacker').exists())

    def test_teacher_same_name_separate_management_and_enrolled_roster(self):
        """兩位同名同姓的陳麒文老師各自擁有獨立帳號，開課與修課學生管理完全互不干擾"""
        # 1. 建立兩位同名同姓「陳麒文」老師
        t1 = create_teacher_account(username='chenkw', name='陳麒文', password='teacher123')
        t2 = create_teacher_account(username='chenkw_alt', name='陳麒文', password='pwd2')

        # 2. 建立分別由兩位陳麒文老師任教之課程
        c1 = Course.objects.create(
            code='CKW101',
            name='陳麒文老師甲的進階演算法',
            teacher='陳麒文',
            teacher_user=t1,
            target_class='資管一甲',
            classroom='電708',
            credits=3,
            category='ELECTIVE',
            day_of_week=5,
            start_period=1,
            end_period=3,
            is_open_for_enrollment=True,
            max_students=40
        )

        c2 = Course.objects.create(
            code='CKW102',
            name='陳麒文老師乙的企業資源規劃',
            teacher='陳麒文',
            teacher_user=t2,
            target_class='資管一甲',
            classroom='藝406',
            credits=3,
            category='ELECTIVE',
            day_of_week=5,
            start_period=6,
            end_period=8,
            is_open_for_enrollment=False,
            max_students=40
        )

        # 學生選修 c1
        Enrollment.objects.create(user=self.student_user, course=c1)

        # 3. 測試陳麒文老師 1 (chenkw) 登入
        self.client.force_login(t1)
        res_t1 = self.client.get(reverse('pages:teacher_courses'))
        self.assertEqual(res_t1.status_code, 200)
        # 能看到自己的課程 c1 與修課學生張家豪
        self.assertContains(res_t1, '陳麒文老師甲的進階演算法')
        self.assertContains(res_t1, '張家豪')
        # 不能看到陳麒文老師 2 的課程 c2
        self.assertNotContains(res_t1, '陳麒文老師乙的企業資源規劃')

        # chenkw 可切換自己課程 c1 開放狀態
        toggle_c1 = self.client.post(reverse('pages:toggle_course_status', args=[c1.id]), follow=True)
        self.assertEqual(toggle_c1.status_code, 200)
        c1.refresh_from_db()
        self.assertFalse(c1.is_open_for_enrollment)

        # chenkw 無法切換 chenkw_alt 的課程 c2 (應被禁止 403)
        toggle_c2_by_t1 = self.client.post(reverse('pages:toggle_course_status', args=[c2.id]))
        self.assertEqual(toggle_c2_by_t1.status_code, 403)

        # 4. 測試陳麒文老師 2 (chenkw_alt) 登入
        self.client.force_login(t2)
        res_t2 = self.client.get(reverse('pages:teacher_courses'))
        self.assertEqual(res_t2.status_code, 200)
        # 能看到自己的課程 c2，但看不到 c1
        self.assertContains(res_t2, '陳麒文老師乙的企業資源規劃')
        self.assertNotContains(res_t2, '陳麒文老師甲的進階演算法')

        # chenkw_alt 可切換自己課程 c2 開放狀態
        toggle_c2 = self.client.post(reverse('pages:toggle_course_status', args=[c2.id]), follow=True)
        self.assertEqual(toggle_c2.status_code, 200)
        c2.refresh_from_db()
        self.assertTrue(c2.is_open_for_enrollment)

        # chenkw_alt 無法切換 chenkw 的課程 c1 (應被禁止 403)
        toggle_c1_by_t2 = self.client.post(reverse('pages:toggle_course_status', args=[c1.id]))
        self.assertEqual(toggle_c1_by_t2.status_code, 403)

    def test_class_restricted_electives_and_admin_adjust_class(self):
        """學生僅能加選自己所屬班級之選修課程，管理員可自由調整學生班級"""
        # 建立一門資管二甲限定之選修課
        c_mis2a = Course.objects.create(
            code='MIS201',
            name='資料庫管理專題',
            teacher='唐日新',
            target_class='資管二甲',
            classroom='電708',
            credits=3,
            category='ELECTIVE',
            day_of_week=4,
            start_period=7,
            end_period=9,
            is_open_for_enrollment=True,
            max_students=45
        )

        # 1. 學生原本所屬班級為「資管一甲」
        self.client.force_login(self.student_user)
        self.assertEqual(self.student_user.profile.student_class, '資管一甲')

        # 學生嘗試加選資管二甲之課程 -> 應被攔截阻擋
        res_enroll = self.client.post(reverse('pages:enroll_course', args=[c_mis2a.id]), follow=True)
        self.assertEqual(res_enroll.status_code, 200)
        self.assertFalse(Enrollment.objects.filter(user=self.student_user, course=c_mis2a).exists())
        self.assertContains(res_enroll, '為【資管二甲】限定選修課程')

        # 2. 管理員將學生班級調整為「資管二甲」
        self.client.force_login(self.admin_user)
        edit_url = reverse('pages:edit_student_id', args=[self.student_user.id])
        res_admin = self.client.post(edit_url, {
            'student_id': self.student_user.profile.student_id,
            'student_class': '資管二甲'
        }, follow=True)
        self.assertEqual(res_admin.status_code, 200)

        # 驗證資料庫中班級已更新為資管二甲
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.student_class, '資管二甲')

        # 3. 學生登入後現在可以加選資管二甲之課程
        self.client.force_login(self.student_user)
        res_enroll_ok = self.client.post(reverse('pages:enroll_course', args=[c_mis2a.id]), follow=True)
        self.assertEqual(res_enroll_ok.status_code, 200)
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=c_mis2a).exists())

    def test_class_timetable_switching(self):
        """使用者可查閱資管一甲、資管二甲、資管三甲課表，二三甲暫無課程時顯示編排中提示"""
        self.client.force_login(self.student_user)

        # 查閱資管一甲課表
        res_1a = self.client.get(reverse('pages:timetable') + '?class_name=資管一甲')
        self.assertEqual(res_1a.status_code, 200)
        self.assertContains(res_1a, '資訊管理導論')

        # 查閱資管二甲課表（暫未排課）
        res_2a = self.client.get(reverse('pages:timetable') + '?class_name=資管二甲')
        self.assertEqual(res_2a.status_code, 200)
        self.assertContains(res_2a, '【資管二甲】')
        self.assertContains(res_2a, '尚在編排中')

        # 查閱資管三甲課表（暫未排課）
        res_3a = self.client.get(reverse('pages:timetable') + '?class_name=資管三甲')
        self.assertEqual(res_3a.status_code, 200)
        self.assertContains(res_3a, '【資管三甲】')
        self.assertContains(res_3a, '尚在編排中')

    def test_teacher_display_username_yajusenpai(self):
        """驗證田所浩二 (yajusenpai) 老師帳號建立與課程之帳號名稱顯示"""
        # 1. 建立田所浩二教師帳號 yajusenpai
        t_user = create_teacher_account(username='yajusenpai', name='田所浩二', password='teacher123')
        
        # 2. 獲取由田所浩二授課之課程 HM101
        c_jp = Course.objects.get(code='HM101')
        self.assertEqual(c_jp.teacher, '田所浩二')
        # 驗證 display_teacher_username 自動對應至 yajusenpai
        self.assertEqual(c_jp.display_teacher_username, 'yajusenpai')

        # 3. 透過管理員進入課程管理頁面，驗證有顯示 (yajusenpai)
        self.client.force_login(self.admin_user)
        res = self.client.get(reverse('pages:manage_courses'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '田所浩二')
        self.assertContains(res, '(yajusenpai)')

    def test_admin_delete_student_graduated(self):
        """管理員以「已畢業」為由刪除學生帳號"""
        self.client.force_login(self.admin_user)
        stu = create_student_account(username='stu_grad', name='畢業生A', student_id='B110001')
        user_id = stu.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '已畢業'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '已成功刪除學生帳號【畢業生A】')
        self.assertContains(res, '原因：已畢業')

    def test_admin_delete_student_dropped_out(self):
        """管理員以「已退學」為由刪除學生帳號"""
        self.client.force_login(self.admin_user)
        stu = create_student_account(username='stu_drop', name='退學生B', student_id='B110002')
        user_id = stu.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '已退學'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '已成功刪除學生帳號【退學生B】')
        self.assertContains(res, '原因：已退學')

    def test_admin_delete_user_other_reason(self):
        """管理員以「其他」並附帶詳細說明刪除帳號"""
        self.client.force_login(self.admin_user)
        stu = create_student_account(username='stu_other', name='轉學生C', student_id='B110003')
        user_id = stu.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '其他',
            'reason_other': '轉學至他校'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '原因：其他（轉學至他校）')

    def test_admin_delete_user_other_without_explanation_rejected(self):
        """選擇「其他」卻未填寫原因說明時，應被阻擋並保留帳號"""
        self.client.force_login(self.admin_user)
        stu = create_student_account(username='stu_no_reason', name='學生D', student_id='B110004')
        user_id = stu.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '其他',
            'reason_other': '   '
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '請填寫詳細說明')

    def test_admin_delete_user_invalid_reason_rejected(self):
        """未提供合法刪除原因時，應被阻擋並保留帳號"""
        self.client.force_login(self.admin_user)
        stu = create_student_account(username='stu_invalid', name='學生E', student_id='B110005')
        user_id = stu.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '不喜歡'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '請選擇刪除原因')

    def test_admin_cannot_delete_self(self):
        """管理員無法刪除自身的帳號"""
        self.client.force_login(self.admin_user)
        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': self.admin_user.id,
            'reason_type': '已退學'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(User.objects.filter(id=self.admin_user.id).exists())
        self.assertContains(res, '無法刪除管理員帳號')

    def test_non_admin_cannot_delete_user(self):
        """非教務管理員（如一般學生）禁止呼叫刪除帳號功能 (403 Forbidden)"""
        self.client.force_login(self.student_user)
        victim = create_student_account(username='stu_victim', name='學生F')
        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': victim.id,
            'reason_type': '已退學'
        })
        self.assertEqual(res.status_code, 403)
        self.assertTrue(User.objects.filter(id=victim.id).exists())

    def test_delete_teacher_preserves_courses(self):
        """刪除教師帳號時，該教師的課程應保留並將 teacher_user 設為 None"""
        self.client.force_login(self.admin_user)
        tea = create_teacher_account(username='tea_del', name='測試刪除師')
        c = Course.objects.create(
            code='TEA_DEL_01',
            name='待保留課程',
            teacher='測試刪除師',
            teacher_user=tea,
            classroom='電101',
            credits=2
        )
        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': tea.id,
            'reason_type': '其他',
            'reason_other': '教師離職'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=tea.id).exists())
        # 課程依然存在
        c.refresh_from_db()
        self.assertIsNone(c.teacher_user)
        self.assertEqual(c.name, '待保留課程')

    def test_admin_delete_teacher_retired(self):
        """管理員以「退休」為由刪除教師帳號"""
        self.client.force_login(self.admin_user)
        tea = create_teacher_account(username='tea_retire', name='退休教師A')
        user_id = tea.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '退休'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '已成功刪除教師帳號【退休教師A】')
        self.assertContains(res, '原因：退休')

    def test_admin_delete_teacher_resigned(self):
        """管理員以「離職」為由刪除教師帳號"""
        self.client.force_login(self.admin_user)
        tea = create_teacher_account(username='tea_resign', name='離職教師B')
        user_id = tea.id

        res = self.client.post(reverse('pages:delete_user'), {
            'user_id': user_id,
            'reason_type': '離職'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertContains(res, '已成功刪除教師帳號【離職教師B】')
        self.assertContains(res, '原因：離職')

    def test_teacher_add_course_syncs_to_admin_and_students(self):
        """驗證老師可新增課程，且新增後資訊即時同步至 admin 與 student 端"""
        # 1. 建立田所浩二老師帳號
        t_user = create_teacher_account(username='yajusenpai', name='田所浩二', password='teacher123')
        self.client.force_login(t_user)

        # 2. 老師由教師專區新增課程 HM102
        add_data = {
            'code': 'HM102',
            'name': '日本現代次文化研究',
            'target_class': '資管一甲',
            'classroom': '藝405',
            'credits': 2,
            'category': 'ELECTIVE',
            'day_of_week': 5,
            'start_period': 8,
            'end_period': 9,
            'is_open_for_enrollment': 'on',
            'max_students': 30,
            'description': '次文化與網路迷因演進',
            'color_tag': 'indigo',
        }
        res_teacher = self.client.post(reverse('pages:add_course'), add_data, follow=True)
        self.assertEqual(res_teacher.status_code, 200)

        # 驗證課程已成功寫入資料庫，且授課教師與帳號正確綁定為本人
        course = Course.objects.get(code='HM102')
        self.assertEqual(course.name, '日本現代次文化研究')
        self.assertEqual(course.teacher, '田所浩二')
        self.assertEqual(course.teacher_user, t_user)
        self.assertEqual(course.display_teacher_username, 'yajusenpai')

        # 3. 驗證教師端可看到自己新增的這門課
        res_t_view = self.client.get(reverse('pages:teacher_courses'))
        self.assertContains(res_t_view, '日本現代次文化研究')
        self.assertContains(res_t_view, '藝405')

        # 4. 驗證同步至 Admin 端：admin 課程管理清單立即可見此課程，並顯示教師名稱與帳號 (yajusenpai)
        self.client.force_login(self.admin_user)
        res_admin = self.client.get(reverse('pages:manage_courses'))
        self.assertEqual(res_admin.status_code, 200)
        self.assertContains(res_admin, '日本現代次文化研究')
        self.assertContains(res_admin, '田所浩二')
        self.assertContains(res_admin, '(yajusenpai)')

        # 5. 驗證同步至 Student 端：資管一甲學生在選修專區立即可見此新課程，並能正常加選
        self.client.force_login(self.student_user)
        res_student_electives = self.client.get(reverse('pages:electives'))
        self.assertEqual(res_student_electives.status_code, 200)
        self.assertContains(res_student_electives, '日本現代次文化研究')
        self.assertContains(res_student_electives, '田所浩二')

        # 學生執行加選
        res_enroll = self.client.post(reverse('pages:enroll_course', args=[course.id]), follow=True)
        self.assertEqual(res_enroll.status_code, 200)
        self.assertTrue(Enrollment.objects.filter(user=self.student_user, course=course).exists())

        # 6. 驗證教師端之修課名單同步更新出現該學生
        self.client.force_login(t_user)
        res_t_roster = self.client.get(reverse('pages:teacher_courses'))
        self.assertContains(res_t_roster, self.student_user.first_name)

    def test_teacher_can_edit_and_delete_own_course(self):
        """驗證教師可編輯與刪除自己開的課程，但無法竄改其他教師的課程"""
        t1 = create_teacher_account(username='tea_alpha', name='甲老師')
        t2 = create_teacher_account(username='tea_beta', name='乙老師')

        c1 = Course.objects.create(
            code='ALPHA01',
            name='甲老師專題',
            teacher='甲老師',
            teacher_user=t1,
            classroom='電101',
            credits=2,
            day_of_week=1,
            start_period=8,
            end_period=9
        )

        # 乙老師嘗試編輯甲老師的課程被拒絕 (403)
        self.client.force_login(t2)
        res_t2_edit = self.client.post(reverse('pages:edit_course', args=[c1.id]), {
            'name': '被竄改的課程'
        })
        self.assertEqual(res_t2_edit.status_code, 403)

        # 甲老師編輯自己的課程成功
        self.client.force_login(t1)
        res_t1_edit = self.client.post(reverse('pages:edit_course', args=[c1.id]), {
            'name': '甲老師專題(更新版)',
            'classroom': '電708',
            'credits': 3,
            'category': 'ELECTIVE',
            'day_of_week': 1,
            'start_period': 8,
            'end_period': 9,
            'max_students': 40
        }, follow=True)
        self.assertEqual(res_t1_edit.status_code, 200)
        c1.refresh_from_db()
        self.assertEqual(c1.name, '甲老師專題(更新版)')
        self.assertEqual(c1.classroom, '電708')

        # 乙老師嘗試刪除甲老師的課程被拒絕 (403)
        self.client.force_login(t2)
        res_t2_del = self.client.post(reverse('pages:delete_course', args=[c1.id]))
        self.assertEqual(res_t2_del.status_code, 403)
        self.assertTrue(Course.objects.filter(id=c1.id).exists())

        # 甲老師刪除自己的課程成功
        self.client.force_login(t1)
        res_t1_del = self.client.post(reverse('pages:delete_course', args=[c1.id]), follow=True)
        self.assertEqual(res_t1_del.status_code, 200)
        self.assertFalse(Course.objects.filter(id=c1.id).exists())

    def test_student_cannot_add_course(self):
        """一般學生禁止呼叫新增課程功能 (403 Forbidden)"""
        self.client.force_login(self.student_user)
        res = self.client.post(reverse('pages:add_course'), {
            'code': 'HACK01',
            'name': '學生私開課程'
        })
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Course.objects.filter(code='HACK01').exists())






    def test_login_failure_does_not_leak_credentials(self):
        """登入失敗訊息不得洩漏帳號密碼資訊（符合資安規範）"""
        res = self.client.post(reverse('pages:login'), {
            'username': 'student',
            'password': 'wrongpassword'
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '帳號或密碼輸入錯誤，請重新確認後再試。')
        self.assertNotContains(res, 'student123')
        self.assertNotContains(res, 'admin123')
        self.assertNotContains(res, 'teacher123')

    def test_login_rate_limiting_brute_force_protection(self):
        """連續登入失敗超過上限應觸發防暴力破解鎖定限制"""
        for _ in range(5):
            res = self.client.post(reverse('pages:login'), {
                'username': 'student',
                'password': 'wrongpassword'
            }, follow=True)
            self.assertEqual(res.status_code, 200)

        # 第 6 次嘗試應直接被資安頻率限制攔截
        res_blocked = self.client.post(reverse('pages:login'), {
            'username': 'student',
            'password': 'student123'
        }, follow=True)
        self.assertEqual(res_blocked.status_code, 200)
        self.assertContains(res_blocked, '登入失敗次數過多，為維護帳號資訊安全')
