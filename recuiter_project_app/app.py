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
from Utils import save_to_env
import io
import re
from googleapiclient.http import MediaIoBaseUpload
from config import *
from Featch_cv import normalize_arabic_text
# Import your existing functions
from Google_services import google_services
from Drive import (
    ensure_drive_folder, ensure_sheet, get_candidate_from_sheet,
    find_candidate_row_by_email, read_drive_file_text
)


# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="لوحة متابعة التوظيف",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
# Custom CSS - Enhanced for Arabic RTL
st.markdown("""
<style>
    /* Import Arabic font */
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap');
    
    /* RTL Base Styles for entire app */
    .main .block-container {
        direction: rtl;
        text-align: right;
        font-family: 'Tajawal', 'Segoe UI', sans-serif;
    }
    
    /* RTL for all text elements */
    .main-header, .metric-card, .candidate-card, .report-section,
    h1, h2, h3, h4, h5, h6, p, div, span, label {
        direction: rtl;
        text-align: right;
        font-family: 'Tajawal', 'Segoe UI', sans-serif;
    }
    
    .main-header {
        font-size: 3rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
        font-weight: 700;
    }
    
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem;
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    
    .candidate-card {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border-right: 4px solid #1f77b4;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .status-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.8rem;
        font-weight: bold;
    }
    
    .report-section {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    
    /* RTL for Streamlit specific components */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > div,
    .stMultiselect > div > div > div {
        direction: rtl;
        text-align: right;
        font-family: 'Tajawal', sans-serif;
    }
    
    /* RTL for buttons */
    .stButton > button {
        font-family: 'Tajawal', sans-serif;
    }
    
    /* RTL for radio buttons */
    .stRadio > label {
        direction: rtl;
        text-align: right;
        padding-right: 20px;
    }
    
    /* RTL for checkboxes */
    .stCheckbox > label {
        direction: rtl;
        text-align: right;
        padding-right: 20px;
    }
    
    /* RTL for sidebar */
    [data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
    }
    
    [data-testid="stSidebar"] .stRadio > label,
    [data-testid="stSidebar"] .stCheckbox > label,
    [data-testid="stSidebar"] .stButton > button {
        direction: rtl;
        text-align: right;
    }
    
    /* RTL for tabs */
    .stTabs [data-baseweb="tab-list"] {
        direction: rtl;
    }
    
    /* RTL for dataframes */
    .dataframe {
        direction: rtl;
    }
    
    .dataframe th {
        text-align: right !important;
    }
    
    /* RTL for alerts and info boxes */
    .stAlert {
        direction: rtl;
        text-align: right;
    }
    
    /* RTL for form labels */
    .stForm {
        direction: rtl;
    }
    
    /* RTL for selectbox dropdown */
    .stSelectbox [data-baseweb="select"] div {
        text-align: right;
    }
    
    /* RTL for multiselect */
    .stMultiSelect [data-baseweb="select"] div {
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

class ATSApp:
    def __init__(self):
        self.workflow = None
        self.state = None
        self.sheet_id = None
        self.drive_folder_id = None
        self.send_tests_enabled = True  # default
        
        # Initialize session state
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
        """Normalize city names for better matching"""
        if not city:
            return ""
        
        city = str(city).strip()
        
        # Common city variations and normalizations
        city_variations = {
            # Arabic variations
            'مكه': 'مكة',
            'مكّه': 'مكة',
            'مكة المكرمة': 'مكة',
            'المدينة المنورة': 'المدينة',
            'الرياض': 'الرياض',
            'جده': 'جدة',
            'جدّه': 'جدة',
            'الدمام': 'الدمام',
            'الطائف': 'الطائف',
            # English variations
            'makkah': 'مكة',
            'mecca': 'مكة',
            'madina': 'المدينة',
            'medina': 'المدينة',
            'riyadh': 'الرياض',
            'jeddah': 'جدة',
            'dammam': 'الدمام',
            'taif': 'الطائف'
        }
        
        # Normalize Arabic text
        city =normalize_arabic_text(city)
        
        # Convert to lowercase for comparison
        city_lower = city.lower()
        
        # Check for variations
        for variation, normalized in city_variations.items():
            if variation in city_lower or city_lower in variation:
                return normalized
        
        return city
    
    def cities_match(self, candidate_city: str, selected_cities: List[str]) -> bool:
        """Check if candidate city matches any selected city"""
        if not candidate_city or not selected_cities:
            return False
        
        normalized_candidate_city = self.normalize_city_name(candidate_city)
        
        for selected_city in selected_cities:
            normalized_selected = self.normalize_city_name(selected_city)
            
            # Exact match
            if normalized_candidate_city == normalized_selected:
                return True
            
            # Substring match (more flexible)
            if (normalized_selected in normalized_candidate_city or 
                normalized_candidate_city in normalized_selected):
                return True
            
            # Check for common abbreviations or variations
            if self.are_cities_similar(normalized_candidate_city, normalized_selected):
                return True
        
        return False
    
    def are_cities_similar(self, city1: str, city2: str) -> bool:
        """Check if two city names are similar"""
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
        
        # Check if they are direct matches in aliases
        for main_city, aliases in common_aliases.items():
            if (city1_norm == main_city and city2_norm in aliases) or \
               (city2_norm == main_city and city1_norm in aliases):
                return True
        
        return False
    
    def filter_candidates_by_city(self, candidates: List[Candidate], selected_cities: List[str]) -> List[Candidate]:
        """Filter candidates by city if filtering is enabled"""
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
            self.workflow = build_graph(send_tests_enabled=self.send_tests_enabled)
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
            # FIX: Get job_id from environment or session state consistently
            job_id = os.getenv("JOB_ID") or st.session_state.get("JOB_ID")
            if not job_id:
                st.error("❌ لم يتم العثور على معرف الوظيفة (JOB_ID). يرجى تعبئة الحقول أولاً.")
                return None

            # FIX: Ensure job_id is not None in folder name
            drive_folder_name = f"ATS/{job_id}"
            sheet_title = f"ATS_Candidates_{job_id}"  # FIX: Make sheet name unique per job
            
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
            # FIX: Clear previous candidates when starting new pipeline
            st.session_state.candidates = []
            
            # FIX: Ensure all job config values are set
            for key, value in job_config.items():
                if value:  # Only set if value is not empty
                    os.environ[key] = value
                    st.session_state[key] = value
            
            # FIX: Verify JOB_ID is set before proceeding
            if not os.getenv("JOB_ID"):
                st.error("❌ JOB_ID غير محدد. يرجى تعبئة الحقول أولاً.")
                return False
                
            sheet_id = self.setup_infrastructure()
            if not sheet_id:
                st.error("فشل في إعداد Google infrastructure")
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
                    # Ensure scores are numbers, not None
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
                        cv_score=float(cv_score) if cv_score is not None else 0.0,
                        test_score=float(test_score) if test_score is not None else 0.0,
                        overall_score=float(overall_score) if overall_score is not None else 0.0,
                    )
                    candidates.append(candidate)
            
            return candidates
            
        except Exception as e:
            st.error(f"Error reading from Google Sheets: {str(e)}")
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
            st.error(f"Failed to get/create candidate folder for {candidate.email}: {str(e)}")
            return ""
    
    def get_interview_questions(self, candidate: Candidate) -> str:
        services = self.get_google_services()
        if not services:
            return "Google services not initialized."
        
        gmail, calendar, drive, sheets, forms = services
        
        candidate_folder_id = self.get_candidate_folder_id(candidate)
        if not candidate_folder_id:
            return "No drive folder available for this candidate."
        
        try:
            query = f"'{candidate_folder_id}' in parents and (name contains 'interview_questions' or name contains 'questions') and trashed = false"
            results = drive.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            
            for file in files:
                content = read_drive_file_text(drive, file['id'], file['name'])
                if content:
                    return content
            
            return "No interview questions found in candidate's folder."
                
        except Exception as e:
            return f"Error loading interview questions: {str(e)}"

    def get_candidate_report(self, candidate: Candidate) -> str:
        services = self.get_google_services()
        if not services:
            return "Google services not initialized."
        
        gmail, calendar, drive, sheets, forms = services
        
        candidate_folder_id = self.get_candidate_folder_id(candidate)
        if not candidate_folder_id:
            return "No drive folder available for this candidate."
        
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
            return "No readable report files found in candidate's folder."
                
        except Exception as e:
            return f"Error loading report: {str(e)}"
    
    def format_report_as_markdown(self, data: Dict) -> str:
        """Format JSON report as well-structured markdown"""
        md = "# Candidate Report\n\n"
        
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
        """Format plain text report with better structure"""
        lines = content.split('\n')
        md = "# Candidate Report\n\n"
        
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
        """Format interview questions with proper markdown"""
        lines = content.split('\n')
        md = "# Interview Questions\n\n"
        
        question_number = 1
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(keyword in line.lower() for keyword in ['question', 'q:']):
                md += f"## Question {question_number}\n\n{line}\n\n"
                question_number += 1
            else:
                md += f"{line}\n\n"
        
        return md
    
    def reset_job_inputs(self):
        """Reset only job-related info"""
        for key in ["JOB_ID", "JOB_CITY", "JOB_REQUIREMENTS"]:
            if key in st.session_state:
                del st.session_state[key]
        # Also reset candidate list
        st.session_state.candidates = []
    
    def regenerate_interview_questions(self, candidate: Candidate, mode: str = "both") -> bool:
        """Regenerate interview questions based on the selected mode (cv / job_requirements / both)."""
        try:
            services = self.get_google_services()
            if not services:
                return False

            gmail, calendar, drive, sheets, forms = services

            job_requirements = os.getenv("JOB_REQUIREMENTS", "")
            job_id = os.getenv("JOB_ID", "")

            # Build prompt strictly based on mode
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

            # Final combined prompt
            prompt = f"""
            {prompt_intro}

            قم بإنشاء 6 أسئلة مقابلة مهنية مختصرة ومحددة للدور.
            يجب أن تكون جميع الأسئلة باللغة العربية فقط.
            أعد النتيجة على شكل مصفوفة JSON فقط مثل:
            ["سؤال 1", "سؤال 2", "سؤال 3", "سؤال 4", "سؤال 5", "سؤال 6"]

            {source_text}
                    """.strip()

            # Generate response from LLM
            llm_response = llm_json(prompt)

            # Extract questions safely
            if isinstance(llm_response, list):
                new_questions = llm_response
            elif isinstance(llm_response, dict):
                new_questions = list(llm_response.values())[0] if llm_response else []
            else:
                new_questions = []

            if not new_questions:
                st.error("فشل في استخراج الأسئلة من الاستجابة.")
                return False

            # Save to Drive
            candidate_folder_id = self.get_candidate_folder_id(candidate)
            if not candidate_folder_id:
                return False

            # Delete old question files
            self.delete_old_question_files(drive, candidate_folder_id)

            # Save new file
            content = io.BytesIO("\n".join(new_questions).encode("utf-8"))
            media = MediaIoBaseUpload(content, mimetype="text/plain", resumable=False)
            meta = {"name": f"interview_questions_{candidate.email}.txt", "parents": [candidate_folder_id]}
            drive.files().create(body=meta, media_body=media, fields="id, webViewLink").execute()

            # Update candidate object
            candidate.interview_questions = new_questions

            return True

        except Exception as e:
            st.error(f"Error regenerating questions: {str(e)}")
            return False

    def delete_old_question_files(self, drive, candidate_folder_id: str):

        """Delete existing question files"""
        try:
            query = f"'{candidate_folder_id}' in parents and (name contains 'interview_questions' or name contains 'questions') and trashed = false"
            results = drive.files().list(q=query, fields="files(id)").execute()
            
            for file in results.get('files', []):
                drive.files().delete(fileId=file['id']).execute()
                
        except Exception as e:
            print(f"Warning: Could not delete old question files: {e}")
    
    def display_metrics(self, candidates: List[Candidate]):
        col1, col2, col3, col4, col5 = st.columns(5)
        
        total_candidates = len(candidates)
        interviewed = len([c for c in candidates if c.status == 'interview_scheduled'])
        rejected = len([c for c in candidates if c.status == 'rejected'])
        tested = len([c for c in candidates if c.test_score is not None])
        
        with col1:
            st.metric("Total Candidates", total_candidates)
        with col2:
            st.metric("Interviews Scheduled", interviewed)
        with col3:
            st.metric("Rejected", rejected)
        with col4:
            st.metric("Tests Completed", tested)

    def ensure_google_auth(self):
        """
        Thin wrapper: if already marked authenticated in session => return True.
        Otherwise call google_services() to either start the OAuth flow (which will st.stop())
        or finish it (when code present) and set session_state accordingly.
        """
        # If already authenticated in session, ensure services are available
        if st.session_state.get("google_authenticated"):
            return True
    
        try:
            # This will either:
            #  - show auth link + st.stop() (if no code present) OR
            #  - exchange code and return services (if code present / or creds in session)
            gmail, calendar, drive, sheets, forms = google_services()
            # successful -> mark session as authenticated
            st.session_state["google_authenticated"] = True
            # Optionally keep a flag or minimal info about services; we avoid storing client objects permanently
            st.session_state["google_services_ready"] = True
            return True
        except FileNotFoundError:
            st.error("⚠️ يرجى رفع ملف client_secret.json أولاً لتفعيل الدخول.")
            return False
        except Exception as e:
            # google_services already shows a user-friendly message for many errors
            return False
    def add_logout_button(self):
        """Add a logout button to clear authentication"""
        if st.sidebar.button("🚪 Logout"):
            # Clear session state
            if 'google_creds' in st.session_state:
                del st.session_state.google_creds
            
            # Clear token file
            if os.path.exists("token.json"):
                os.remove("token.json")
            
            st.success("Logged out successfully!")
            st.rerun()

    def display_candidate_details(self, candidate: Candidate):
        candidate_folder_id = self.get_candidate_folder_id(candidate)
        
        st.markdown(f"### 📋 تفاصيل المتقدم: {candidate.name or candidate.email}")
        
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
        
        with st.expander("📊 معلومات إضافية"):
            col3, col4 = st.columns(2)
            with col3:
                st.write("**المؤهل العلمي:**", candidate.degree or "غير متوفر")
                st.write("**الخبرة:**", candidate.experience or "غير متوفر")
                st.write("**الشهادات:**", ", ".join(candidate.certifications) or "لا توجد")
            with col4:
                st.write("**معرّف الوظيفة (Job ID):**", candidate.job_id)
                if candidate_folder_id:
                    st.write("**مجلد المرشح على جوجل درايف:**", f"[فتح المجلد](https://drive.google.com/drive/folders/{candidate_folder_id})")
        
        # Interview Questions Section
        with st.expander("❓ أسئلة المقابلة", expanded=True):
            questions_content = self.get_interview_questions(candidate)
            if questions_content.startswith("Error") or "not found" in questions_content:
                st.info("لم يتم العثور على أسئلة مقابلة.")
            else:
                formatted_questions = self.format_questions_as_markdown(questions_content)
                st.markdown(formatted_questions)
        
        # Regenerate Questions Section - FIXED INDENTATION
        with st.expander("🔄 إعادة إنشاء أسئلة المقابلة"):
            st.write("**خيارات إنشاء الأسئلة:**")
            col1, col2 = st.columns(2)
        
            with col1:
                mode_options = {
                    "job_requirements": "إنشاء جديد حسب متطلبات الوظيفة فقط",
                    "cv": "إنشاء جديد حسب السيرة الذاتيه",
                    "both": "إنشاء جديد حسب الاثنين معاً"
                }

                # ✅ Wrap in form to avoid re-run conflict
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

        with st.expander("📝 التقرير الكامل والتحليل"):
            report_content = self.get_candidate_report(candidate)
            if report_content.startswith("Error") or "not found" in report_content:
                st.info("لم يتم العثور على تقرير للمرشح.")
            else:
                st.markdown(f'<div class="report-section">{report_content}</div>', unsafe_allow_html=True)


def main():
    st.sidebar.title("📋 نظام التوظيف الذكي")

    # Ensure no persistent token file exists on disk (double-safety)
    if os.path.exists("token.json"):
        try:
            os.remove("token.json")
        except Exception:
            pass

    # Initialize session state on first run
    if "initialized" not in st.session_state:
        # Intentionally keep this minimal and re-create anything needed afterwards
        st.session_state.clear()
        st.session_state.initialized = True
        st.session_state.google_authenticated = False
        st.session_state.page = "🏠 الصفحة الرئيسية"

    # Create ATSApp instance (recreate if cleared)
    if "app_instance" not in st.session_state:
        st.session_state.app_instance = ATSApp()
    app = st.session_state.app_instance

    # If the Google redirect returned a "code", complete auth automatically on rerun.
    params = st.query_params
    if not st.session_state.get("google_authenticated", False) and params.get("code"):
        # Attempt to finish the OAuth exchange (google_services will handle token exchange)
        ok = app.ensure_google_auth()
        if ok:
            st.success("✅ تم تسجيل الدخول بنجاح! جاري التحميل...")
            st.balloons()
            # Now continue to the main app UI
            st.rerun()
        else:
            st.error("❌ فشل إتمام تسجيل الدخول. تأكد من إعدادات OAuth (redirect URI) ثم حاول مجدداً.")
            # clear params to allow retry
            st.query_params.clear()

    # If still not authenticated, show the login button (user clicks this to start OAuth)
    if not st.session_state.get("google_authenticated", False):
        st.title("🔐 تسجيل الدخول")
        st.write("يرجى تسجيل الدخول عبر Google للمتابعة إلى نظام التوظيف الذكي.")
        if st.button("تسجيل الدخول باستخدام Google"):
            # Start the OAuth flow. google_services() will show the auth link and st.stop()
            app.ensure_google_auth()
            # ensure_google_auth will either st.stop() (if starting) or return True (if already code present)
            return
        return

    # ---------------- App UI after successful login ----------------
    page = st.sidebar.radio(
        "اختر الصفحة",
        ["🏠 الصفحة الرئيسية", "📊 لوحة التحكم"],
        index=["🏠 الصفحة الرئيسية", "📊 لوحة التحكم"].index(st.session_state.get("page", "🏠 الصفحة الرئيسية"))
    )
    st.session_state.page = page

    # Example: ensure services are available (they are created in google_services and indicated by session flag)
    if st.session_state.get("google_services_ready"):
        st.sidebar.success("✅ تم تهيئة خدمات Google بنجاح")

    # --- الصفحة الرئيسية ---
    if page == "🏠 الصفحة الرئيسية":
        st.markdown('<h1 class="main-header">🏠 الصفحة الرئيسية</h1>', unsafe_allow_html=True)
        st.write("قم بإعداد الاتصال بالنظام قبل البدء في متابعة عملية التوظيف")

        with st.form("home_form"):
            st.subheader("📧 بيانات الموارد البشرية")
            hr_email = st.text_input("بريد الموارد البشرية (HR Email)")
            form_id = st.text_input("معرف نموذج Google Form")

            st.subheader("🤖 إعداد الذكاء الاصطناعي")
            model_choice = st.selectbox("اختر نموذج الذكاء الاصطناعي:", ["Gemini", "OpenAI"])
            api_key = st.text_input("API Key", type="password")
            

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
                job_id = st.text_input("معرف الوظيفة")

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
                    default=current_job_cities
                )
                new_city = st.text_input("➕ أضف مدينة جديدة (اختياري):")
                job_requirements = st.text_area("🧾 متطلبات الوظيفة", height=100)

                st.subheader("🧠 خيارات الاختبار")
                send_tests_enabled = st.radio("هل تريد إرسال اختبارات للمرشحين؟", ["نعم", "لا"], index=0)
                app.send_tests_enabled = True if send_tests_enabled == "نعم" else False

                st.subheader("📈 حدود التقييم")
                interview_threshold = st.slider("الحد الأدنى للمقابلة", 0, 100, int(os.getenv("INTERVIEW_THRESHOLD", 50)))
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
                    #save_to_env("HR_FROM_EMAIL", hr_email)

                    # تعيين متغيرات البيئة فوراً
                    os.environ["JOB_ID"] = job_id
                    os.environ["JOB_CITY"] = json.dumps(job_cities, ensure_ascii=False)
                    os.environ["JOB_REQUIREMENTS"] = job_requirements
                    os.environ["EVALUATION_MODE"] = "cv_only" if evaluation_mode == "تقييم السيرة الذاتية فقط" else "cv_and_test"
                    os.environ["INTERVIEW_THRESHOLD"] = str(interview_threshold)
                    #os.environ["HR_FROM_EMAIL"] = hr_email
                    
                    # تحديث حالة الجلسة
                    st.session_state["JOB_ID"] = job_id
                    st.session_state["JOB_CITY"] = job_cities
                    st.session_state["JOB_REQUIREMENTS"] = job_requirements
                    #st.session_state["HR_FROM_EMAIL"] = hr_email

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
                st.subheader("📅 حالة المرشحين")
                status_data = []
                for candidate in filtered_candidates:
                    status_data.append({
                        "المرشح": candidate.name or candidate.email,
                        "المدينة": candidate.city or "غير معروف",
                        "الحالة": candidate.status,
                        "تقييم السيرة الذاتية": candidate.cv_score or 0,
                        "تقييم الاختبار": candidate.test_score or 0,
                        "التقييم الكلي": candidate.overall_score or 0
                    })
                if status_data:
                    df = pd.DataFrame(status_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # Show filtering summary
                    if len(filtered_candidates) != len(all_candidates):
                        st.info(f"💡 يتم عرض {len(filtered_candidates)} مرشح من أصل {len(all_candidates)} بعد التصفية")
            else:
                st.info("لا يوجد مرشحين. قم بتشغيل الخط أو التحديث.")

        with tab2:
            st.header("إدارة المرشحين")
            if filtered_candidates:
                candidate_options = [f"{c.name or 'غير معروف'} ({c.email}) - {c.city or 'غير معروف'}" for c in filtered_candidates]
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













































