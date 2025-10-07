from typing import Any, Tuple
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from google.auth.transport.requests import Request
import os
import json
import streamlit as st

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/forms.responses.readonly'
]

def google_services() -> Tuple[Any, Any, Any, Any, Any]:
    """
    Authorize Google APIs using OAuth2 with file upload option.
    Returns: (gmail, calendar, drive, sheets, forms)
    """
    creds = None
    token_path = "token.json"
    client_secret_path = "client_secret.json"

    # 1️⃣ Load saved token if available
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            st.sidebar.success("✅ تم تحميل بيانات الاعتماد المحفوظة من Google")
        except Exception as e:
            st.warning(f"⚠️ خطأ في تحميل التوكن المحفوظ: {e}")

    # 2️⃣ If no valid creds, refresh or create new
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                st.sidebar.success("✅ تم تجديد بيانات الاعتماد بنجاح")
            except Exception as e:
                st.warning(f"⚠️ تعذر تجديد التوكن: {e}")
                creds = None

        if not creds:
            # Check if client_secret.json exists, if not, allow upload
            if not os.path.exists(client_secret_path):
                st.error("⚠️ ملف client_secret.json غير موجود")
                
                # File upload option
                uploaded_file = st.file_uploader(
                    "📁 رفع ملف client_secret.json", 
                    type=["json"],
                    help="حمّل ملف client_secret.json من Google Cloud Console",
                    key="client_secret_uploader"
                )
                
                if uploaded_file is not None:
                    try:
                        # Validate the uploaded file
                        file_content = uploaded_file.getvalue().decode('utf-8')
                        json.loads(file_content)  # Test if valid JSON
                        
                        # Save the uploaded file
                        with open(client_secret_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                        st.success("✅ تم رفع الملف بنجاح! جاري التحميل...")
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("❌ الملف المرفوع ليس ملف JSON صالح")
                    except Exception as e:
                        st.error(f"❌ خطأ في رفع الملف: {e}")
                else:
                    st.info("""
                    **📋 تعليمات الحصول على الملف:**

                    1. **اذهب إلى [Google Cloud Console](https://console.cloud.google.com/)**
                    2. **أنشئ مشروع جديد أو اختر مشروع موجود**
                    3. **اذهب إلى "APIs & Services" > "Credentials"**
                    4. **انقر على "+ CREATE CREDENTIALS" > "OAuth 2.0 Client ID"**
                    5. **اختر "Web application" كنوع التطبيق**
                    6. **أضف عناوين URI التالية:**
                       - `https://aicruiter.streamlit.app`
                       - `http://localhost:8501`
                    7. **انقر على "CREATE" ثم "DOWNLOAD JSON"**
                    8. **حمّل الملف الذي تم تحميله كـ client_secret.json**
                    """)
                    st.stop()
            
            # Continue with OAuth flow using the client_secret.json file
            try:
                redirect_uri = "https://aicruiter.streamlit.app"
                
                # Create flow from the uploaded client_secret file
                flow = Flow.from_client_secrets_file(
                    client_secret_path, 
                    scopes=SCOPES, 
                    redirect_uri=redirect_uri
                )
                
                # Generate authorization URL
                auth_url, state = flow.authorization_url(
                    prompt="consent",
                    access_type="offline",
                    include_granted_scopes="true"
                )
                
                st.markdown("### 🔐 المصادقة مع Google مطلوبة")
                st.markdown(f"""
                **للمتابعة، يرجى تفويض هذا التطبيق باستخدام حساب Google الخاص بك:**
                
                [👉 انقر هنا للتفويض مع Google]({auth_url})
                
                بعد التفويض، سيتم إعادة توجيهك إلى هذا التطبيق.
                """)

                # Check for authorization code in URL parameters
                query_params = st.experimental_get_query_params()
                code = query_params.get("code")
                
                if code:
                    with st.spinner("🔄 جاري إكمال عملية التفويض..."):
                        # Exchange authorization code for tokens
                        flow.fetch_token(code=code[0])
                        creds = flow.credentials
                        
                        # Save token for future reuse
                        with open(token_path, "w") as token_file:
                            token_file.write(creds.to_json())
                        
                        st.success("✅ تم ربط حساب Google بنجاح!")
                        st.balloons()
                        st.rerun()  # Refresh to continue with authenticated state
                else:
                    st.info("🔗 يرجى النقر على رابط التفويض أعلاه للمتابعة.")
                    st.stop()
                    
            except Exception as e:
                st.error(f"❌ خطأ في عملية المصادقة: {str(e)}")
                # If there's an error, remove the problematic client_secret file
                if os.path.exists(client_secret_path):
                    os.remove(client_secret_path)
                st.stop()

    # 3️⃣ Build service clients
    try:
        gmail = build('gmail', 'v1', credentials=creds)
        calendar = build('calendar', 'v3', credentials=creds)
        drive = build('drive', 'v3', credentials=creds)
        sheets = build('sheets', 'v4', credentials=creds)
        forms = build('forms', 'v1', credentials=creds)
        
        st.sidebar.success("✅ تم تهيئة خدمات Google بنجاح")
        return gmail, calendar, drive, sheets, forms
        
    except Exception as e:
        st.error(f"❌ فشل في تهيئة خدمات Google: {str(e)}")
        st.stop()





