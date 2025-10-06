from typing import Any, Dict, List, Optional, Tuple
from googleapiclient.discovery import build
import logging
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os
from google.auth.transport.requests import Request

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
    Returns (gmail, calendar, drive, sheets, forms) service clients authorized for SCOPES.
    Uses credentials.json (OAuth client for Desktop) and saves token.json after first run.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError("credentials.json not found — create OAuth client in Google Cloud and download it.")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            # On local machine this will open your browser
            creds = flow.run_local_server(port=0, open_browser=True)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())

    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    forms = build('forms', 'v1', credentials=creds)
    return gmail, calendar, drive, sheets, forms
