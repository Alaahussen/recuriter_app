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
    Authorize Google APIs using pre-configured OAuth credentials.
    Regular users just click "Login with Google" - no technical setup needed.
    """
    creds = None
    token_path = "token.json"

    # Load saved token if available
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Use YOUR pre-configured credentials from Streamlit secrets
            client_config = {
                "web": {
                    "client_id": "1049951738822-tikfl78a21u8j8drca04b71ec4q2e3qo.apps.googleusercontent.com",
                    "client_secret": "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",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri":"https://oauth2.googleapis.com/token",
                    "redirect_uris": ["https://aicruiter.streamlit.app"]
                }
            }
            
            flow = Flow.from_client_config(client_config, scopes=SCOPES, 
                                         redirect_uri="https://aicruiter.streamlit.app")
            
            auth_url, _ = flow.authorization_url(prompt="consent")
            st.markdown(f"[👉 Click here to authorize with Google]({auth_url})")

            code = st.experimental_get_query_params().get("code")
            if code:
                flow.fetch_token(code=code[0])
                creds = flow.credentials
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())
                st.success("✅ Google account connected!")
                st.rerun()
            else:
                st.info("Please click the authorization link above.")
                st.stop()

    # Build and return services
    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    forms = build('forms', 'v1', credentials=creds)

    return gmail, calendar, drive, sheets, forms








