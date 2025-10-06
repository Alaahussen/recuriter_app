from datetime import datetime, timedelta, UTC
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
import pdfplumber
import docx
import logging
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import mimetypes
import re
import json
import base64
import io
import os
from Google_services import google_services
from models import *
from config import get_job_config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")

from dotenv import load_dotenv
load_dotenv()

from config import get_job_config


def ensure_drive_folder(drive, folder_path: str) -> str:
    """Ensure nested folder exists; return final folder id."""
    parts = [p.strip() for p in folder_path.split('/') if p.strip()]
    parent_id = None
    for name in parts:
        q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        res = drive.files().list(q=q, spaces='drive', fields='files(id, name)', pageSize=1).execute()
        files = res.get('files', [])
        if files:
            parent_id = files[0]['id']
        else:
            meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
            if parent_id:
                meta['parents'] = [parent_id]
            folder = drive.files().create(body=meta, fields='id').execute()
            parent_id = folder['id']
    return parent_id


def ensure_sheet(sheets, drive, title: str, parent_folder_id: str) -> str:
    """Ensure sheet exists under folder and create 'Candidates' tab and header."""
    res = drive.files().list(q=(f"name = '{title}' and '{parent_folder_id}' in parents and "
                                "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"),
                             fields='files(id,name)').execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    sheet = sheets.spreadsheets().create(body={'properties': {'title': title}}).execute()
    sheet_id = sheet['spreadsheetId']
    # move to folder
    drive.files().update(fileId=sheet_id, addParents=parent_folder_id, removeParents='root').execute()
    # rename default sheet to Candidates
    requests = [{"updateSheetProperties": {"properties": {"sheetId": 0, "title": "Candidates"}, "fields": "title"}}]
    sheets.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": requests}).execute()
    header = [[
        'Timestamp','Job ID','Name','Email','City','Degree','Experience','Certifications',
        'CV Score','Test Score','Overall Score','Status','Notes'
    ]]
    sheets.spreadsheets().values().update(spreadsheetId=sheet_id, range='Candidates!A1', valueInputOption='RAW',
                                         body={'values': header}).execute()
    return sheet_id

def upsert_candidate_row(sheets, sheet_id: str, c: Candidate, drive_folder_link: str):
    row = [
        datetime.now(UTC).isoformat(), 
        c.job_id, 
        c.name or '', 
        c.email, 
        c.city or '',
        str(c.degree) if c.degree else '',
        ', '.join(c.experience) if c.experience else '',
        ', '.join(c.certifications) if c.certifications else '',
        c.cv_score if c.cv_score is not None else '', 
        c.test_score if c.test_score is not None else '',
        c.overall_score if c.overall_score is not None else '', 
        c.status,
        c.notes or ''

    ]
    sheets.spreadsheets().values().append(spreadsheetId=sheet_id, range='Candidates!A1', valueInputOption='RAW',
                                         body={'values': [row]}).execute()
    

def find_candidate_row_by_email(sheets, sheet_id: str, email: str) -> Optional[int]:
    """
    Search the Candidates sheet for the email and return the row index (1-based).
    Returns None if not found.
    Assumes header row is row 1.
    """
    try:
        # Read the Email column (D) from row 2 downward
        res = sheets.spreadsheets().values().get(spreadsheetId=sheet_id, range='Candidates!D2:D').execute()
        vals = res.get('values', []) or []
        for idx, row in enumerate(vals, start=2):
            if not row:
                continue
            cell = row[0]
            if cell and email and cell.strip().lower() == email.strip().lower():
                return idx
        return None
    except Exception as e:
        logger.warning(f"Failed to search sheet for {email}: {e}")
        return None


