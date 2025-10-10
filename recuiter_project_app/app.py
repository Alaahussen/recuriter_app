# streamlit_app.py
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
import streamlit as st
import os
import json
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from models import PipelineState, Candidate
from Graph import build_graph
from dotenv import load_dotenv
from config import get_job_config
from Utils import _send_gmail_direct,_get_message_body,save_to_env,extract_city_from_form_data,assign_city_to_candidate
import io
import re
from googleapiclient.http import MediaIoBaseUpload
from config import *
from Featch_cv import normalize_arabic_text
from Google_services import google_services
from Drive import *
# تحميل متغيرات البيئة
import os
os.environ["MALLOC_TRIM_THRESHOLD_"] = "0"
os.environ["MALLOC_ARENA_MAX"] = "2"
load_dotenv()

# إعدادات الصفحة
st.set_page_config(
    page_title="لوحة متابعة التوظيف",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)
# تنسيق CSS للغة العربية
st.markdown("""
<style>
/* ===========================================================
   🌗 Universal RTL + Theme-Aware Styling (Light & Dark Modes)
   ===========================================================*/

/* --- Define theme variables --- */
:root {
  --background-color: #ffffff;
  --background-color-secondary: #f9fafb;
  --text-color: #1e1e1e;
  --accent-color: #facc15;
  --accent-color-hover: #fde047;
  --border-color: #e5e7eb;
  --shadow-color: rgba(0, 0, 0, 0.08);
}

/* --- Dark mode overrides --- */
@media (prefers-color-scheme: dark) {
  :root {
    --background-color: #1e1e1e;
    --background-color-secondary: #2a2a2a;
    --text-color: #f5f5f5;
    --accent-color: #eab308; /* gold but less saturated for dark bg */
    --accent-color-hover: #facc15;
    --border-color: #3a3a3a;
    --shadow-color: rgba(0, 0, 0, 0.5);
  }
}

/* ------------------------------
   🌐 Global RTL + Base Setup
---------------------------------*/
html, body, [class*="css"] {
    font-family: 'Tajawal', 'Cairo', sans-serif !important;
    direction: rtl !important;
    text-align: right !important;
    background-color: var(--background-color) !important;
    color: var(--text-color) !important;
}

/* Box container */
.box {
    background-color: var(--background-color-secondary);
    color: var(--text-color);
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 2px 8px var(--shadow-color);
}
</style>

<div class="box">
    <p>هذا المربع يتكيف تلقائيًا مع وضع السمة 🌓</p>
</div>

<style>
/* ------------------------------
   🧭 Sidebar Styling
---------------------------------*/
[data-testid="stSidebar"] {
    direction: rtl !important;
    text-align: right !important;
    background-color: var(--background-color-secondary) !important;
    color: var(--text-color) !important;
}

/* Sidebar inputs and labels */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stRadio,
[data-testid="stSidebar"] .stCheckbox {
    font-weight: 500;
    font-size: 1rem;
    color: var(--text-color) !important;
}

/* Slider styling */
.stSlider {
    direction: ltr !important;
    text-align: left !important;
    color: var(--text-color) !important;
}

/* ------------------------------
   📋 Headings & Cards
---------------------------------*/
.main-header {
    font-size: 2.5rem;
    color: var(--accent-color);
    text-align: center;
    margin-bottom: 2rem;
    font-weight: 700;
}

.metric-card, .candidate-card, .report-section {
    background-color: var(--background-color-secondary);
    border-radius: 0.75rem;
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 4px var(--shadow-color);
    padding: 1.5rem;
    margin: 1rem 0;
    color: var(--text-color);
}

/* ------------------------------
   🖲️ Buttons
---------------------------------*/
.stButton > button {
    background-color: var(--accent-color) !important;
    color: var(--text-color) !important;
    font-weight: 600 !important;
    border-radius: 0.5rem !important;
    border: none !important;
}
.stButton > button:hover {
    background-color: var(--accent-color-hover) !important;
}

/* ------------------------------
   📑 DataFrame Styling
---------------------------------*/
.dataframe, .dataframe table, .dataframe th, .dataframe td {
    direction: ltr !important;
    text-align: left !important;
    unicode-bidi: plaintext !important;
    font-family: 'Segoe UI', 'Courier New', sans-serif !important;
}

.dataframe th {
    background-color: var(--accent-color) !important;
    color: var(--text-color) !important;
    font-weight: bold !important;
}

.dataframe td {
    background-color: var(--background-color-secondary) !important;
    color: var(--text-color) !important;
    border-bottom: 1px solid var(--border-color) !important;
}

/* ------------------------------
   ⚠️ Alerts and Info Boxes
---------------------------------*/
.stAlert {
    direction: rtl !important;
    text-align: right !important;
}

/* ------------------------------
   🧩 Form Elements
---------------------------------*/
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input,
.stSelectbox > div > div > div,
.stMultiselect > div > div > div {
    direction: rtl !important;
    text-align: right !important;
    font-family: 'Tajawal', sans-serif !important;
    background-color: var(--background-color-secondary) !important;
    color: var(--text-color) !important;
}

/* ------------------------------
   📅 Tabs and Misc
---------------------------------*/
.stTabs [data-baseweb="tab-list"] {
    direction: rtl !important;
}

/* Tooltip + Radio + Checkbox */
.stRadio > label { gap: 4px !important; }
.stCheckbox > label {
    direction: rtl;
    text-align: right;
    padding-right: 4px;
    gap: 4px !important;
}
</style>
""", unsafe_allow_html=True)


