from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple
import os
import re 
import logging
from Google_services import google_services

from Drive import *
from Utils import _send_gmail_direct 
from models import *

from dotenv import load_dotenv
from config import get_job_config
import openai
from google.generativeai import GenerativeModel
import google.generativeai as genai
from Utils import *

logger = logging.getLogger(__name__)
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")

def node_bootstrap(state: PipelineState) -> PipelineState
    config=get_job_config()
    gmail, calendar, drive, sheets, forms = google_services()
    state.calendar_id = config['calendar_id']
    
    # FIX: Validate job_id before creating folders
    job_id = config.get('job_id') or os.getenv("JOB_ID")
    if not job_id:
        logger.error("Job ID not found in config or environment")
        return state
    
    # FIX: Use consistent folder naming
    drive_folder_name = f"ATS/{job_id}"
    sheet_title = f"ATS_Candidates_{job_id}"
    
    folder_id = ensure_drive_folder(drive, drive_folder_name)
    sheet_id = ensure_sheet(sheets, drive, sheet_title, folder_id)
    
    state.drive_folder_id = folder_id
    state.sheet_id = sheet_id
    logger.info(f"Bootstrap complete: drive_folder={folder_id} sheet={sheet_id}")
    return state

def normalize_arabic_text(t: str) -> str:
        if not t:
            return ""
        t = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', t)
        t = re.sub(r'[إأآٱا]', 'ا', t)
        t = re.sub(r'[يى]', 'ي', t)
        t = t.replace('ة', 'ه').replace('ؤ', 'و').replace('ئ', 'ي')
        t = re.sub(r'[^\u0600-\u06FFa-zA-Z0-9\s]', '', t)
        t = re.sub(r'\s+', ' ', t).strip().lower()
        return t


