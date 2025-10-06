from typing import Any, Dict, List, Optional, Tuple
from Google_services import google_services
from pydantic import BaseModel, Field
import os
import logging
import time

from Drive import *
from Utils import _send_gmail_direct
from models import *
from config import get_job_config

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")

INTERVIEW_THRESHOLD = float(os.getenv("INTERVIEW_THRESHOLD", "50"))
AUTO_REJECT = os.getenv("AUTO_REJECT", "false").lower() == "true"

def node_schedule_interviews(state: PipelineState) -> PipelineState:
    config=get_job_config()
    gmail, calendar, drive, sheets, forms = google_services()
    threshold = INTERVIEW_THRESHOLD
    
    # Get meeting link from environment variable
    MEET_LINK = os.getenv("MEET_LINK", "(see calendar invite)")
    
    for c in state.candidates:
        # Skip if already processed (check both status and sheet)
        if c.status in {'interview_scheduled', 'rejected', 'hired'}:
            continue
            
        # Check if candidate already has interview scheduled in Google Sheets
        existing_candidate = get_candidate_from_sheet(sheets, state.sheet_id, c.email)
        if existing_candidate and existing_candidate.get('status') == 'interview_scheduled':
            logger.info(f"Candidate {c.email} already has interview scheduled in sheet, skipping")
            c.status = 'interview_scheduled'
            if existing_candidate.get('interview_event_id'):
                c.interview_event_id = existing_candidate.get('interview_event_id')
            continue
            
        if (c.overall_score or 0) >= threshold:
            # Schedule interview
            start = datetime.now(UTC) + timedelta(days=1)
            end = start + timedelta(minutes=45)
            
            event = {
                'summary': f"Interview: {config['job_title']} - {c.name or c.email}",
                'start': {'dateTime': start.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': end.isoformat(), 'timeZone': 'UTC'},
                'attendees': [{'email': c.email}],
                'reminders': {
                    'useDefault': True,  # Use calendar's default reminders
                },
            }
            
            # Add Google Meet link if available
            if MEET_LINK and MEET_LINK != "(see calendar invite)":
                event['conferenceData'] = {
                    'createRequest': {
                        'requestId': f"meet_{c.email}_{int(time.time())}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                }
            
            try:
                # Create event with notifications enabled
                ev = calendar.events().insert(
                    calendarId=state.calendar_id, 
                    body=event,
                    conferenceDataVersion=1,  # This enables Google Meet creation
                    sendUpdates='all'  # This sends notifications to all attendees
                ).execute()
                
                c.interview_event_id = ev.get('id')
                c.status = 'interview_scheduled'
                
                # Get the actual meeting link
                actual_meet_link = MEET_LINK
                if ev.get('hangoutLink'):
                    actual_meet_link = ev.get('hangoutLink')
                elif ev.get('conferenceData', {}).get('entryPoints'):
                    for entry_point in ev['conferenceData']['entryPoints']:
                        if entry_point.get('entryPointType') == 'video':
                            actual_meet_link = entry_point.get('uri', MEET_LINK)
                            break
                
                # Send email only if not already sent
                if not c.interview_email_sent:
                    _send_gmail_direct(
                        gmail, 
                        c.email, 
                        f"Interview Invitation - {config['job_title']}",
                        config['templates']['interview_invite'].format(
                            name=c.name or 'Candidate', 
                            date_time=start.strftime('%Y-%m-%d %H:%M UTC'), 
                            tz='UTC', 
                            meet_link=actual_meet_link
                        )
                    )
                    c.interview_email_sent = True
                    logger.info(f"Interview scheduled and email sent to {c.email}")
                
                # Update Google Sheets immediately to record the interview scheduling
                try:
                    row_index = find_candidate_row_by_email(sheets, state.sheet_id, c.email)
                    if row_index:
                        # Update status and interview event ID in sheet
                        update_range = f"Candidates!M{row_index}"  # Status column
                        sheets.spreadsheets().values().update(
                            spreadsheetId=state.sheet_id,
                            range=update_range,
                            valueInputOption='RAW',
                            body={'values': [[c.status]]}
                        ).execute()
                        
                        # Update interview event ID if column exists (assuming column O)
                        update_range_id = f"Candidates!O{row_index}"
                        sheets.spreadsheets().values().update(
                            spreadsheetId=state.sheet_id,
                            range=update_range_id,
                            valueInputOption='RAW',
                            body={'values': [[c.interview_event_id]]}
                        ).execute()
                        
                        logger.info(f"Updated Google Sheets for {c.email} with interview status")
                except Exception as e:
                    logger.warning(f"Failed to update Google Sheets for {c.email}: {e}")
                
            except Exception as e:
                logger.warning(f"Failed scheduling interview for {c.email}: {e}")
                
        else:
            # Auto-reject below threshold candidates
            if AUTO_REJECT and not c.rejection_email_sent:
                try:
                    _send_gmail_direct(
                        gmail, 
                        c.email, 
                        f"Application Update - {config['job_title']}",
                        config['templates']['reject'].format(
                            name=c.name or 'Candidate', 
                            job_title=config['job_title']
                        )
                    )
                    c.status = 'rejected'
                    c.rejection_email_sent = True
                    
                    # Update Google Sheets for rejection
                    try:
                        row_index = find_candidate_row_by_email(sheets, state.sheet_id, c.email)
                        if row_index:
                            update_range = f"Candidates!M{row_index}"  # Status column
                            sheets.spreadsheets().values().update(
                                spreadsheetId=state.sheet_id,
                                range=update_range,
                                valueInputOption='RAW',
                                body={'values': [[c.status]]}
                            ).execute()
                    except Exception as e:
                        logger.warning(f"Failed to update Google Sheets rejection for {c.email}: {e}")
                        
                    logger.info(f"Rejection email sent to {c.email}")
                except Exception as e:
                    logger.warning(f"Failed sending reject to {c.email}: {e}")
    
    return state

def node_generate_reports(state: PipelineState) -> PipelineState:
    config=get_job_config()
    gmail, calendar, drive, sheets, forms = google_services()
    config=get_job_config()
    for candidate in state.candidates:
        try:
            # Create folder for candidate using their email
            candidate_folder_id = ensure_drive_folder(drive, f"{config['drive_folder_name']}/{candidate.email}")
            
            # Create report name using candidate's name or email if name is not available
            report_name = f"{candidate.name or candidate.email}_report.json"
            
            # Create candidate-specific report
            candidate_report = {
                'job_id': config['job_id'], 
                'generated_at': datetime.now(UTC).isoformat(), 
                "candidate": candidate.model_dump(exclude={"raw_text","notes","form_id"})

            }
            
            content = io.BytesIO(json.dumps(candidate_report, indent=2, ensure_ascii=False).encode('utf-8'))
            media = MediaIoBaseUpload(content, mimetype='application/json', resumable=False)
            meta = {
                'name': report_name,
                'parents': [candidate_folder_id]
            }
            
            # Check if report already exists and update it, otherwise create new
            try:
                query = f"'{candidate_folder_id}' in parents and name = '{report_name}' and trashed = false"
                existing_files = drive.files().list(q=query, fields='files(id)').execute()
                files = existing_files.get('files', [])
                
                if files:
                    # Update existing report
                    drive.files().update(
                        fileId=files[0]['id'],
                        media_body=media,
                        fields='id'
                    ).execute()
                    logger.info(f"Updated report for {candidate.email}")
                else:
                    # Create new report
                    drive.files().create(body=meta, media_body=media, fields='id').execute()
                    logger.info(f"Created new report for {candidate.email}")
                    
            except Exception as e:
                logger.warning(f"Failed to check/update report for {candidate.email}: {e}")
                # Fallback: try to create new report
                try:
                    drive.files().create(body=meta, media_body=media, fields='id').execute()
                except Exception as e2:
                    logger.warning(f"Failed to create fallback report for {candidate.email}: {e2}")
                    
        except Exception as e:
            logger.warning(f"Failed to process report for candidate {candidate.email}: {e}")
    
    return state

