import google.generativeai as genai
from dotenv import load_dotenv
import logging
import re
import json
import os
from openai import OpenAI

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")


def get_job_config():
    """Get fresh job config with current environment variables"""
    load_dotenv(override=True)

    job_id = os.getenv("JOB_ID")
    job_city = os.getenv("JOB_CITY")
    job_requirements = os.getenv("JOB_REQUIREMENTS")

    return {
        "job_id": job_id,
        "job_title": job_id,
        "job_city": job_city,
        "requirements": job_requirements,
        "drive_folder_name": f"ATS/{job_id}" if job_id else "ATS/Unknown",
        "sheet_title": f"Candidates - {job_id}" if job_id else "Candidates",
        "calendar_id": os.getenv("CALENDAR_ID", "primary"),
        "hr_email": os.getenv("HR_FROM_EMAIL", ""),
        "form_id": os.getenv("FORM_ID", ""),
        "interview_threshold": int(os.getenv("INTERVIEW_THRESHOLD", 70)),
        "auto_reject": os.getenv("AUTO_REJECT", "false").lower() == "true",
        "evaluation_mode": os.getenv("EVALUATION_MODE", ""),
        "send_tests_enabled": os.getenv("SEND_TESTS_ENABLED", "true").lower() == "true",
        "templates": {
            "ack": "مرحبًا {name}، لقد استلمنا طلبك لوظيفة {job_title}. سيقوم فريقنا بمراجعة الطلب والتواصل معك قريبًا.",
            "test": "مرحبًا {name}، يرجى إكمال الاختبار التقني التالي: {test_link}. آخر موعد للتسليم: {deadline}.",
            "interview_invite": "Hello {name}, we'd like to invite you for an interview on {date_time} (timezone: {tz}). Meet link: {meet_link}",
            "reminder": "Reminder: Your interview for {job_title} is on {date_time}.",
            "result": "Hello {name}, thanks for interviewing for {job_title}. Result: {result}.",
            "reject": "مرحبًا {name}، نشكرك على التقديم لوظيفة {job_title}. بعد المراجعة، نعتذر عن عدم الاستمرار في هذه المرحلة. نتمنى لك كل التوفيق والنجاح."
        }
    }


# -------------------------------
# DYNAMIC LLM CALL FUNCTIONS
# -------------------------------

def llm_json(prompt: str, expect_list=False):
    """
    Send prompt to OpenAI (if OPENAI_API_KEY is set), otherwise fallback to Gemini.
    Returns parsed JSON. If parsing fails, returns a safe fallback.
    """
    try:
        # Reload environment each time
        load_dotenv(override=True)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        gemini_api_key = os.getenv("GEMINI_API_KEY")

        text = None

        # --- OpenAI path ---
        if openai_api_key:
            openai_client = OpenAI(api_key=openai_api_key)
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            text = resp.choices[0].message.content

        # --- Gemini path ---
        elif gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            gemini_client = genai.GenerativeModel("gemini-2.0-flash")
            resp = gemini_client.generate_content(prompt)
            text = resp.text

        else:
            logger.warning("No API key found for OpenAI or Gemini; returning fallback")
            return [] if expect_list else {}

        # --- Extract and parse JSON ---
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if m:
            return json.loads(m.group(0))

        return json.loads(text)

    except Exception as e:
        logger.warning(f"LLM call failed: {e} -- returning fallback")
        return [] if expect_list else {}


def llm_completion(prompt: str) -> str:
    """
    LLM completion function - returns plain text answer.
    Dynamically reads API key each time (OpenAI > Gemini fallback).
    """
    try:
        load_dotenv(override=True)
        openai_api_key = os.getenv("OPENAI_API_KEY")
        gemini_api_key = os.getenv("GEMINI_API_KEY")

        # --- OpenAI ---
        if openai_api_key:
            openai_client = OpenAI(api_key=openai_api_key)
            resp = openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100
            )
            return resp.choices[0].message.content.strip()

        # --- Gemini ---
        elif gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(
                prompt,
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                ],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=100
                )
            )
            return response.text.strip()

        # --- No key ---
        else:
            logger.error("No OpenAI or Gemini API key found; returning fallback")
            return "Fallback Answer"

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return "Fallback Answer"


# -------------------------------
# PROMPTS (unchanged)
# -------------------------------
CLASSIFY_PROMPT = (
    "You are an ATS extractor. Given the resume text, return JSON with keys:\n"
    "name, city, degree, experience (array), certifications (array)\n\n"
    "Instructions for experience:\n"
    "- Extract the years of experience exactly as mentioned in the resume "
    "(e.g., '5 years of experience', '3+ years').\n"
    "- If the resume contains a 'Work Experience' section, summarize return it "
    "only if the duration is explicitly written (e.g., 'Jan 2019 - Dec 2021').\n"
    "- Do NOT estimate years of experience if the information is unclear or missing.\n"
    "- If no explicit number or clear work history duration is given, set experience to null.\n\n"
    "Additional guidance:\n"
    "- Only consider experience that is actually mentioned in the CV (job titles, durations, or explicit statements).\n"
    "- Ignore unrelated hints or assumptions not written in the text.\n"
    "- Certifications should be listed as an array of strings.\n\n"
    "- Experiences should be listed as an array of strings.\n\n"
    "- Do not return the years of experience mentioned in the job requirements; only extract or estimate from the resume itself."
    "Resume:\n{resume}\nRequirements: {requirements}\n"
)

CV_SCORING_PROMPT = (
    "Score the resume against the job requirements from 0 to 100. "
    "Return JSON: {{\"score\": number, \"strengths\": [...], \"risks\": [...]}}.\n"
    "Resume:\n{resume}\nRequirements:\n{requirements}"
)

QUESTIONS_PROMPT = (
    "Given this resume and job requirements, generate a JSON array of 6 concise, role-specific interview questions (strings).\n"
    "يجب أن تكون جميع الأسئلة باللغة العربية فقط.\n"
    "السيرة الذاتية:\n{resume}\nالمتطلبات:\n{requirements}"
)

TEST_GEN_PROMPT = (
    "Generate 5 multiple-choice questions for the job '{job_id}'. "
    "يجب أن تكون جميع الأسئلة باللغة العربية فقط.\n"
    "Return JSON: [{{\"question\": str, \"options\": [...], \"answer\": str}}]"
)

TEST_ANALYSIS_PROMPT = (
    "You are a grader. Given candidate answers (plain text) and the expected quiz (JSON), produce JSON: {\"score\": number, \"feedback\": [..]}.\n"
    "Answers:\n{answers}\nQuiz:\n{quiz}\nExpectations:\n{requirements}"
)