def intelligent_job_match(text: str, job_id: str) -> bool:
    """
    Intelligent job ID matching using only regex and text normalization (no LLM).
    Supports Arabic and English text matching with multiple fallback strategies.
    """
    if not text or not job_id:
        return False

    # --------------------------------------------------
    # 1️⃣ Normalize Arabic & English text
    # --------------------------------------------------
    text_norm = normalize_arabic_text(text)
    job_norm = normalize_arabic_text(job_id)

    # Convert to lowercase for case-insensitive matching
    text_lower = text_norm.lower()
    job_lower = job_norm.lower()

    # --------------------------------------------------
    # 2️⃣ Exact match (fastest)
    # --------------------------------------------------
    if job_lower in text_lower:
        logger.info(f"✅ EXACT MATCH: Found '{job_id}' in text")
        return True

    # --------------------------------------------------
    # 3️⃣ Regex-based search with job context
    # --------------------------------------------------
    escaped_job = re.escape(job_norm)
    
    # Arabic job context patterns
    arabic_patterns = [
        rf"(?:وظيفه|وظيفة|طلب|تقدم|للوظيفة|للوظيفه|لشغل)\s*{escaped_job}",
        rf"{escaped_job}\s*(?:وظيفه|وظيفة|مطلوب|ممكن|متاح)",
        rf"(?:لدي|عندي|أبحث عن|ارغب في)\s*{escaped_job}"
    ]
    
    # English job context patterns  
    english_patterns = [
        rf"(?:job|position|role|application|apply for)\s*{escaped_job}",
        rf"{escaped_job}\s*(?:job|position|role|vacancy|opening)",
        rf"(?:looking for|interested in|apply for)\s*{escaped_job}"
    ]

    flags = re.UNICODE | re.IGNORECASE

    # Check Arabic patterns
    for pattern in arabic_patterns:
        if re.search(pattern, text_norm, flags):
            logger.info(f"✅ ARABIC CONTEXT MATCH: Found '{job_id}' with job context")
            return True

    # Check English patterns
    for pattern in english_patterns:
        if re.search(pattern, text_norm, flags):
            logger.info(f"✅ ENGLISH CONTEXT MATCH: Found '{job_id}' with job context")
            return True

    # --------------------------------------------------
    # 4️⃣ Word boundary matching
    # --------------------------------------------------
    word_boundary_pattern = rf"\b{re.escape(job_lower)}\b"
    if re.search(word_boundary_pattern, text_lower, flags):
        logger.info(f"✅ WORD BOUNDARY MATCH: Found '{job_id}' as separate word")
        return True

    # --------------------------------------------------
    # 5️⃣ Arabic word-based matching
    # --------------------------------------------------
    arabic_words = re.findall(r'[\u0600-\u06FF]{2,}', job_norm)  # At least 2 Arabic characters
    if arabic_words:
        text_arabic_words = set(re.findall(r'[\u0600-\u06FF]{2,}', text_norm))
        
        # Check if all Arabic words from job_id are in text
        found_all_words = all(word in text_arabic_words for word in arabic_words)
        if found_all_words:
            logger.info(f"✅ ARABIC WORDS MATCH: All Arabic words from '{job_id}' found in text")
            return True
        
        # Check if majority of Arabic words are present
        found_words = sum(1 for word in arabic_words if word in text_arabic_words)
        if found_words >= len(arabic_words) * 0.7:  # 70% threshold
            logger.info(f"✅ ARABIC PARTIAL MATCH: {found_words}/{len(arabic_words)} words from '{job_id}' found")
            return True

    # --------------------------------------------------
    # 6️⃣ Common job title variations and abbreviations
    # --------------------------------------------------
    common_variations = {
        # Arabic variations
        'مطور': ['مطور برامج', 'مبرمج', 'مطور ويب'],
        'مبرمج': ['مطور', 'مطور برامج', 'مبرمج ويب'],
        'مصمم': ['مصمم جرافيك', 'مصمم ويب'],
        'مدير': ['مدير مشروع', 'مدير فريق'],
        'مهندس': ['مهندس برمجيات', 'مهندس نظم'],
        
        # English variations
        'developer': ['software developer', 'web developer'],
        'programmer': ['developer', 'software programmer'],
        'designer': ['graphic designer', 'web designer'],
        'manager': ['project manager', 'team manager'],
        'engineer': ['software engineer', 'systems engineer']
    }
    
    # Check for variations of the job_id
    if job_lower in common_variations:
        for variation in common_variations[job_lower]:
            if variation.lower() in text_lower:
                logger.info(f"✅ JOB VARIATION MATCH: Found variation '{variation}' for '{job_id}'")
                return True

    # --------------------------------------------------
    # 7️⃣ Split and match for multi-word job titles
    # --------------------------------------------------
    job_words = job_lower.split()
    if len(job_words) > 1:
        # Check if all words are present (order doesn't matter)
        text_words_set = set(text_lower.split())
        found_all = all(word in text_words_set for word in job_words)
        if found_all:
            logger.info(f"✅ MULTI-WORD MATCH: All words from '{job_id}' found in text")
            return True
        
        # Check if majority of words are present
        found_count = sum(1 for word in job_words if word in text_words_set)
        if found_count >= len(job_words) * 0.7:  # 70% threshold
            logger.info(f"✅ MULTI-WORD PARTIAL MATCH: {found_count}/{len(job_words)} words from '{job_id}' found")
            return True

    # --------------------------------------------------
    # 8️⃣ Remove common stop words and try again
    # --------------------------------------------------
    stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but', 'ال', 'في', 'على', 'إلى', 'من', 'و', 'أو'}
    job_words_clean = [word for word in job_lower.split() if word not in stop_words and len(word) > 2]
    
    if job_words_clean:
        text_words_clean = [word for word in text_lower.split() if word not in stop_words and len(word) > 2]
        text_words_set_clean = set(text_words_clean)
        
        found_clean = all(word in text_words_set_clean for word in job_words_clean)
        if found_clean:
            logger.info(f"✅ CLEANED WORDS MATCH: Found '{job_id}' after removing stop words")
            return True

    # --------------------------------------------------
    # Final fallback: Simple substring without context
    # --------------------------------------------------
    words_in_job = job_lower.split()
    if len(words_in_job) == 1 and words_in_job[0] in text_lower:
        logger.info(f"✅ SINGLE WORD FALLBACK: Found single word '{job_id}' in text")
        return True

    # --------------------------------------------------
    # If everything fails
    # --------------------------------------------------
    logger.info(f"❌ NO MATCH FOUND for '{job_id}'")
    return False

