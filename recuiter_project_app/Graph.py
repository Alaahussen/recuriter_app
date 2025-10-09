from Google_services import google_services
from langgraph.graph import StateGraph, END
from Drive import *
from Featch_cv import *
from Scores import *
from Reports import *
from pydantic import BaseModel
from config import get_job_config
from models import *
from dotenv import load_dotenv
import os

load_dotenv()

def evaluate_cv_node(state: PipelineState) -> PipelineState:
    """
    Evaluate candidates based on the configured evaluation mode and update their status.
    Also syncs updates to Google Sheets if available.

    Evaluation modes:
        - "تقييم السيرة الذاتية فقط": Uses only CV score.
        - "تقييم السيرة الذاتية + الاختبار": Combines CV and test scores if candidate is tested.

    Environment variables:
        - EVALUATION_MODE: Controls which evaluation logic to use.
        - INTERVIEW_THRESHOLD: Minimum score to move candidate to the interview stage.
    """
    evaluation_mode = os.getenv("EVALUATION_MODE", "تقييم السيرة الذاتية فقط")
    interview_threshold = float(os.getenv("INTERVIEW_THRESHOLD", "0.6"))

    for candidate in state.candidates:
        # --- Safe extraction of attributes ---
        candidate.cv_score = float(getattr(candidate, "cv_score", 0.0) or 0.0)
        candidate.test_score = float(getattr(candidate, "test_score", 0.0) or 0.0)
        candidate.status = getattr(candidate, "status", "Pending")

        # --- Calculate overall score based on evaluation mode ---
        if evaluation_mode == "تقييم السيرة الذاتية فقط":
            candidate.overall_score = candidate.cv_score

        elif evaluation_mode == "تقييم السيرة الذاتية + الاختبار":
            if candidate.status.lower() == "tested":
                candidate.overall_score = 0.6 * candidate.cv_score + 0.4 * candidate.test_score
            else:
                candidate.overall_score = candidate.cv_score

        else:
            print(f"⚠️ Unknown evaluation mode: {evaluation_mode}, defaulting to CV score only.")
            candidate.overall_score = candidate.cv_score

        # --- Assign status based on threshold ---
        if candidate.overall_score >= interview_threshold:
            candidate.status = "Pending"
        else:
            candidate.status = "Under Threshold"

        # --- Log evaluation ---
        print(f"✅ Evaluated {getattr(candidate, 'name', 'Unknown')}: "
              f"CV={candidate.cv_score}, Test={candidate.test_score}, "
              f"Overall={candidate.overall_score}, Status={candidate.status}")

        # --- Update Google Sheet if possible ---
        try:
            if "sheets" in globals() and getattr(state, "sheet_id", None):
                row_index = find_candidate_row_by_email(sheets, state.sheet_id, candidate.email)
                if row_index:
                    update_range = f"Candidates!M{row_index}"
                    sheets.spreadsheets().values().update(
                        spreadsheetId=state.sheet_id,
                        range=update_range,
                        valueInputOption="RAW",
                        body={"values": [[candidate.status]]},
                    ).execute()
        except Exception as e:
            print(f"⚠️ Warning while updating Google Sheets for {candidate.email}: {e}")

    return state


def build_graph(send_tests_enabled=True, evaluation_mode="تقييم السيرة الذاتية فقط"):
    """Build ATS pipeline with flexible evaluation mode and test sending."""
    gmail, calendar, drive, sheets, forms = google_services()

    g = StateGraph(PipelineState)

    # --- Nodes ---
    g.add_node("bootstrap", node_bootstrap)
    g.add_node("check_existing_candidates", node_check_existing_candidates)
    g.add_node("ingest_gmail", node_ingest_gmail)
    g.add_node("ingest_forms", node_ingest_forms)
    g.add_node("classify_and_score", node_classify_and_score)
    g.add_node("send_tests", node_send_tests)
    g.add_node("poll_test_answers", node_poll_test_answers)
    g.add_node("evaluate_cv", evaluate_cv_node)  # ✅ New node here
    g.add_node("compute_overall_and_store", node_compute_overall_and_store)
    g.add_node("generate_reports", node_generate_reports)

    # --- Flow ---
    g.set_entry_point("bootstrap")
    g.add_edge("bootstrap", "check_existing_candidates")
    g.add_edge("check_existing_candidates", "ingest_gmail")
    g.add_edge("ingest_gmail", "ingest_forms")

    def next_step(state: PipelineState) -> str:
        new_candidates = [c for c in state.candidates if c.status == "received"]

        if new_candidates:
            return "classify_and_score"

        if send_tests_enabled:
            needs_tests = any(c.status == "classified" and not c.form_id for c in state.candidates)
            if needs_tests:
                return "send_tests"

            needs_polling = any(c.status == "test_sent" for c in state.candidates)
            if needs_polling:
                return "poll_test_answers"

        return "evaluate_cv"  # ✅ Go to evaluation next

    g.add_conditional_edges("ingest_forms", next_step, {
        "classify_and_score": "classify_and_score",
        "send_tests": "send_tests",
        "poll_test_answers": "poll_test_answers",
        "evaluate_cv": "evaluate_cv"
    })

    if send_tests_enabled:
        g.add_edge("classify_and_score", "send_tests")
        g.add_edge("send_tests", "poll_test_answers")
        g.add_edge("poll_test_answers", "evaluate_cv")
    else:
        g.add_edge("classify_and_score", "evaluate_cv")

    # ✅ Evaluation happens before computing & storing
    g.add_edge("evaluate_cv", "compute_overall_and_store")
    g.add_edge("compute_overall_and_store", "generate_reports")
    g.add_edge("generate_reports", END)

    os.environ["EVALUATION_MODE"] = evaluation_mode
    return g.compile()



