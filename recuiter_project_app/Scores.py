from typing import Any, Dict, List, Optional, Tuple
from Google_services import google_services
from pydantic import BaseModel, Field
import logging
from Drive import *
from Utils import _send_gmail_direct

from config import *
from models import *

import traceback 
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")



def node_classify_and_score(state: PipelineState) -> PipelineState:
    config=get_job_config()
    gmail, calendar, drive, sheets, forms = google_services()
    for c in state.candidates:
        # Check if candidate already exists in sheet
        row_index = find_candidate_row_by_email(sheets, state.sheet_id, c.email)
        existing_candidate = get_candidate_from_sheet(sheets, state.sheet_id, c.email) if row_index else None
        
        if existing_candidate:
            logger.info(f"Candidate {c.email} already exists in sheet; updating data.")
            # Update our candidate object with existing data where we don't have new data
            c.name = c.name or existing_candidate.get('name')
            c.city = c.city or existing_candidate.get('city')
            c.role_applied = c.role_applied or existing_candidate.get('role_applied') or config['job_id']
            c.degree = c.degree or existing_candidate.get('degree')
            c.experience = c.experience or existing_candidate.get('experience',[])
            c.certifications = c.certifications or existing_candidate.get('certifications', [])
            c.cv_score = c.cv_score if c.cv_score is not None else existing_candidate.get('cv_score')
            c.test_score = c.test_score if c.test_score is not None else existing_candidate.get('test_score')
            c.overall_score = c.overall_score if c.overall_score is not None else existing_candidate.get('overall_score')
            c.status = c.status if c.status != "received" else existing_candidate.get('status', 'received')
            c.form_id = c.form_id or existing_candidate.get('form_id')
            c.notes = c.notes or existing_candidate.get('notes')
            
            # If we already have a test score, skip classification
            if c.test_score is not None and c.test_score > 0:
                logger.info(f"Candidate {c.email} already has test score {c.test_score}, skipping classification.")
                continue

        # Only classify if we don't have complete data
        if not all([c.name, c.city, c.cv_score is not None]):
            classify = llm_json(CLASSIFY_PROMPT.format(resume=c.raw_text[:15000], job_title=config['job_id'], requirements=config['requirements'])) or {}
            #print(classify)
            c.name = classify.get('name') or c.name
            c.city = classify.get('city') or c.city
            c.role_applied = classify.get('role_applied') or config['job_title']
            c.degree = classify.get('degree') or c.degree
            c.experience = classify.get('experience',[]) or c.experience
            c.certifications = classify.get('certifications', []) or c.certifications

            cvscore = llm_json(CV_SCORING_PROMPT.format(resume=c.raw_text[:15000], requirements=config['requirements'])) or {}
            try:
                c.cv_score = float(cvscore.get('score', 0))
            except:
                c.cv_score = 0.0

        # Generate questions if we don't have them
        if not c.interview_questions:
            qs = llm_json(QUESTIONS_PROMPT.format(resume=c.raw_text[:15000], requirements=config['requirements']), expect_list=True)
            if isinstance(qs, list):
                c.interview_questions = [str(x) for x in qs][:6]

        # Save questions .txt into candidate folder
        try:
            candidate_folder_id = ensure_drive_folder(drive, f"{config['drive_folder_name']}/{c.email}")
            questions_content = "\n".join(c.interview_questions) if c.interview_questions else ""
            content = io.BytesIO(questions_content.encode('utf-8'))
            media = MediaIoBaseUpload(content, mimetype='text/plain', resumable=False)
            meta = {'name': f"interview_questions_{c.email}.txt", 'parents': [candidate_folder_id]}
            file = drive.files().create(body=meta, media_body=media, fields='id, webViewLink').execute()
            questions_link = file.get('webViewLink')
        except Exception as e:
            logger.warning(f"Failed to write questions file for {c.email}: {e}")
            questions_link = ""

        # Update or append candidate row
        drive_folder_link = f"https://drive.google.com/drive/folders/{state.drive_folder_id}" if state.drive_folder_id else ""
        
        if row_index:
            # Update existing row
            update_candidate_row(sheets, state.sheet_id, row_index, c, drive_folder_link)
            # Update quiz links if we have them
            if c.form_id:
                form_link = f"https://docs.google.com/forms/d/{c.form_id}/viewform"
                update_candidate_row_links(sheets, state.sheet_id, row_index, c.form_id, form_link, questions_link)
        else:
            # Append new row
            upsert_candidate_row(sheets, state.sheet_id, c, drive_folder_link)

        c.status = 'classified' if c.status == 'received' else c.status
        
    return state

