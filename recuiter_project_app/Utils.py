from typing import Any, Dict, List, Optional, Tuple
import base64
import os 
from models import *

from dotenv import load_dotenv
from config import get_job_config
load_dotenv()


HR_FROM_EMAIL = os.getenv("HR_FROM_EMAIL")  # optional From alias when sending emails

def _get_message_body(payload: Dict[str,Any]) -> str:
    """
    Extract a plain text body from Gmail message payload recursively.
    """
    if not payload:
        return ""
    body = ""
    mime = payload.get('mimeType','')
    if mime == 'text/plain' and payload.get('body',{}).get('data'):
        data = payload['body']['data']
        body += base64.urlsafe_b64decode(data.encode()).decode('utf-8', errors='ignore')
    parts = payload.get('parts',[]) or []
    for p in parts:
        body += _get_message_body(p)
    return body

def _send_gmail_direct(gmail, to: str, subject: str, text: str):
    config=get_job_config()
    from email.mime.text import MIMEText
    msg = MIMEText(text)
    msg['to'] = to
    msg['subject'] = subject
    if HR_FROM_EMAIL:
        msg['from'] = HR_FROM_EMAIL
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId='me', body={'raw': raw}).execute()


def save_to_env(key, value, env_path=".env"):
    """Save or update a key=value pair in .env file"""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    # Check if key already exists
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    
    if not found:
        lines.append(f"{key}={value}\n")
    
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    load_dotenv(override=True)
    os.environ[key] = value