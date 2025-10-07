import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

# 1️⃣ Load environment variables from .env
load_dotenv(override=True)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/forms.responses.readonly'
]

def google_services():
    """
    Initialize Google API services using the credentials path
    stored in the .env file (CREDENTIALS_PATH).
    """
    creds_path = os.getenv("CREDENTIALS_PATH")
    if not creds_path or not os.path.exists(creds_path):
        raise FileNotFoundError(
            "CREDENTIALS_PATH not found in environment or file does not exist. "
            "Please upload your credentials and set the path in .env."
        )

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES
    )

    gmail = build('gmail', 'v1', credentials=creds)
    calendar = build('calendar', 'v3', credentials=creds)
    drive = build('drive', 'v3', credentials=creds)
    sheets = build('sheets', 'v4', credentials=creds)
    forms = build('forms', 'v1', credentials=creds)

    return gmail, calendar, drive, sheets, forms

