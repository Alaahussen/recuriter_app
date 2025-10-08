import os
import json
import streamlit as st
from typing import Any, Tuple
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

SCOPES = [
    #'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.readonly',      
    'https://www.googleapis.com/auth/gmail.send', 
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/forms.body.readonly',
    'https://www.googleapis.com/auth/forms.responses.readonly'
]

# ---------- google_services ----------
def google_services() -> Tuple[Any, Any, Any, Any, Any]:
    """
    Two-mode behavior:
      - If there's no 'code' query param and no in-session creds: generate auth_url, show link and stop.
      - If there's a 'code' query param (or creds already in session), exchange it and return service clients.
    DOES NOT save any token.json to disk (keeps creds only in session_state).
    """
    # Prefer credentials stored in session (kept only in memory for the running session)
    creds = None
    if st.session_state.get("creds_json"):
        try:
            creds = Credentials.from_authorized_user_info(json.loads(st.session_state["creds_json"]), SCOPES)
            # refresh if needed (still in-memory)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                st.session_state["creds_json"] = creds.to_json()
        except Exception:
            creds = None

    # Load client config (move to st.secrets in production if you prefer)
    client_config = {
        "web": {
            "client_id": "1049951738822-tikfl78a21u8j8drca04b71ec4q2e3qo.apps.googleusercontent.com",
            "client_secret": "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",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            # Make sure this redirect URI matches your OAuth client configuration in Google Cloud
            "redirect_uris": ["https://aicruiter.streamlit.app"]
        }
    }
    redirect_uri = client_config["web"]["redirect_uris"][0

    # Use the new st.query_params API
    params = st.query_params
    code = params.get("code")  # returns the first value if exists, else None

    # If we don't yet have credentials, either start OAuth (show link) or finish it using code
    if not creds:
        if code:
            # We have a code -> exchange it for tokens (complete OAuth)
            try:
                flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
                # Exchange the code for credentials
                flow.fetch_token(code=code)
                creds = flow.credentials

                # Keep credentials in-memory only (don't write token.json).
                st.session_state["creds_json"] = creds.to_json()

                # Clean up URL query params so we don't repeat exchange on subsequent reruns
                st.query_params.clear()
            except Exception as e:
                # Show the underlying error to help debugging (redirect mismatch / invalid code, etc.)
                st.error(f"❌ خطأ أثناء إتمام التفويض: {e}")
                raise
        else:
            # No code and no creds -> start OAuth: generate auth link and halt for the user to click it
            flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            st.markdown("### 🔐 Google Authentication Required")
            st.markdown(
                "اضغط على الرابط التالي لتفويض هذا التطبيق بالوصول إلى حساب Google الخاص بك:"
            )
            st.markdown(f"[👉 اكمل التفويض هنا]({auth_url})")
            st.info("بعد التفويض سيتم إعادة التوجيه إلى هذه الصفحة — انتظر إعادة التحميل.")
            # `st.stop()` halts execution here so user can click the link and return with ?code=...
            st.stop()

    # Build service clients using the in-memory credentials
    try:
        gmail = build("gmail", "v1", credentials=creds)
        calendar = build("calendar", "v3", credentials=creds)
        drive = build("drive", "v3", credentials=creds)
        sheets = build("sheets", "v4", credentials=creds)
        forms = build("forms", "v1", credentials=creds)
        return gmail, calendar, drive, sheets, forms
    except Exception as e:
        st.error(f"❌ فشل تهيئة خدمات Google: {e}")
        raise





