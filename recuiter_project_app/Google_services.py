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
    Authorize Google APIs using OAuth2.
    Works with client_secret.json and stores token.json for future use.
    Returns: (gmail, calendar, drive, sheets, forms)
    """

    creds = None
    token_path = "token.json"
    client_secret_path = "client_secret.json"

    # 1️⃣ Load saved token if available
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # 2️⃣ If no valid creds, refresh or create new
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(client_secret_path):
                raise FileNotFoundError("client_secret.json not found. Please upload it or configure your app credentials.")

            # Streamlit-specific: redirect URI
            redirect_uri = "https://aicruiter.streamlit.app"
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # only for local dev

            # Check if running inside Streamlit (web) or local
            if st._is_running_with_streamlit:
                flow = Flow.from_client_secrets_file(client_secret_path, scopes=SCOPES, redirect_uri=redirect_uri)
                auth_url, _ = flow.authorization_url(prompt="consent")
                st.markdown(f"[👉 Click here to authorize Google access]({auth_url})")

                # Wait for authorization code (Streamlit URL param)
                code = st.experimental_get_query_params().get("code")
                if code:
                    flow.fetch_token(code=code[0])
                    creds = flow.credentials
                    # Save token for future reuse
                    with open(token_path, "w") as token_file:
                        token_file.write(creds.to_json())
                    st.success("✅ Google account connected successfully!")
                else:
                    st.stop()  # pause app until authorization
            else:
                # Fallback: local InstalledAppFlow (for development)
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())

    # 3️⃣ Build service clients
    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    forms = build('forms', 'v1', credentials=creds)

    return gmail, calendar, drive, sheets, forms



