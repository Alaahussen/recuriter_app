from typing import Any, Tuple
from googleapiclient.discovery import build
from google.oauth2 import service_account
import streamlit as st
import tempfile

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/forms.responses.readonly'
]

def google_services(uploaded_credentials: Any = None) -> Tuple[Any, Any, Any, Any, Any]:
    """
    Returns (gmail, calendar, drive, sheets, forms) service clients authorized for SCOPES.
    `uploaded_credentials` should be a Streamlit UploadedFile object or path to a service account JSON.
    """
    if uploaded_credentials is None:
        raise ValueError("Please upload a Service Account JSON file.")

    # Save temporarily if uploaded via Streamlit
    if hasattr(uploaded_credentials, "read"):
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(uploaded_credentials.read())
            credentials_path = tmp_file.name
    else:
        credentials_path = uploaded_credentials

    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES
    )

    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    forms = build('forms', 'v1', credentials=creds)

    return gmail, calendar, drive, sheets, forms