class ATSApp:
    def __init__(self):
        self.workflow = None
        self.state = None
        self.sheet_id = None
        self.drive_folder_id = None
        self.send_tests_enabled = True  # افتراضي
        
        # تهيئة حالة الجلسة
        if 'candidates' not in st.session_state:
            st.session_state.candidates = []
        if 'selected_candidate_index' not in st.session_state:
            st.session_state.selected_candidate_index = 0
        if 'google_services' not in st.session_state:
            st.session_state.google_services = None
        if 'sheet_id' not in st.session_state:
            st.session_state.sheet_id = None
        if 'drive_folder_id' not in st.session_state:
            st.session_state.drive_folder_id = None
        if 'enable_city_filter' not in st.session_state:
            st.session_state.enable_city_filter = True
        if 'job_cities' not in st.session_state:
            st.session_state.job_cities = []
        if 'regenerate_questions' not in st.session_state:
            st.session_state.regenerate_questions = "استخدام الأسئلة الموجودة (لا إنشاء جديد)"
    
    def normalize_city_name(self, city: str) -> str:
        """توحيد أسماء المدن لمطابقة أفضل"""
        if not city:
            return ""
        
        city = str(city).strip()
        
        # الاختلافات الشائعة في أسماء المدن
        city_variations = {
            # الاختلافات العربية
            'مكه': 'مكة',
            'مكّه': 'مكة',
            'مكة المكرمة': 'مكة',
            'المدينة المنورة': 'المدينة',
            'الرياض': 'الرياض',
            'جده': 'جدة',
            'جدّه': 'جدة',
            'الدمام': 'الدمام',
            'الطائف': 'الطائف',
            # الاختلافات الإنجليزية
            'makkah': 'مكة',
            'mecca': 'مكة',
            'madina': 'المدينة',
            'medina': 'المدينة',
            'riyadh': 'الرياض',
            'jeddah': 'جدة',
            'dammam': 'الدمام',
            'taif': 'الطائف'
        }
        
        # توحيد النص العربي
        city = normalize_arabic_text(city)
        
        # التحويل للأحرف الصغيرة للمقارنة
        city_lower = city.lower()
        
        # التحقق من الاختلافات
        for variation, normalized in city_variations.items():
            if variation in city_lower or city_lower in variation:
                return normalized
        
        return city
    
    def cities_match(self, candidate_city: str, selected_cities: List[str]) -> bool:
        """التحقق مما إذا كانت مدينة المرشح تطابق أي مدينة محددة"""
        if not candidate_city or not selected_cities:
            return False
        
        normalized_candidate_city = self.normalize_city_name(candidate_city)
        
        for selected_city in selected_cities:
            normalized_selected = self.normalize_city_name(selected_city)
            
            # تطابق تام
            if normalized_candidate_city == normalized_selected:
                return True
            
            # تطابق جزئي (مرن أكثر)
            if (normalized_selected in normalized_candidate_city or 
                normalized_candidate_city in normalized_selected):
                return True
            
            # التحقق من الاختصارات أو الاختلافات الشائعة
            if self.are_cities_similar(normalized_candidate_city, normalized_selected):
                return True
        
        return False
    
    def are_cities_similar(self, city1: str, city2: str) -> bool:
        """التحقق مما إذا كان اسمي المدينة متشابهين"""
        common_aliases = {
            'مكة': ['مكه', 'مكّه', 'مكة المكرمة', 'makkah', 'mecca'],
            'المدينة': ['المدينة المنورة', 'madina', 'medina'],
            'الرياض': ['riyadh'],
            'جدة': ['جده', 'جدّه', 'jeddah'],
            'الدمام': ['dammam'],
            'الطائف': ['الطائف', 'taif']
        }
        
        city1_norm = self.normalize_city_name(city1)
        city2_norm = self.normalize_city_name(city2)
        
        # التحقق مما إذا كانا متطابقين مباشرة في الأسماء المستعارة
        for main_city, aliases in common_aliases.items():
            if (city1_norm == main_city and city2_norm in aliases) or \
               (city2_norm == main_city and city1_norm in aliases):
                return True
        
        return False
    
    def filter_candidates_by_city(self, candidates: List[Candidate], selected_cities: List[str]) -> List[Candidate]:
        """تصفية المرشحين حسب المدينة إذا كان التصفية مفعلة"""
        if not st.session_state.enable_city_filter or not selected_cities:
            return candidates
        
        filtered_candidates = []
        for candidate in candidates:
            if candidate.city and self.cities_match(candidate.city, selected_cities):
                filtered_candidates.append(candidate)
        
        return filtered_candidates

    def get_google_services(self):
        if st.session_state.google_services is None:
            try:
                st.session_state.google_services = google_services()
            except Exception as e:
                st.error(f"فشل في تهيئة خدمات Google: {str(e)}")
                return None
        return st.session_state.google_services
    
    def initialize_workflow(self):
        try:
            self.workflow = build_graph()
            return True
        except Exception as e:
            st.error(f"فشل في تهيئة سير العمل: {str(e)}")
            return False
    
    def setup_infrastructure(self):
        services = self.get_google_services()
        load_dotenv(override=True)
        if not services:
            return None
        gmail, calendar, drive, sheets, forms = services
        
        try:
            # الحصول على job_id من البيئة أو حالة الجلسة
            job_id = os.getenv("JOB_ID") or st.session_state.get("JOB_ID")
            if not job_id:
                st.error("❌ لم يتم العثور على معرف الوظيفة (JOB_ID). يرجى تعبئة الحقول أولاً.")
                return None

            # التأكد من أن job_id ليس None في اسم المجلد
            drive_folder_name = f"ATS/{job_id}"
            sheet_title = f"ATS_Candidates_{job_id}"  # جعل اسم الورقة فريدًا لكل وظيفة
            
            self.drive_folder_id = ensure_drive_folder(drive, drive_folder_name)
            st.session_state.drive_folder_id = self.drive_folder_id
            os.environ["DRIVE_FOLDER_ID"] = self.drive_folder_id
            
            self.sheet_id = ensure_sheet(sheets, drive, sheet_title, self.drive_folder_id)
            st.session_state.sheet_id = self.sheet_id
            os.environ["SHEET_ID"] = self.sheet_id
            
            return self.sheet_id
            
        except Exception as e:
            st.error(f"فشل في إعداد البنية التحتية: {str(e)}")
            return None
    
    def run_pipeline(self, job_config: Dict[str, Any]):
        load_dotenv(override=True)
        try:
            # مسح المرشحين السابقين عند بدء خط أنابيب جديد
            st.session_state.candidates = []
            
            # التأكد من تعيين جميع قيم تكوين الوظيفة
            for key, value in job_config.items():
                if value:  # التعيين فقط إذا كانت القيمة غير فارغة
                    os.environ[key] = value
                    st.session_state[key] = value
            
            # التحقق من تعيين JOB_ID قبل المتابعة
            if not os.getenv("JOB_ID"):
                st.error("❌ JOB_ID غير محدد. يرجى تعبئة الحقول أولاً.")
                return False
                
            sheet_id = self.setup_infrastructure()
            if not sheet_id:
                st.error("فشل في إعداد البنية التحتية لـ Google")
                return False
            
            self.sheet_id = sheet_id
            st.session_state.sheet_id = sheet_id
            self.drive_folder_id = st.session_state.drive_folder_id
            
            if self.workflow is None:
                if not self.initialize_workflow():
                    return False
            
            initial_state = PipelineState()
            self.state = self.workflow.invoke(initial_state.model_dump())
            st.session_state.candidates = self.get_candidates_from_sheet()
            
            return True
        except Exception as e:
            st.error(f"فشل تنفيذ خط الأنابيب: {str(e)}")
            return False

    def get_candidates_from_sheet(self) -> List[Candidate]:
        sheet_id = self.sheet_id or st.session_state.get('sheet_id')
        services = self.get_google_services()
        if not services or not sheet_id:
            return []
        
        gmail, calendar, drive, sheets, forms = services
        
        try:
            res = sheets.spreadsheets().values().get(
                spreadsheetId=sheet_id, 
                range='Candidates!D2:D'
            ).execute()
            
            emails = [row[0] for row in res.get('values', []) if row and row[0]]
            candidates = []
            
            for email in emails:
                candidate_data = get_candidate_from_sheet(sheets, sheet_id, email)
                if candidate_data:
                    # التأكد من أن النقاط أرقام وليست None
                    cv_score = candidate_data.get('cv_score')
                    test_score = candidate_data.get('test_score') 
                    overall_score = candidate_data.get('overall_score')
                    
                    candidate = Candidate(
                        email=email,
                        name=candidate_data.get('name'),
                        city=candidate_data.get('city'),
                        degree=candidate_data.get('degree'),
                        experience=candidate_data.get('experience',[]),
                        certifications=candidate_data.get('certifications', []),
                        job_id=candidate_data.get('job_id', os.getenv("JOB_ID", "")),
                        status=candidate_data.get('status', 'received'),
                        final_evaluation=candidate_data.get('final_evaluation'),
                        cv_score=float(cv_score) if cv_score is not None else 0.0,
                        test_score=float(test_score) if test_score is not None else 0.0,
                        overall_score=float(overall_score) if overall_score is not None else 0.0,
                    )
                    candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            st.error(f"خطأ في القراءة من Google Sheets: {str(e)}")
            return []
    
    def get_candidate_folder_id(self, candidate: Candidate) -> str:
        services = self.get_google_services()
        if not services or not st.session_state.drive_folder_id:
            return ""
        
        gmail, calendar, drive, sheets, forms = services
        
        try:
            candidate_folder_name = candidate.email
            query = f"'{st.session_state.drive_folder_id}' in parents and name = '{candidate_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = drive.files().list(q=query, fields="files(id)").execute()
            files = results.get('files', [])
            
            if files:
                return files[0]['id']
            else:
                folder_metadata = {
                    'name': candidate_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [st.session_state.drive_folder_id]
                }
                folder = drive.files().create(body=folder_metadata, fields='id').execute()
                return folder['id']
                
        except Exception as e:
            st.error(f"فشل في الحصول/إنشاء مجلد المرشح لـ {candidate.email}: {str(e)}")
            return ""
    
    def get_interview_questions(self, candidate: Candidate) -> str:
        services = self.get_google_services()
        if not services:
            return "خدمات Google غير مهيأة."
        
        gmail, calendar, drive, sheets, forms = services
        
        candidate_folder_id = self.get_candidate_folder_id(candidate)
        if not candidate_folder_id:
            return "لا يوجد مجلد Drive متاح لهذا المرشح."
        
        try:
            query = f"'{candidate_folder_id}' in parents and (name contains 'interview_questions' or name contains 'questions') and trashed = false"
            results = drive.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            for file in files:
                content = read_drive_file_text(drive, file['id'], file['name'])
                if content:
                    return content
            
            return "لم يتم العثور على أسئلة مقابلة في مجلد المرشح."
                
        except Exception as e:
            return f"خطأ في تحميل أسئلة المقابلة: {str(e)}"

    def get_candidate_report(self, candidate: Candidate) -> str:
        services = self.get_google_services()
        if not services:
            return "خدمات Google غير مهيأة."
        
        gmail, calendar, drive, sheets, forms = services
        
        candidate_folder_id = self.get_candidate_folder_id(candidate)
        if not candidate_folder_id:
            return "لا يوجد مجلد Drive متاح لهذا المرشح."
        
        try:
            query = f"'{candidate_folder_id}' in parents and (name contains 'report.json' or name contains 'report') and trashed = false"
            results = drive.files().list(q=query, fields="files(id, name, mimeType)").execute()
            files = results.get('files', [])
            
            for file in files:
                if file['mimeType'] in ['text/plain', 'application/json']:
                    content = read_drive_file_text(drive, file['id'], file['name'])
                    if content:
                        try:
                            data = json.loads(content)
                            return self.format_report_as_markdown(data)
                        except:
                            return self.format_text_report(content)
            return "لم يتم العثور على ملفات تقرير قابلة للقراءة في مجلد المرشح."
                
        except Exception as e:
            return f"خطأ في تحميل التقرير: {str(e)}"
    
    def format_report_as_markdown(self, data: Dict) -> str:
        """تنسيق التقرير JSON كـ markdown منظم"""
        md = "# تقرير المرشح\n\n"
        
        for section, content in data.items():
            if isinstance(content, dict):
                md += f"## {section.replace('_', ' ').title()}\n\n"
                for key, value in content.items():
                    if isinstance(value, list):
                        md += f"### {key.replace('_', ' ').title()}\n"
                        for item in value:
                            md += f"- {item}\n"
                        md += "\n"
                    else:
                        md += f"**{key.replace('_', ' ').title()}:** {value}\n\n"
            elif isinstance(content, list):
                md += f"## {section.replace('_', ' ').title()}\n\n"
                for item in content:
                    md += f"- {item}\n"
                md += "\n"
            else:
                md += f"**{section.replace('_', ' ').title()}:** {content}\n\n"
        
        return md
    
    def format_text_report(self, content: str) -> str:
        """تنسيق التقرير النصي العادي بهيكل أفضل"""
        lines = content.split('\n')
        md = "# تقرير المرشح\n\n"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.endswith(':'):
                md += f"## {line[:-1]}\n\n"
            elif line.startswith('- ') or line.startswith('* '):
                md += f"{line}\n"
            else:
                md += f"{line}\n\n"
        
        return md
    
    def format_questions_as_markdown(self, content: str) -> str:
        """تنسيق أسئلة المقابلة بـ markdown مناسب"""
        lines = content.split('\n')
        md = "# أسئلة المقابلة\n\n"
        
        question_number = 1
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(keyword in line.lower() for keyword in ['question', 'q:']):
                md += f"## السؤال {question_number}\n\n{line}\n\n"
                question_number += 1
            else:
                md += f"{line}\n\n"
        
        return md
    
    def reset_job_inputs(self):
        """إعادة تعيين معلومات الوظيفة فقط"""
        for key in ["JOB_ID", "JOB_CITY", "JOB_REQUIREMENTS"]:
            if key in st.session_state:
                del st.session_state[key]
        # أيضًا إعادة تعيين قائمة المرشحين
        st.session_state.candidates = []
    def node_send_tests(self, candidate: Candidate) -> Tuple[bool, str]:
        """إرسال اختبار لمرشح واحد وإرجاع نجاح العملية ورابط النموذج"""
        try:
            config = get_job_config()
            services = self.get_google_services()
            if not services:
                return False, ""
                
            gmail, calendar, drive, sheets, forms = services
            
            # إنشاء الاختبار
            quiz = llm_json(TEST_GEN_PROMPT.format(job_id=config['job_id']), expect_list=True) or []
            if not quiz:
                return False, ""
    
            # إنشاء نموذج Google
            form_body = {
                "info": {
                    "title": f"{config.get('job_title', 'Technical Quiz')} - Technical Quiz",
                    "documentTitle": f"Quiz for {candidate.name or 'Candidate'}"
                }
            }
            form = forms.forms().create(body=form_body).execute()
            form_id = form["formId"]
    
            # إضافة الأسئلة للنموذج
            requests = []
            for i, q in enumerate(quiz):
                qtxt = q.get("question") if isinstance(q, dict) else str(q)
                opts = q.get("options", []) if isinstance(q, dict) else []
    
                question_item = {
                    "title": qtxt,
                    "questionItem": {
                        "question": {
                            "required": True,
                        }
                    }
                }
    
                if opts:
                    question_item["questionItem"]["question"]["choiceQuestion"] = {
                        "type": "RADIO",
                        "options": [{"value": o} for o in opts],
                        "shuffle": True,
                    }
    
                requests.append({
                    "createItem": {
                        "item": question_item,
                        "location": {"index": i}
                    }
                })
    
            if requests:
                forms.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
    
            form_link = f"https://docs.google.com/forms/d/{form_id}/viewform"
    
            # إرسال البريد الإلكتروني
            deadline = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
            body = config.get('templates', {}).get('test', '').format(
                name=candidate.name or 'Candidate',
                test_link=form_link,
                deadline=deadline
            )
            _send_gmail_direct(gmail, candidate.email, f"{config['job_id']} - Technical Quiz", body)
    
            # تحديث بيانات المرشح في state
            candidate.status = 'test_sent'
            candidate.form_id = form_id
            candidate.notes = json.dumps({
                "form_id": form_id,
                "quiz": quiz,
                "test_sent_at": datetime.now().isoformat()
            }, ensure_ascii=False)
    
            # تحديث الـ Sheet مباشرة
            sheet_id = self.sheet_id or st.session_state.get('sheet_id')
            if sheet_id:
                row_index = find_candidate_row_by_email(sheets, sheet_id, candidate.email)
                if row_index:
                    # تحديث الحالة والملاحظات في الـ Sheet
                    update_range = f"Candidates!L{row_index}:M{row_index}"  # L: Status, M: Notes
                    sheets.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=update_range,
                        valueInputOption="RAW",
                        body={"values": [[candidate.status, candidate.notes]]},
                    ).execute()
                    
                    # تحديث رابط الاختبار
                    update_candidate_row_links(sheets, sheet_id, row_index, form_id, form_link, "")
    
            return True, form_link
    
        except Exception as e:
            print(f"❌ فشل إرسال الاختبار: {e}")
            return False, ""
    def regenerate_interview_questions(self, candidate: Candidate, mode: str = "both") -> bool:
        """إعادة إنشاء أسئلة المقابلة بناءً على الوضع المحدد (cv / job_requirements / both)."""
        try:
            services = self.get_google_services()
            if not services:
                return False

            gmail, calendar, drive, sheets, forms = services

            job_requirements = os.getenv("JOB_REQUIREMENTS", "")
            job_id = os.getenv("JOB_ID", "")

            # بناء النص بناءً على الوضع
            if mode == "cv":
                source_text = f"السيرة الذاتية:\n{candidate.raw_text[:15000]}"
                prompt_intro = (
                    "اعتمد فقط على السيرة الذاتية التالية لإنشاء أسئلة مقابلة مناسبة للدور الوظيفي. "
                    "قم بتحليل الخبرات العملية، والمشروعات المنفذة، والمهارات التقنية، "
                    "والدورات التدريبية أو الشهادات المذكورة في السيرة الذاتية، "
                    "واطرح أسئلة تساعد على تقييم مدى عمق الخبرة والفهم التطبيقي لهذه الجوانب."
                )
            elif mode == "job_requirements":
                source_text = f"متطلبات الوظيفة:\n{job_requirements}"
                prompt_intro = "اعتمد فقط على متطلبات الوظيفة التالية لإنشاء أسئلة مقابلة مناسبة."
            else:  # both
                source_text = (
                    f"السيرة الذاتية:\n{candidate.raw_text[:10000]}\n\n"
                    f"متطلبات الوظيفة:\n{job_requirements}"
                )
                prompt_intro = "اعتمد على السيرة الذاتية ومتطلبات الوظيفة لإنشاء أسئلة مقابلة مناسبة."

            # النص النهائي المدمج
            prompt = f"""
            {prompt_intro}

            قم بإنشاء 6 أسئلة مقابلة مهنية مختصرة ومحددة للدور.
            يجب أن تكون جميع الأسئلة باللغة العربية فقط.
            أعد النتيجة على شكل مصفوفة JSON فقط مثل:
            ["سؤال 1", "سؤال 2", "سؤال 3", "سؤال 4", "سؤال 5", "سؤال 6"]

            {source_text}
                    """.strip()

            # إنشاء استجابة من LLM
            llm_response = llm_json(prompt)

            # استخراج الأسئلة بأمان
            if isinstance(llm_response, list):
                new_questions = llm_response
            elif isinstance(llm_response, dict):
                new_questions = list(llm_response.values())[0] if llm_response else []
            else:
                new_questions = []

            if not new_questions:
                st.error("فشل في استخراج الأسئلة من الاستجابة.")
                return False

            # الحفظ في Drive
            candidate_folder_id = self.get_candidate_folder_id(candidate)
            if not candidate_folder_id:
                return False

            # حذف ملفات الأسئلة القديمة
            self.delete_old_question_files(drive, candidate_folder_id)

            # حفظ الملف الجديد
            content = io.BytesIO("\n".join(new_questions).encode("utf-8"))
            media = MediaIoBaseUpload(content, mimetype="text/plain", resumable=False)
            meta = {"name": f"interview_questions_{candidate.email}.txt", "parents": [candidate_folder_id]}
            drive.files().create(body=meta, media_body=media, fields="id, webViewLink").execute()

            # تحديث كائن المرشح
            candidate.interview_questions = new_questions

            return True

        except Exception as e:
            st.error(f"خطأ في إعادة إنشاء الأسئلة: {str(e)}")
            return False

    def delete_old_question_files(self, drive, candidate_folder_id: str):
        """حذف ملفات الأسئلة الموجودة"""
        try:
            query = f"'{candidate_folder_id}' in parents and (name contains 'interview_questions' or name contains 'questions') and trashed = false"
            results = drive.files().list(q=query, fields="files(id)").execute()
            
            for file in results.get('files', []):
                drive.files().delete(fileId=file['id']).execute()
                
        except Exception as e:
            print(f"تحذير: لا يمكن حذف ملفات الأسئلة القديمة: {e}")
    
    def display_metrics(self, candidates: List[Candidate]):
        col1, col2, col3, col4, col5 = st.columns(5)
        
        total_candidates = len(candidates)
        interviewed = len([c for c in candidates if c.status == 'interview_scheduled'])
        rejected = len([c for c in candidates if c.status == 'rejected'])
        tested = len([c for c in candidates if c.status == 'tested'])
        high_score = len([c for c in candidates if c.final_evaluation=='Interview Step'])
        
        with col1:
            st.metric("إجمالي المرشحين", total_candidates)
        with col2:
            st.metric("المقابلات المجدولة", interviewed)
        with col3:
            st.metric("المرفوضين", rejected)
        with col4:
            st.metric("الاختبارات المكتملة", tested)
        with col5:
            st.metric("مرشحين ممتازين", high_score)

    def get_arabic_status(self, status: str) -> str:
        """تحويل الحالة إلى العربية"""
        status_map = {
            'received': 'مستلم',
            'interview_scheduled': 'مقابلة مجدولة',
            'rejected': 'مرفوض',
            'accepted': 'مقبول',
            'test_sent': 'تم إرسال الاختبار',
            'tested': 'تم إكمال الاختبار',
            'classified':'تم التصنيف'
        }
        return status_map.get(status, status)

    def ensure_google_auth(self):
        """
        غلاف رقيق: إذا تم تمييزه كمصادق بالفعل في الجلسة => إرجاع True.
        وإلا استدعاء google_services() إما لبدء تدفق OAuth (والذي سيتوقف st.stop())
        أو إنهائه (عند وجود الكود) وتعيين session_state وفقًا لذلك.
        """
        # إذا تم المصادقة بالفعل في الجلسة، تأكد من توفر الخدمات
        if st.session_state.get("google_authenticated"):
            return True
    
        try:
            # سيقوم هذا إما بـ:
            #  - عرض رابط المصادقة + st.stop() (إذا لم يكن هناك كود حاضر) OR
            #  - تبادل الكود وإرجاع الخدمات (إذا كان الكود حاضرًا / أو بيانات الاعتماد في الجلسة)
            gmail, calendar, drive, sheets, forms = google_services()
            # نجح -> وضع علامة على الجلسة كمصادقة
            st.session_state["google_authenticated"] = True
            # اختياريًا الاحتفاظ بعلم أو معلومات دنيا حول الخدمات؛ نتجنب تخزين كائنات العميل بشكل دائم
            st.session_state["google_services_ready"] = True
            return True
        except FileNotFoundError:
            st.error("⚠️ يرجى رفع ملف client_secret.json أولاً لتفعيل الدخول.")
            return False
        except Exception as e:
            # google_services تعرض بالفعل رسالة سهلة للمستخدم للعديد من الأخطاء
            return False

    def add_logout_button(self):
        """إضافة زر تسجيل الخروج لمسح المصادقة"""
        if st.sidebar.button("🚪 تسجيل الخروج"):
            # مسح حالة الجلسة
            if 'google_creds' in st.session_state:
                del st.session_state.google_creds
            
            # مسح ملف الرمز
            if os.path.exists("token.json"):
                os.remove("token.json")
            
            st.success("تم تسجيل الخروج بنجاح!")
            st.rerun()
    def display_candidate_details(self, candidate: Candidate, state=None):

        config = get_job_config()
        candidate_folder_id = self.get_candidate_folder_id(candidate)
    
        st.markdown(f"### 📋 تفاصيل المتقدم: {candidate.name or candidate.email}")
    
        # --- معلومات عامة ---
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**البريد الإلكتروني:** {candidate.email}")
            st.info(f"**المدينة:** {candidate.city or 'غير متوفر'}")
    
        with col2:
            if candidate.cv_score is not None:
                st.success(f"**تقييم السيرة الذاتية:** {candidate.cv_score}/100")
            if candidate.test_score is not None:
                st.success(f"**نتيجة الاختبار:** {candidate.test_score}/100")
            if candidate.overall_score is not None:
                st.success(f"**التقييم الكلي:** {candidate.overall_score}/100")
            st.success(f"**الوظيفة المتقدم لها:** {candidate.job_id or 'غير متوفر'}")
    
        # --- معلومات إضافية ---
        with st.expander("📊 معلومات إضافية"):
            col3, col4 = st.columns(2)
            with col3:
                st.write("**المؤهل العلمي:**", candidate.degree or "غير متوفر")
                st.write("**الخبرة:**", candidate.experience or "غير متوفر")
                st.write("**الشهادات:**", ", ".join(candidate.certifications) or "لا توجد")
            with col4:
                st.write("**معرّف الوظيفة (Job ID):**", candidate.job_id)
                if candidate_folder_id:
                    st.write("**مجلد المرشح على جوجل درايف:**",
                             f"[فتح المجلد](https://drive.google.com/drive/folders/{candidate_folder_id})")
    
        # --- قسم اختبار المرشح ---
        with st.expander("🧠 اختبار المرشح", expanded=False):
            st.write("يمكنك هنا عرض أو إرسال اختبار المرشح.")
            col_test1, col_test2 = st.columns(2)
    
            # --- عرض أسئلة الاختبار ---
            with col_test1:
                if st.button("📘 عرض أسئلة الاختبار", key=f"show_test_{candidate.email}"):
                    with st.spinner("جاري إنشاء أسئلة الاختبار..."):
                        try:
                            quiz = llm_json(
                                TEST_GEN_PROMPT.format(job_id=config['job_id']),
                                expect_list=True
                            ) or []
                            if quiz:
                                st.markdown("#### 📝 أسئلة الاختبار:")
                                for i, q in enumerate(quiz, start=1):
                                    qtxt = q.get("question") if isinstance(q, dict) else str(q)
                                    opts = q.get("options", []) if isinstance(q, dict) else []
                                    st.markdown(f"**{i}. {qtxt}**")
                                    if opts:
                                        for opt in opts:
                                            st.markdown(f"- {opt}")
                                    st.markdown("---")
                            else:
                                st.warning("لم يتم توليد أي أسئلة اختبار.")
                        except Exception as e:
                            st.error(f"حدث خطأ أثناء توليد الأسئلة: {e}")
    
            # --- إرسال الاختبار إلى المرشح ---
            with col_test2:
                if st.button("📤 إرسال الاختبار إلى المرشح", key=f"send_test_{candidate.email}"):
                    with st.spinner("جاري إرسال الاختبار إلى المرشح..."):
                        try:
                            success, form_link = self.node_send_tests(candidate)
                            logger.info(success)
                            if success:
                                #st.success(f"✅ تم إرسال الاختبار بنجاح إلى {candidate.name or candidate.email}!")
                                st.markdown(f"📎 [عرض اختبار المرشح]({form_link})")
                            else:
                                st.error("❌ فشل في إرسال الاختبار إلى هذا المرشح.")
                        except Exception as e:
                            st.error(f"حدث خطأ أثناء إرسال الاختبار: {e}")
    
        # --- قسم أسئلة المقابلة ---
        with st.expander("❓ أسئلة المقابلة", expanded=True):
            questions_content = self.get_interview_questions(candidate)
            if questions_content.startswith("Error") or "not found" in questions_content:
                st.info("لم يتم العثور على أسئلة مقابلة.")
            else:
                formatted_questions = self.format_questions_as_markdown(questions_content)
                st.markdown(formatted_questions)
    
        # --- إعادة إنشاء أسئلة المقابلة ---
        with st.expander("🔄 إعادة إنشاء أسئلة المقابلة"):
            st.write("**خيارات إنشاء الأسئلة:**")
            col1, col2 = st.columns(2)
    
            with col1:
                mode_options = {
                    "job_requirements": "إنشاء جديد حسب متطلبات الوظيفة فقط",
                    "cv": "إنشاء جديد حسب السيرة الذاتية",
                    "both": "إنشاء جديد حسب الاثنين معاً"
                }
    
                with st.form(key=f"regen_form_{candidate.email}"):
                    selected_mode = st.selectbox(
                        "اختر طريقة الإنشاء:",
                        options=list(mode_options.keys()),
                        format_func=lambda x: mode_options[x],
                        key=f"mode_{candidate.email}"
                    )
    
                    regenerate_btn = st.form_submit_button("🔄 إعادة إنشاء الأسئلة")
    
                    if regenerate_btn:
                        with st.spinner("جاري إنشاء أسئلة جديدة..."):
                            success = self.regenerate_interview_questions(candidate, mode=selected_mode)
                            if success:
                                st.success("تم إنشاء أسئلة جديدة بنجاح!")
                                st.rerun()
                            else:
                                st.error("فشل في إنشاء الأسئلة الجديدة")
    
            with col2:
                st.info("""
                **ملاحظة:** 
                - سيتم إنشاء أسئلة جديدة وحفظها في مجلد المرشح  
                - الأسئلة القديمة سيتم استبدالها  
                - يمكنك اختيار الأساس الذي تريد إنشاء الأسئلة عليه
                """)
    
        # --- التقرير الكامل ---
        with st.expander("📝 التقرير الكامل والتحليل"):
            report_content = self.get_candidate_report(candidate)
            if report_content.startswith("Error") or "not found" in report_content:
                st.info("لم يتم العثور على تقرير للمرشح.")
            else:
                st.markdown(f'<div class="report-section">{report_content}</div>', unsafe_allow_html=True)