def node_ingest_gmail(state: PipelineState) -> PipelineState:
    """
    Process unread emails with intelligent regex-based job_id matching.
    Only opens and processes emails where the SUBJECT matches the job_id.
    """
    config = get_job_config() 
    gmail, calendar, drive, sheets, forms = google_services()
    
    # Get unread emails with attachments
    msgs = list_unread_with_attachments(gmail, 'label:inbox is:unread has:attachment')
    
    MAX_EMAILS_TO_PROCESS = 50
    if len(msgs) > MAX_EMAILS_TO_PROCESS:
        msgs = msgs[:MAX_EMAILS_TO_PROCESS]
    
    logger.info(f"📧 Found {len(msgs)} unread emails with attachments")
    
    job_id = config['job_id'] or ""
    processed_count = 0
    skipped_count = 0
    
    for m in msgs:
        sender = re.findall(r'<([^>]+)>', m['from'])
        sender_email = sender[0] if sender else (m['from'] or '')
        subject = m.get('subject', '')
        
        logger.info(f"📨 Email from: {sender_email}")
        logger.info(f"   Subject: {subject}")
        
        # Check if candidate already exists in sheet
        existing_candidate = get_candidate_from_sheet(sheets, state.sheet_id, sender_email)
        if existing_candidate:
            logger.info(f"⏭️ Already in system - marking read and skipping")
            try:
                gmail.users().messages().modify(userId='me', id=m['id'], body={"removeLabelIds": ["UNREAD"]}).execute()
            except:
                pass
            skipped_count += 1
            continue
        
        # 🔍 CRITICAL: Check job_id in email subject FIRST using regex
        if job_id:
            subject_match = intelligent_job_match(subject, job_id)
            logger.info(f"🔍 Subject match result: {subject_match}")
            
            if not subject_match:
                logger.info(f"⏭️ NO SUBJECT MATCH - Keeping email UNREAD for other positions")
                skipped_count += 1
                continue
        
        # ✅ If we get here, the subject matches - process the email
        logger.info(f"✅ SUBJECT MATCHED - Processing email and attachments")
        
        candidate_folder_id = ensure_drive_folder(drive, f"{config['drive_folder_name']}/{sender_email}")
        attachments_meta = []
        raw_text = ""
        
        # Process attachments (only for matching emails)
        for att in m['attachments']:
            try:
                logger.info(f"   📎 Processing attachment: {att['filename']}")
                fid = download_attachment_to_drive(gmail, drive, candidate_folder_id, att['message_id'], att['attachment_id'], att['filename'])
                attachments_meta.append({"name": att['filename'], "drive_file_id": fid})
                
                # Read the CV content
                raw_text_part = read_drive_file_text(drive, fid, att['filename'])
                raw_text += "\n" + raw_text_part
                logger.info(f"   ✅ Successfully processed: {att['filename']}")
                
            except Exception as e:
                logger.warning(f"   ❌ Failed to process {att['filename']}: {e}")
        
        # Mark email as read since we processed it
        try:
            gmail.users().messages().modify(userId='me', id=m['id'], body={"removeLabelIds": ["UNREAD"]}).execute()
            logger.info(f"📭 Marked email as READ - processed successfully")
        except Exception as e:
            logger.warning(f"❌ Failed to mark email as read: {e}")
        
        if not raw_text.strip():
            logger.info("⏭️ No readable text in attachments - but email was processed")
            continue
        
        # Additional content verification (optional)
        if job_id and not intelligent_job_match(raw_text, job_id):
            logger.info("⚠️ Job ID not found in CV content, but processing anyway (subject matched)")
        
        # Create candidate
        cand = Candidate(
            email=sender_email, 
            raw_text=raw_text.strip(), 
            source='gmail', 
            attachments=attachments_meta, 
            job_id=config['job_id']
        )
        state.candidates.append(cand.model_dump())
        processed_count += 1
        
        # Send acknowledgment
        try:
            send_gmail = lambda to, sub, body: _send_gmail_direct(gmail, to, sub, body)
            send_gmail(
                sender_email, 
                f"Application received: {config['job_title']}",
                config['templates']['ack'].format(
                    name=cand.name or 'Candidate', 
                    job_title=config['job_title']
                )
            )
            logger.info(f"📤 Sent acknowledgment to {sender_email}")
        except Exception as e:
            logger.warning(f"❌ Failed to send acknowledgment: {e}")
    
    logger.info(f"📊 Email processing complete: {processed_count} processed, {skipped_count} skipped/kept unread")
    return state


