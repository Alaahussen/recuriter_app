from typing import Any, Dict, List, Optional, Tuple
import base64
import os 
from models import *

from dotenv import load_dotenv
from config import get_job_config
from openai import OpenAI
import google.generativeai as genai
import logging
load_dotenv()


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")

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


def extract_city_from_form_data(form_data: dict) -> str:
    """
    Use an LLM (OpenAI or Gemini) to extract the city name from Google Form responses.
    Returns the detected city as a string, or an empty string if none found.
    """
    # Combine form answers into one text block
    text = "\n".join(f"{k}: {v}" for k, v in form_data.items())

    prompt = f"""
    From the following form responses, identify the candidate's city of residence.
    If no city is mentioned, respond with "None".

    Responses:
    {text}

    Return ONLY the city name (one word or short phrase), nothing else.
    """

    provider = os.getenv("MODEL_TYPE", "Gemini").lower()
    city = ""

    try:
        if provider == "gemini":
            # --- Google Gemini ---
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            city = response.text.strip()

        else:
            # --- OpenAI GPT ---
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a data extractor that finds cities from text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            city = response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"⚠️ City extraction failed: {e}")
        city = ""

    # Normalize result
    if city.lower() in ["none", "null", "not found", ""]:
        return ""
    return city
    
def assign_city_to_candidate(cand, form_data: dict):
    """
    Assigns the city field in the Candidate object using LLM extraction from form data.
    """
    city = extract_city_from_form_data(form_data)
    if city:
        cand.city = city
        logger.info(f"🌆 City extracted for {cand.email}: {city}")
    else:
        cand.city = ""
        logger.info(f"🚫 No city found for {cand.email}")