def main():
    st.sidebar.title("📋 نظام التوظيف الذكي")

    # التأكد من عدم وجود ملف رمز ثابت على القرص (سلامة مزدوجة)
    if os.path.exists("token.json"):
        try:
            os.remove("token.json")
        except Exception:
            pass

    # تهيئة حالة الجلسة في التشغيل الأول
    if "initialized" not in st.session_state:
        # الحفاظ على هذا بحد أدنى بشكل متعمد وإعادة إنشاء أي شيء مطلوب لاحقًا
        st.session_state.clear()
        st.session_state.initialized = True
        st.session_state.google_authenticated = False
        st.session_state.page = "🏠 الصفحة الرئيسية"

    # إنشاء مثيل ATSApp (إعادة الإنشاء إذا تم مسحه)
    if "app_instance" not in st.session_state:
        st.session_state.app_instance = ATSApp()
    app = st.session_state.app_instance

    # إذا أعاد التوجيه من Google رمز "code"، أكمل المصادقة تلقائيًا عند إعادة التشغيل.
    params = st.query_params
    if not st.session_state.get("google_authenticated", False) and params.get("code"):
        # محاولة إنهاء تبادل OAuth (سيتعامل google_services مع تبادل الرمز)
        ok = app.ensure_google_auth()
        if ok:
            st.success("✅ تم تسجيل الدخول بنجاح! جاري التحميل...")
            st.balloons()
            # الآن متابعة إلى واجهة المستخدم الرئيسية للتطبيق
            st.rerun()
        else:
            st.error("❌ فشل إتمام تسجيل الدخول. تأكد من إعدادات OAuth (redirect URI) ثم حاول مجدداً.")
            # مسح المعلمات للسماح بإعادة المحاولة
            st.query_params.clear()

    # إذا لم يتم المصادقة بعد، عرض زر تسجيل الدخول (ينقر المستخدم على هذا لبدء OAuth)
    if not st.session_state.get("google_authenticated", False):
        st.title("🔐 تسجيل الدخول")
        st.write("يرجى تسجيل الدخول عبر Google للمتابعة إلى نظام التوظيف الذكي.")
        if st.button("تسجيل الدخول باستخدام Google"):
            # بدء تدفق OAuth. سيعرض google_services() رابط المصادقة وst.stop()
            app.ensure_google_auth()
            # ensure_google_auth سيتوقف إما st.stop() (إذا بدأ) أو يعود True (إذا كان الرمز حاضرًا بالفعل)
            return
        return

    # ---------------- واجهة المستخدم للتطبيق بعد تسجيل الدخول الناجح ----------------
    page = st.sidebar.radio(
        "اختر الصفحة:",
        ["🏠 الصفحة الرئيسية", "📊 لوحة التحكم"],
        index=["🏠 الصفحة الرئيسية", "📊 لوحة التحكم"].index(st.session_state.get("page", "🏠 الصفحة الرئيسية"))
    )
    st.session_state.page = page

    # مثال: التأكد من توفر الخدمات (يتم إنشاؤها في google_services ويتم الإشارة إليها بواسطة علم الجلسة)
    if st.session_state.get("google_services_ready"):
        st.sidebar.success("✅ تم تهيئة خدمات Google بنجاح")

    # --- الصفحة الرئيسية ---
    if page == "🏠 الصفحة الرئيسية":
        st.markdown('<h1 class="main-header">🏠 الصفحة الرئيسية</h1>', unsafe_allow_html=True)
        st.write("قم بإعداد الاتصال بالنظام قبل البدء في متابعة عملية التوظيف")

        with st.form("home_form"):
            st.subheader("📧 بيانات الموارد البشرية")
            hr_email = st.text_input("بريد الموارد البشرية (HR Email)", placeholder="أدخل البريد الإلكتروني للموارد البشرية")
            form_id = st.text_input("معرف نموذج Google Form", placeholder="أدخل معرف النموذج")

            st.subheader("🤖 إعداد الذكاء الاصطناعي")
            model_choice = st.selectbox("اختر نموذج الذكاء الاصطناعي:", ["Gemini", "OpenAI"])
            api_key = st.text_input("مفتاح API", type="password", placeholder="أدخل مفتاح API")
            

            submitted = st.form_submit_button("➡️ متابعة إلى لوحة التحكم")

            if submitted:
                if not hr_email or not form_id:
                    st.error("❌ يرجى إدخال بريد الموارد البشرية ومعرف النموذج.")
                elif not api_key:
                    st.error("❌ يرجى إدخال مفتاح الـ API.")
                else:
                    # حفظ ملف الاعتماد
                    save_to_env("FORM_ID", form_id) 
                    save_to_env("MODEL_TYPE", model_choice)
                    if model_choice=="Gemini":
                        save_to_env("GEMINI_API_KEY", api_key)
                    else:
                        save_to_env("OPENAI_API_KEY", api_key)
                    os.environ["HR_FROM_EMAIL"] = hr_email
                    os.environ["FORM_ID"] = form_id
                    os.environ["API_KEY"] = api_key
                    os.environ["MODEL_TYPE"] = model_choice

                    st.session_state["HR_FROM_EMAIL"] = hr_email
                    st.session_state["FORM_ID"] = form_id
                    st.session_state["API_KEY"] = api_key
                    st.session_state["MODEL_TYPE"] = model_choice

                    st.success("✅ تم حفظ البيانات بنجاح! يمكنك الانتقال إلى لوحة التحكم من الشريط الجانبي.")
                    st.balloons()

    # --- لوحة التحكم ---
    elif page == "📊 لوحة التحكم":
        st.markdown('<h1 class="main-header">📊 لوحة متابعة التوظيف</h1>', unsafe_allow_html=True)

        # التحقق من وجود الإعدادات الأساسية
        required_keys = ["HR_FROM_EMAIL", "FORM_ID", "API_KEY", "MODEL_TYPE"]
        if any(key not in st.session_state for key in required_keys):
            st.warning("⚠️ يرجى إدخال البيانات في الصفحة الرئيسية أولاً قبل الانتقال إلى لوحة التحكم.")
            st.stop()

        with st.sidebar:
            st.header("⚙️ إعدادات الوظيفة")  
            with st.form("config_form"):
                st.subheader("📄 تفاصيل الوظيفة")
                job_id = st.text_input("معرف الوظيفة", placeholder="أدخل معرف الوظيفة")

                enable_city_filter = st.checkbox(
                    "تفعيل تصفية المدن", 
                    value=st.session_state.get('enable_city_filter', True),
                    help="عند التفعيل، سيتم عرض المرشحين من المدن المحددة فقط"
                )
                st.session_state.enable_city_filter = enable_city_filter

                base_cities = ["مكة", "المدينة", "الرياض", "جدة", "الدمام", "الطائف"]
                current_job_cities = st.session_state.get('job_cities', [])
                all_city_options = list(set(base_cities + current_job_cities))

                job_cities = st.multiselect(
                    "🏙️ المدن المطلوبة",
                    all_city_options,
                    default=current_job_cities,
                    help="اختر المدن المطلوبة للوظيفة"
                )
                new_city = st.text_input("➕ أضف مدينة جديدة (اختياري):", placeholder="أدخل اسم مدينة جديدة")
                job_requirements = st.text_area("🧾 متطلبات الوظيفة", height=100, placeholder="أدخل متطلبات الوظيفة...")
                
                st.subheader("📈 حدود التقييم")
                interview_threshold = st.slider("\u200Fالحد الأدنى للمقابلة", 0, 100, int(os.getenv("INTERVIEW_THRESHOLD", 50)))
                evaluation_mode = st.selectbox(
                    "طريقة التقييم:",
                    ["تقييم السيرة الذاتية فقط", "تقييم السيرة الذاتية والاختبار"],
                    index=0 if os.getenv("EVALUATION_MODE", "cv_only") == "cv_only" else 1
                )
                
                if new_city and new_city.strip() and new_city.strip() not in job_cities:
                    job_cities.append(new_city.strip())
                st.session_state.job_cities = job_cities
         
                if st.form_submit_button("🚀 تشغيل البرنامج"):
                    # التحقق من الحقول المطلوبة
                    if not job_id:
                        st.error("❌ يرجى إدخال معرف الوظيفة")
                        st.stop()
                    
                    # تخزين المدن في حالة الجلسة
                    st.session_state.job_cities = job_cities
                    
                    # حفظ في البيئة وحالة الجلسة
                    save_to_env("JOB_ID", job_id) 
                    save_to_env("JOB_CITY", json.dumps(job_cities, ensure_ascii=False)) 
                    save_to_env("JOB_REQUIREMENTS", job_requirements)
                    save_to_env("INTERVIEW_THRESHOLD", str(interview_threshold))
                    save_to_env("EVALUATION_MODE", evaluation_mode)

                    # تعيين متغيرات البيئة فوراً
                    os.environ["JOB_ID"] = job_id
                    os.environ["JOB_CITY"] = json.dumps(job_cities, ensure_ascii=False)
                    os.environ["JOB_REQUIREMENTS"] = job_requirements
                    os.environ["EVALUATION_MODE"] = "cv_only" if evaluation_mode == "تقييم السيرة الذاتية فقط" else "cv_and_test"
                    os.environ["INTERVIEW_THRESHOLD"] = str(interview_threshold)
                    os.environ["EVALUATION_MODE"] = evaluation_mode
                    
                    # تحديث حالة الجلسة
                    st.session_state["JOB_ID"] = job_id
                    st.session_state["JOB_CITY"] = job_cities
                    st.session_state["JOB_REQUIREMENTS"] = job_requirements
                    st.session_state["EVALUATION_MODE"] = evaluation_mode

                    load_dotenv(override=True)
                    
                    job_config = {
                        "JOB_ID": job_id,
                        "JOB_CITY": json.dumps(job_cities, ensure_ascii=False),
                        "JOB_REQUIREMENTS": job_requirements,
                        "FORM_ID": os.getenv("FORM_ID", ""),
                        "INTERVIEW_THRESHOLD": str(interview_threshold),
                        "EVALUATION_MODE": "cv_only" if evaluation_mode == "تقييم السيرة الذاتية فقط" else "cv_and_test"
                    }

                    with st.spinner("جاري تشغيل خط التوظيف..."):
                        success = app.run_pipeline(job_config)
                        if success:
                            st.success("تم تنفيذ خط التوظيف بنجاح ✅")
                        else:
                            st.error("فشل تشغيل خط التوظيف ❌")
            
            # زر تحديث قائمة المرشحين
            if st.button("🔄 تحديث قائمة المرشحين"):
                services = app.get_google_services()
                if services:
                    candidates = app.get_candidates_from_sheet()
                    if candidates:
                        st.session_state.candidates = candidates
                        st.success(f"تم تحديث {len(candidates)} مرشح")
                    else:
                        st.warning("لم يتم العثور على مرشحين أو فشل تحميل البيانات")
                else:
                    st.error("فشل في تهيئة خدمات Google")
        
        # تبويبات لوحة التحكم
        tab1, tab2 = st.tabs(["📈 لوحة التحكم", "👥 إدارة المرشحين"])
        
        # الحصول على جميع المرشحين
        all_candidates = st.session_state.get('candidates', [])
        
        # تطبيق تصفية المدن إذا كانت مفعلة
        if st.session_state.enable_city_filter and st.session_state.job_cities:
            filtered_candidates = app.filter_candidates_by_city(all_candidates, st.session_state.job_cities)
            st.info(f"📍 تم تصفية المدن: {', '.join(st.session_state.job_cities)} - ({len(filtered_candidates)} من أصل {len(all_candidates)} مرشح)")
        else:
            filtered_candidates = all_candidates
            if st.session_state.enable_city_filter:
                st.info("📍 عرض جميع المرشحين (لم يتم تحديد مدن للتصفية)")
            else:
                st.info("📍 عرض جميع المرشحين (التصفية معطلة)")

        with tab1:
            st.header("نظرة عامة على خط التوظيف")
            if filtered_candidates:
                app.display_metrics(filtered_candidates)
                st.subheader("📊 حالة المرشحين")
                status_data = []
                for candidate in filtered_candidates:
                    status_data.append({
                        "الاسم": candidate.name or "غير معروف",
                        "البريد الإلكتروني": candidate.email,
                        "المدينة": candidate.city or "غير معروف",
                        "الحالة": app.get_arabic_status(candidate.status),
                        "تقييم السيرة": candidate.cv_score or 0,
                        "نتيجة الاختبار": candidate.test_score or 0,
                        "التقييم النهائي": candidate.overall_score or 0,
                        "الحالة النهائيه": candidate.final_evaluation
                    })
                if status_data:
                    df = pd.DataFrame(status_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # عرض ملخص التصفية
                    if len(filtered_candidates) != len(all_candidates):
                        st.info(f"💡 يتم عرض {len(filtered_candidates)} مرشح من أصل {len(all_candidates)} بعد التصفية")
            else:
                st.info("لا يوجد مرشحين. قم بتشغيل الخط أو التحديث.")

        with tab2:
            st.header("👥 إدارة المرشحين")
            if filtered_candidates:
                candidate_options = [f"{c.name or 'غير معروف'} - {c.email} - {c.city or 'غير معروف'}" for c in filtered_candidates]
                selected_index = st.selectbox(
                    "اختر مرشح:",
                    range(len(filtered_candidates)),
                    index=st.session_state.selected_candidate_index,
                    format_func=lambda x: candidate_options[x]
                )
                st.session_state.selected_candidate_index = selected_index
                if selected_index is not None:
                    selected_candidate = filtered_candidates[selected_index]
                    app.display_candidate_details(selected_candidate)
                
            else:    
                st.info("لا يوجد مرشحين. قم بتشغيل الخط أو التحديث.")


if __name__ == "__main__":
    main()
































































