def node_ingest_forms(state: PipelineState) -> PipelineState:
    """
    Process Google Form responses:
      - Create a folder per candidate using their email (directly, not inside Form CVs)
      - Store uploaded CV(s) with original names
      - Save form question/answer data in JSON file
    """
    config = get_job_config()
    gmail, calendar, drive, sheets, forms = google_services()
    FORM_ID=config['form_id']
    if not FORM_ID:
        logger.info("⏭️ FORM_ID not set; skipping Forms ingestion.")
        return state

    resp = forms.forms().get(formId=FORM_ID).execute()
    form_items = resp.get('items', [])
    question_map = {item['questionItem']['question']['questionId']: item['title']
                    for item in form_items if 'questionItem' in item and 'question' in item['questionItem']}

    resp = forms.forms().responses().list(formId=FORM_ID).execute()
    responses = resp.get('responses', []) or []

    logger.info(f"📋 Processing {len(responses)} form responses")

    job_id = config['job_id'] or ""
    processed_count = 0

    for r in responses:
        answers = r.get('answers', {}) or {}
        email = None
        name = None
        job_id_found = False
        attachments_meta = []
        raw_text = ""
        form_data = {}

        # Extract text answers (including email, name, etc.)
        for qid, v in answers.items():
            tlist = v.get('textAnswers', {}).get('answers', [])
            if not tlist:
                continue
            val = tlist[0].get('value', '').strip()

            # Save Q&A with actual question titles
            q_title = question_map.get(qid, qid)
            form_data[q_title] = val

            if '@' in val and not email:
                email = val
            elif not name and val and '@' not in val:
                name = val

            if job_id and intelligent_job_match(val, job_id):
                job_id_found = True
                logger.info(f"✅ Form response matches job_id: {email}")

        # Skip if job_id doesn’t match
        if job_id and not job_id_found:
            continue
        if not email:
            continue

        # Skip if candidate already exists
        existing_candidate = get_candidate_from_sheet(sheets, state.sheet_id, email)
        if existing_candidate:
            continue

        # Create folder directly named by email (no "Form CVs" subfolder)
        email_folder_id = ensure_drive_folder(drive, f"{config['drive_folder_name']}/{email}")

        # Handle file uploads (keep original name)
        for qid, v in answers.items():
            fups = v.get('fileUploadAnswers', {}).get('answers', [])
            for fobj in fups:
                file_id = fobj.get('fileId')
                original_fname = fobj.get('fileName') or f"{file_id}.bin"
                original_fn=original_fname.split('-')[0]
                if file_id:
                    try:
                        copied = drive.files().copy(
                            fileId=file_id,
                            body={'parents': [email_folder_id], 'name': original_fn}
                        ).execute()
                        fid = copied.get('id')

                        attachments_meta.append({"name": original_fn, "drive_file_id": fid})
                        file_text = read_drive_file_text(drive, fid, original_fn)
                        if file_text.strip():
                            raw_text += "\n" + file_text

                    except Exception as e:
                        logger.warning(f"❌ File processing error: {e}")

        if not raw_text.strip():
            continue

        # Save form responses as JSON file
        form_json_name = "form_responses.json"
        json_bytes = io.BytesIO(json.dumps(form_data, indent=2, ensure_ascii=False).encode('utf-8'))
        media = MediaIoBaseUpload(json_bytes, mimetype='application/json', resumable=True)
        drive.files().create(
            body={'name': form_json_name, 'parents': [email_folder_id]},
            media_body=media,
            fields='id'
        ).execute()

        # Add candidate to pipeline state
        cand = Candidate(
            email=email,
            name=name,
            raw_text=raw_text.strip(),
            source='form',
            attachments=attachments_meta,
            job_id=config['job_id']
        )
        assign_city_to_candidate(cand, form_data)
        state.candidates.append(cand.model_dump())
        processed_count += 1

    logger.info(f"✅ Form processing complete: {processed_count} candidates added")
    return state