def update_candidate_row_links(sheets, sheet_id: str, row_index: int, quiz_form_id: str = "", quiz_link: str = "", questions_link: str = ""):
    """
    Update the Quiz Form ID (col Q), Quiz Link (col R), Interview Questions Link (col S) for the given row index.
    Columns: A..S = 1..19; Q=17, R=18, S=19
    We'll update range Candidates!Q{row}:S{row}
    """
    try:
        values = [[quiz_form_id or "", quiz_link or "", questions_link or ""]]
        range_a1 = f"Candidates!Q{row_index}:S{row_index}"
        sheets.spreadsheets().values().update(spreadsheetId=sheet_id, range=range_a1, valueInputOption='RAW', body={'values': values}).execute()
    except Exception as e:
        logger.warning(f"Failed to update quiz links for row {row_index}: {e}")

def get_candidate_from_sheet(sheets, sheet_id: str, email: str) -> Optional[Dict]:
    """
    Get candidate data from sheet by email.
    Returns a dictionary with candidate data if found, None otherwise.
    """
    try:
        row_index = find_candidate_row_by_email(sheets, sheet_id, email)
        if not row_index:
            return None
            
        # Read the entire row
        res = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id, 
            range=f"Candidates!A{row_index}:P{row_index}"
        ).execute()
        
        row = res.get('values', [])[0] if res.get('values') else []
        if not row:
            return None
            
        # Parse the row data
        candidate_data = {
            'job_id':row[1] if len(row) > 1 else '',
            'name': row[2] if len(row) > 2 else '',
            'email': row[3] if len(row) > 3 else '',
            'city': row[4] if len(row) > 4 else '',

            # --- Qualifications & Experience ---
            'degree': row[5] if len(row) > 5 else '',
            'experience': row[6].split(', ') if len(row) > 6 and row[6] else [],
            'certifications': row[7].split(', ') if len(row) > 7 and row[7] else [],

            # --- Scores ---
            'cv_score': float(row[8]) if len(row) > 8 and row[8] else None,
            'test_score': float(row[9]) if len(row) > 9 and row[9] else None,
            'overall_score': float(row[10]) if len(row) > 10 and row[10] else None,

            # --- Status ---
            'status': row[11] if len(row) > 11 else 'received',
            'notes': row[12] if len(row) > 12 else '',
            'form_id': None

        }
        if candidate_data['notes']:
            try:
                notes_data = json.loads(candidate_data['notes'])
                candidate_data['form_id'] = notes_data.get('form_id')
            except:
                pass
                
        return candidate_data
        
    except Exception as e:
        logger.warning(f"Failed to get candidate data for {email}: {e}")
        return None

def list_unread_with_attachments(gmail, query: str) -> List[Dict[str,Any]]:
    res = gmail.users().messages().list(userId='me', q=query, maxResults=100).execute()
    msgs = res.get('messages', []) or []
    out = []
    for m in msgs:
        full = gmail.users().messages().get(userId='me', id=m['id']).execute()
        payload = full.get('payload', {})
        headers = payload.get('headers', [])
        hdr = {h['name'].lower(): h['value'] for h in headers}
        parts = payload.get('parts', []) or []
        attachments = []
        for p in parts:
            if p.get('filename') and p.get('body', {}).get('attachmentId'):
                attachments.append({
                    'message_id': m['id'],
                    'attachment_id': p['body']['attachmentId'],
                    'filename': p['filename'],
                    'mimeType': p.get('mimeType', 'application/octet-stream')
                })
        if attachments:
            out.append({'id': m['id'], 'from': hdr.get('from',''), 'to': hdr.get('to',''),
                        'subject': hdr.get('subject',''), 'attachments': attachments})
    return out

def download_attachment_to_drive(gmail, drive, job_folder_id: str, msg_id: str, attachment_id: str, filename: str) -> str:
    """Download Gmail attachment and upload to Drive; return file id."""
    att = gmail.users().messages().attachments().get(userId='me', messageId=msg_id, id=attachment_id).execute()
    data = att.get('data')
    if data is None:
        # sometimes attachment returned as body->data not present; try get with media
        # fallback error
        raise RuntimeError("Attachment has no data")
    file_data = base64.urlsafe_b64decode(data.encode('UTF-8'))
    mimetype, _ = mimetypes.guess_type(filename)
    if mimetype is None:
        mimetype = "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(file_data), mimetype=mimetype, resumable=False)
    meta = {'name': filename, 'parents': [job_folder_id]}
    f = drive.files().create(body=meta, media_body=media, fields='id').execute()
    return f['id']