def node_send_tests(self,state: PipelineState) -> Tuple[PipelineState, bool, dict]:
        """
        Sends technical tests to candidates via Google Forms and email.
    
        Returns:
            (state, success_flag, form_links)
            - success_flag (bool): True if at least one test was sent successfully.
            - form_links (dict): {candidate_email: form_link} for successfully created tests.
        """
        config = get_job_config()
        gmail, calendar, drive, sheets, forms = google_services()
    
        deadline = (datetime.now(UTC) + timedelta(days=2)).strftime('%Y-%m-%d')
    
        # generate test per role
        quiz = llm_json(TEST_GEN_PROMPT.format(job_id=config['job_id']), expect_list=True) or []
    
        success_flag = False
        form_links = {}
    
        for c in state.candidates:
            if c.status != 'classified' or getattr(c, "form_id", None):
                continue
    
            try:
                # Step 1: Create a Google Form for this candidate
                form_body = {
                    "info": {
                        "title": f"{config['job_title']} - Technical Quiz",
                        "documentTitle": f"Quiz for {c.name or 'Candidate'}"
                    }
                }
                form = forms.forms().create(body=form_body).execute()
                form_id = form["formId"]
    
                # Step 2: Add questions to the form
                requests = []
                for i, q in enumerate(quiz):
                    qtxt = q.get("question") if isinstance(q, dict) else str(q)
                    opts = q.get("options", []) if isinstance(q, dict) else []
    
                    question_item = {
                        "title": qtxt,
                        "questionItem": {
                            "question": {
                                "required": True,
                            }
                        }
                    }
    
                    if opts:  # Multiple-choice
                        question_item["questionItem"]["question"]["choiceQuestion"] = {
                            "type": "RADIO",
                            "options": [{"value": o} for o in opts],
                            "shuffle": True,
                        }
    
                    requests.append({
                        "createItem": {
                            "item": question_item,
                            "location": {"index": i}
                        }
                    })
    
                if requests:
                    forms.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()
    
                # Step 3: Build form URL
                form_link = f"https://docs.google.com/forms/d/{form_id}/viewform"
    
                # Step 4: Send email to candidate
                body = config['templates']['test'].format(
                    name=c.name or 'Candidate',
                    test_link=form_link,
                    deadline=deadline
                )
                _send_gmail_direct(gmail, c.email, f"{config['job_id']} - Technical Quiz", body)
    
                # Step 5: Store formId + quiz in candidate notes
                c.status = 'test_sent'
                c.form_id = form_id
                c.notes = json.dumps({
                    "form_id": form_id,
                    "quiz": quiz
                }, ensure_ascii=False)
    
                # Track success
                form_links[c.email] = form_link
                success_flag = True
    
                # Update the candidate row in the sheet
                try:
                    row_index = find_candidate_row_by_email(sheets, state.sheet_id, c.email)
                    if row_index:
                        update_candidate_row_links(sheets, state.sheet_id, row_index, form_id, form_link, "")
                except Exception as e:
                    logger.warning(f"Failed to update candidate row with form ID: {e}")
    
            except Exception as e:
                logger.warning(f"Failed to send test to {c.email}: {e}")
    
        return state, success_flag, form_links


# Enhance the node_poll_test_answers function

