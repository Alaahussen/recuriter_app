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
    Authorize Google APIs using OAuth2 with Streamlit Secrets.
    Returns: (gmail, calendar, drive, sheets, forms)
    """
    creds = Non
    token_path = "token.json"

    # 1️⃣ Load saved token if available
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            #st.sidebar.success("✅ Using saved Google credentials")
        except Exception as e:
            st.warning(f"⚠️ Error loading saved token: {e}")

    # 2️⃣ If no valid creds, refresh or create new
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                st.sidebar.success("✅ Google credentials refreshed")
            except Exception as e:
                st.warning(f"⚠️ Could not refresh token: {e}")
                creds = None

        if not creds:
            # Try to get client config from Streamlit secrets
            try:
                client_config = {
                    "web": {
                        "client_id": "1049951738822-tikfl78a21u8j8drca04b71ec4q2e3qo.apps.googleusercontent.com",
                        "client_secret": "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",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri":"https://oauth2.googleapis.com/token",
                        "redirect_uris": ["https://aicruiter.streamlit.app"]
                    }
                }
                
                # Use the client config from secrets
                redirect_uri = "https://aicruiter.streamlit.app"
                flow = Flow.from_client_config(
                    client_config, 
                    scopes=SCOPES, 
                    redirect_uri=redirect_uri
                )
                
                # Generate authorization URL
                auth_url, _ = flow.authorization_url(
                    prompt="consent",
                    access_type="offline"
                )
                
                st.markdown("### 🔐 Google Authentication Required")
                st.markdown(f"""
                **To continue, please authorize this app with your Google account:**
                
                [👉 Click here to authorize Google access]({auth_url})
                
                After authorization, you'll be redirected back to this app.
                """)

                # ✅ UPDATED: Use st.query_params instead of st.experimental_get_query_params
                code = st.query_params.get("code")
                
                if code:
                    with st.spinner("🔄 Completing authorization..."):
                        flow.fetch_token(code=code)
                        creds = flow.credentials
                        
                        # Save token for future reuse
                        with open(token_path, "w") as token_file:
                            token_file.write(creds.to_json())
                        
                        st.success("✅ Google account connected successfully!")
                        st.rerun()
                else:
                    st.info("🔗 Please click the authorization link above to continue.")
                    st.stop()
                    
            except KeyError as e:
                st.error(f"""
                ❌ Missing required OAuth configuration: {e}
                
                **Please ensure your Streamlit secrets include:**
                - client_id
                - client_secret
                """)
                st.stop()
            except Exception as e:
                st.error(f"❌ OAuth configuration error: {str(e)}")
                st.stop()

    # 3️⃣ Build service clients
    try:
        gmail = build('gmail', 'v1', credentials=creds)
        calendar = build('calendar', 'v3', credentials=creds)
        drive = build('drive', 'v3', credentials=creds)
        sheets = build('sheets', 'v4', credentials=creds)
        forms = build('forms', 'v1', credentials=creds)
        
        #st.sidebar.success("✅ Google services initialized")
        return gmail, calendar, drive, sheets, forms
        
    except Exception as e:
        st.error(f"❌ Failed to initialize Google services: {str(e)}")
        st.stop()