def read_drive_file_text(drive, file_id: str, name: str) -> str:
    """Read text from pdf or docx stored in Drive."""
    # get metadata mime
    try:
        req = drive.files().get(fileId=file_id, fields='mimeType, name').execute()
        mime = req.get('mimeType')
        name = req.get('name', name)
        fh = io.BytesIO()
        request = drive.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        text = ''
        if name.lower().endswith('.pdf') or (mime and 'pdf' in mime):
            with pdfplumber.open(fh) as pdf:
                for p in pdf.pages:
                    t = p.extract_text() or ''
                    text += t + '\n'
        elif name.lower().endswith('.docx') or (mime and 'wordprocessingml' in (mime or '')):
            # need to write temp file because python-docx expects filename
            tmp = f"tmp_{file_id}.docx"
            with open(tmp, 'wb') as f:
                f.write(fh.read())
            doc = docx.Document(tmp)
            text = '\n'.join([p.text for p in doc.paragraphs])
            try:
                os.remove(tmp)
            except:
                pass
        else:
            # fallback: try decode bytes
            try:
                text = fh.read().decode('utf-8', errors='ignore')
            except:
                text = ''
        return text.strip()
    except Exception as e:
        logger.warning(f"Failed reading drive file {file_id}: {e}")
        return ""


def update_candidate_row(sheets, sheet_id: str, row_index: int, c: Candidate, drive_folder_link: str):
    """Update an existing candidate row with new data."""
    row = [
        datetime.now(UTC).isoformat(), 
        c.job_id, 
        c.name or '', 
        c.email, 
        c.city or '',
        str(c.degree) if c.degree else '',
        ', '.join(c.experience) if c.experience else '',
        ', '.join(c.certifications) if c.certifications else '',
        c.cv_score if c.cv_score is not None else '', 
        c.test_score if c.test_score is not None else '',
        c.overall_score if c.overall_score is not None else '', 
        c.status,
        c.notes or '',
    ]
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id, 
        range=f'Candidates!A{row_index}:P{row_index}',
        valueInputOption='RAW',
        body={'values': [row]}
    ).execute()


def node_check_existing_candidates(state: PipelineState) -> PipelineState:
    """
    Check if candidates already exist in the sheet and load their data.
    This prevents duplication and allows the pipeline to continue where it left off.
    """
    gmail, calendar, drive, sheets, forms = google_services()
    
    if not state.sheet_id:
        logger.warning("No sheet ID available, skipping existing candidate check")
        return state
    
    try:
        # Read all emails from the sheet
        res = sheets.spreadsheets().values().get(
            spreadsheetId=state.sheet_id, 
            range='Candidates!D2:D'
        ).execute()
        
        emails = [row[0] for row in res.get('values', []) if row and row[0]]
        
        for email in emails:
            # Check if we already have this candidate in our state
            existing_in_state = any(c.email == email for c in state.candidates)
            if existing_in_state:
                continue
                
            # Get candidate data from sheet
            candidate_data = get_candidate_from_sheet(sheets, state.sheet_id, email)
            if candidate_data:
                # Create a Candidate object from the sheet data
                cand = Candidate(
                    email=email,
                    name=candidate_data.get('name'),
                    city=candidate_data.get('city'),
                    degree=candidate_data.get('degree'),
                    experience=candidate_data.get('experience',[]),
                    certifications=candidate_data.get('certifications', []),
                    job_id=candidate_data.get('job_id'),
                    status=candidate_data.get('status', 'received'),
                    cv_score=candidate_data.get('cv_score'),
                    test_score=candidate_data.get('test_score'),
                    overall_score=candidate_data.get('overall_score'),
                    notes=candidate_data.get('notes'),
                    form_id=candidate_data.get('form_id')
                )
                state.candidates.append(cand)
                logger.info(f"Loaded existing candidate from sheet: {email}")
                
    except Exception as e:
        logger.warning(f"Failed to check existing candidates: {e}")
    
    return state