def node_poll_test_answers(state: PipelineState) -> PipelineState:
    config=get_job_config()
    """
    Poll test answers from each candidate's Google Form with proper choice-based scoring.
    Uses the same logic as get_llm_correct_answers_with_choices but processes individually.
    """
    gmail, calendar, drive, sheets, forms = google_services()

    for c in state.candidates:
        if c.status not in {'test_sent', 'classified'}:
            continue

        try:
            logger.info(f"=== PROCESSING CANDIDATE: {c.email} ===")
            
            # Extract form_id from candidate notes
            form_id = None
            try:
                notes = json.loads(c.notes) if c.notes else {}
                form_id = notes.get("form_id")
                logger.info(f"Form ID from notes: {form_id}")
            except Exception as e:
                logger.warning(f"Failed to parse notes for {c.email}: {e}")
                continue

            if not form_id:
                logger.info(f"No form_id found for {c.email}, skipping")
                continue

            # 1) Fetch responses from the form
            logger.info("Fetching form responses...")
            resp = forms.forms().responses().list(formId=form_id).execute()
            responses = resp.get("responses", []) or []
            logger.info(f"Found {len(responses)} responses")
            
            if not responses:
                logger.info(f"No responses yet for form {form_id} ({c.email})")
                continue

            # 2) Get the latest response
            latest_response = responses[-1]
            logger.info(f"Using latest response: {latest_response.get('responseId')}")
            
            # Check respondent email if available
            respondent = latest_response.get("respondentEmail")
            if respondent and c.email and respondent.lower() != c.email.lower():
                logger.info(f"Email mismatch: expected {c.email}, got {respondent}")
                continue
            
            # 3) Get the form structure
            logger.info("Fetching form structure...")
            form_info = forms.forms().get(formId=form_id).execute()
            
            # 4) Create list of questions with choices and answers
            questions_with_choices_and_answers = []
            
            for item in form_info.get('items', []):
                item_id = item.get('itemId')
                question_text = item.get('title', 'Unknown question')
                question_item = item.get('questionItem', {})
                question = question_item.get('question', {})
                choice_question = question.get('choiceQuestion', {})

                # Extract choices
                choices = []
                if choice_question.get('type') in ['RADIO', 'DROP_DOWN']:
                    options = choice_question.get('options', [])
                    choices = [opt.get('value', '') for opt in options if opt.get('value')]

                # Find corresponding answer from the response
                candidate_answer = ""
                answers_dict = latest_response.get('answers', {})
                #logger.info(answers_dict)

                # Get the questionId for this item
                question_id = question.get('questionId')
                if question_id and question_id in answers_dict:
                    answer_data = answers_dict[question_id]

                    text_answers = answer_data.get('textAnswers', {}).get('answers', [])
                    if text_answers:
                        candidate_answer = text_answers[0].get('value', '')

                    choice_answers = answer_data.get('choiceAnswers', {}).get('answers', [])
                    if choice_answers and not candidate_answer:
                        candidate_answer = choice_answers[0].get('value', '')

                # Append if we have question + choices
                if choices:  # Only include multiple-choice questions
                    questions_with_choices_and_answers.append({
                        'item_id': item_id,
                        'question': question_text,
                        'choices': choices,
                        'candidate_answer': candidate_answer
                    })
            
            logger.info(f"Found {len(questions_with_choices_and_answers)} multiple-choice questions with answers")
            
            # 5) Process each question individually using the same logic
            correct_answers = 0
            total_questions = len(questions_with_choices_and_answers)
            detailed_feedback = []
            
            for qa in questions_with_choices_and_answers:
                logger.info(f"--- PROCESSING QUESTION ID: {qa['item_id']} ---")
                logger.info(f"Question: {qa['question']}")
                logger.info(f"Choices: {qa['choices']}")
                logger.info(f"Your answer: {qa['candidate_answer']}")
                
                # 6) Use the SAME LOGIC as get_llm_correct_answers_with_choices
                prompt_question = f"""
                Question: {qa['question']}
                Choices:
                """
                for j, choice in enumerate(qa['choices'], 1):
                    prompt_question += f"   {j}. {choice}\n"
                
                answer_prompt = f"""
                You are an expert. For the multiple-choice question below, choose the CORRECT answer from the provided choices.
                You MUST select ONLY from the given choices - do not create your own answer.
                
                Return ONLY the correct answer text (no JSON, no explanation):
                
                {prompt_question}
                """
                
                try:
                    # Use text completion
                    llm_response = llm_completion(answer_prompt)
                    llm_answer = llm_response.strip()
                    logger.info(f"LLM's answer: {llm_answer}")
                    
                    # Validate that the answer is in the choices (SAME LOGIC)
                    valid_answer = None
                    for choice in qa['choices']:
                        if llm_answer.lower() == choice.lower():
                            valid_answer = choice
                            break
                    
                    # If not exact match, try partial matching (SAME LOGIC)
                    if not valid_answer:
                        for choice in qa['choices']:
                            if llm_answer.lower() in choice.lower() or choice.lower() in llm_answer.lower():
                                valid_answer = choice
                                break
                    
                    # If still not found, use first choice as fallback (SAME LOGIC)
                    if not valid_answer and qa['choices']:
                        valid_answer = qa['choices'][0]
                    
                    llm_correct_answer = valid_answer or "Unknown"
                    
                    # Check if your answer matches LLM's answer (SAME LOGIC)
                    is_correct = False
                    if llm_correct_answer and qa['candidate_answer']:
                        is_correct = (qa['candidate_answer'].strip().lower() == llm_correct_answer.strip().lower())
                        if is_correct:
                            correct_answers += 1
                            logger.info("✓ CORRECT")
                        else:
                            logger.info("✗ WRONG")
                    
                    detailed_feedback.append({
                        'question': qa['question'],
                        'candidate_answer': qa['candidate_answer'],
                        'llm_correct_answer': llm_correct_answer,
                        'is_correct': is_correct,
                        'choices': qa['choices']
                    })
                    
                except Exception as e:
                    logger.error(f"Error getting LLM answer: {e}")
                    # Fallback logic (SAME AS ORIGINAL)
                    llm_correct_answer = qa['choices'][0] if qa['choices'] else "Unknown"
                    is_correct = (qa['candidate_answer'].strip().lower() == llm_correct_answer.strip().lower())
                    if is_correct:
                        correct_answers += 1
                    
                    detailed_feedback.append({
                        'question': qa['question'],
                        'candidate_answer': qa['candidate_answer'],
                        'llm_correct_answer': llm_correct_answer,
                        'is_correct': is_correct,
                        'choices': qa['choices'],
                        'error': str(e)
                    })
                
                logger.info("--- END QUESTION ---")
            
            # 7) Calculate final score
            if total_questions > 0:
                final_score = (correct_answers / total_questions) * 100
            else:
                final_score = 0
            
            logger.info(f"=== FINAL SCORE ===")
            logger.info(f"Total Questions: {total_questions}")
            logger.info(f"Correct Answers: {correct_answers}")
            logger.info(f"Final Score: {final_score}/100")
            
            # 8) Store results - LangGraph integration
            c.test_score = round(final_score, 2)
            c.notes = json.dumps({
                "form_id": form_id,
                "score": final_score
            }, ensure_ascii=False)
            c.status = "tested"
            
            logger.info(f"Graded test for {c.email}: {c.test_score}/100")
            
            # Update state for LangGraph
            state.candidates = [c if c.email == candidate.email else candidate for candidate in state.candidates]

        except Exception as e:
            logger.error(f"Error calculating test score for {c.email}: {e}")
            c.test_score = 0
            c.status = "tested"
            c.notes = json.dumps({
                "error": f"Test grading failed: {str(e)}",
                "graded_at": datetime.now(UTC).isoformat()
            }, ensure_ascii=False)
            
            # Update state for LangGraph even on error
            state.candidates = [c if c.email == candidate.email else candidate for candidate in state.candidates]

    return state



def node_compute_overall_and_store(state: PipelineState) -> PipelineState:
    config=get_job_config()
    gmail, calendar, drive, sheets, forms = google_services()
    for c in state.candidates:
        # Only compute if we have both scores
        if c.cv_score is not None and c.test_score is not None and c.overall_score is None:
            cv = c.cv_score or 0
            ts = c.test_score or 0
            c.overall_score = round(0.6*cv + 0.4*ts, 2)
            
        # Update the sheet
        row_index = find_candidate_row_by_email(sheets, state.sheet_id, c.email)
        if row_index:
            drive_folder_link = f"https://drive.google.com/drive/folders/{state.drive_folder_id}" if state.drive_folder_id else ""
            update_candidate_row(sheets, state.sheet_id, row_index, c, drive_folder_link)
            

    return state







