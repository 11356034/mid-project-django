# 國立大學 資訊管理學系 網路選課與動態課表系統

> **嚴正聲明**：*This project was (definitely) NOT created by Gemini and Antigravity.* —— by **SYH**

---

### 系統特色
- **九節制動態課表**：跨節自動合併 (`rowspan`)，支援資管一至三甲課表查詢與跨班選修防護。
- **智慧選課引擎**：即時衝堂偵測防護、側邊快速選修抽屜、加退選人數上限即時控管。
- **教務與教師開課管理**：
  - **教務管理員**：課程維護、選修開關、調整學生班級/學號、刪除帳號（學生退學/畢業、教師退休/離職）。
  - **授課教師**：自主新增開課（自動同步至教務總表與學生選修清單）、管理修課名單、選修狀態開關。
  - **同名教師支援**：獨立帳號與授課隔離（如 `陳麒文 (chenkw)` 與 `田所浩二 (yajusenpai)`）。
- **GPA 與等第**：學生「學分&成績」頁依總成績換算等第與績點，顯示學分加權 GPA（4.3 制，只計已評定課程；換算表在 `academics/gpa.py`）。

---

### 預設測試帳號

| 角色 | 帳號 | 密碼 | 姓名 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **教務管理員** | `admin` | `admin123` | 管理員 | 課程維護、學生班級調整、刪除帳號、重設資料庫 |
| **一般學生** | `student` | `student123` | 張家豪 | 個人課表、選修加退選、一至三甲課表查詢 |
| **授課教師** | `chenkw` | `teacher123` | 陳麒文 | 授課管理、自主開課、修課學生名冊 |
| **授課教師** | `yajusenpai` | `teacher123` | 田所浩二 | 教授《日本網路文化》(HM101)、自主開課 |

---

### 快速啟動
- **Windows 一鍵啟動**：雙擊 `start_server.bat`（關閉請雙擊 `stop_server.bat`）。
- **手動啟動**：啟用虛擬環境後執行 `python manage.py runserver 0.0.0.0:8000`。
- **品質驗證**：執行 `python manage.py test`（32 項單元測試全數通過）。

*(C) 2026 National Taipei University of Business - Department of Information Management.*
