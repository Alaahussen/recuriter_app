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
    Authorize Google APIs using session-based tokens.
    Each user gets their own isolated session.
    """
    # Use session state instead of file
    if 'google_creds' in st.session_state:
        creds = st.session_state.google_creds
    else:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                st.session_state.google_creds = creds
            except:
                creds = None
                st.session_state.google_creds = None

        if not creds:
            # Get client config from secrets
            client_config = {
                "web": {
                    "client_id": "1049951738822-tikfl78a21u8j8drca04b71ec4q2e3qo.apps.googleusercontent.com",
                    "client_secret": "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",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri":"https://oauth2.googleapis.com/token",
                    "redirect_uris": ["https://aicruiter.streamlit.app"]
                }
            }
            
            flow = Flow.from_client_config(
                client_config, 
                scopes=SCOPES, 
                redirect_uri="https://aicruiter.streamlit.app"
            )
            
            # Get query parameters
            query_params = st.experimental_get_query_params()
            code = query_params.get("code")
            
            if code:
                # Exchange code for tokens
                flow.fetch_token(code=code[0])
                creds = flow.credentials
                st.session_state.google_creds = creds
                st.rerun()
            else:
                # Show login button
                auth_url, _ = flow.authorization_url(prompt="consent")
                st.markdown("### 🔐 Login Required")
                st.markdown(f"""
                **Please login with your Google account to continue:**
                
                [👉 Login with Google]({auth_url})
                """)
                st.stop()
    
    # Build services
    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    forms = build('forms', 'v1', credentials=creds
    
    return gmail, calendar, drive, sheets, forms








