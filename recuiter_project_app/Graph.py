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
    Syncs updates to Google Sheets if available.
    """
    evaluation_mode = os.getenv("EVALUATION_MODE", "تقييم السيرة الذاتية فقط")
    interview_threshold = float(os.getenv("INTERVIEW_THRESHOLD", "0.6"))

    for candidate in state.candidates:
        # --- Safe extraction of attributes ---
        candidate.cv_score = float(getattr(candidate, "cv_score", 0.0) or 0.0)
        candidate.test_score = float(getattr(candidate, "test_score", 0.0) or 0.0)
        #candidate.status = getattr(candidate, "status", "Pending")

        # --- Calculate overall score based on evaluation mode ---
        if evaluation_mode in ("cv_only", "تقييم السيرة الذاتية فقط"):
            candidate.overall_score = candidate.cv_score
        elif evaluation_mode in ("cv_and_test", "تقييم السيرة الذاتية والاختبار"):
            if candidate.test_score > 0:
                candidate.overall_score = 0.6 * candidate.cv_score + 0.4 * candidate.test_score
            else:
                candidate.overall_score = candidate.cv_score
        else:
            print(f"⚠️ Unknown evaluation mode: {evaluation_mode}, using CV only.")
            candidate.overall_score = candidate.cv_score

        # --- Assign status ---
        if candidate.overall_score >= interview_threshold:
            candidate.final_evaluation = "Interview Step"
        else:
            candidate.final_evaluation = "Under Threshold"

        print(f"✅ Evaluated {getattr(candidate, 'name', 'Unknown')}: "
              f"CV={candidate.cv_score}, Test={candidate.test_score}, "
              f"Overall={candidate.overall_score}, Status={candidate.status}")

        # --- Update Google Sheet if exists ---
        try:
            if "sheets" in globals() and getattr(state, "sheet_id", None):
                row_index = find_candidate_row_by_email(sheets, state.sheet_id, candidate.email)
                if row_index:
                    update_range = f"Candidates!M{row_index}"
                    sheets.spreadsheets().values().update(
                        spreadsheetId=state.sheet_id,
                        range=update_range,
                        valueInputOption="RAW",
                        body={"values": [[candidate.final_evaluation]]},
                    ).execute()
        except Exception as e:
            print(f"⚠️ Warning while updating Google Sheets for {candidate.email}: {e}")

    return state


def build_graph(evaluation_mode="تقييم السيرة الذاتية فقط"):
    """
    Build ATS pipeline with poll_test_answers node (no send_tests node).
    """
    print("🏗️ Building graph with poll_test_answers...")
    
    try:
        gmail, calendar, drive, sheets, forms = google_services()
        print("✅ Google services initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Google services: {e}")
        return None

    g = StateGraph(PipelineState)

    # --- Nodes ---
    g.add_node("bootstrap", node_bootstrap)
    g.add_node("check_existing_candidates", node_check_existing_candidates)
    g.add_node("ingest_gmail", node_ingest_gmail)
    g.add_node("ingest_forms", node_ingest_forms)
    g.add_node("classify_and_score", node_classify_and_score)
    g.add_node("poll_test_answers", node_poll_test_answers)
    g.add_node("evaluate_cv", evaluate_cv_node)
    g.add_node("compute_overall_and_store", node_compute_overall_and_store)
    g.add_node("generate_reports", node_generate_reports)

    # --- Flow structure ---
    g.set_entry_point("bootstrap")
    g.add_edge("bootstrap", "check_existing_candidates")
    g.add_edge("check_existing_candidates", "ingest_gmail")
    g.add_edge("ingest_gmail", "ingest_forms")
    g.add_edge("ingest_forms", "classify_and_score")
    g.add_edge("classify_and_score", "poll_test_answers")
    g.add_edge("poll_test_answers", "evaluate_cv")
    g.add_edge("evaluate_cv", "compute_overall_and_store")
    g.add_edge("compute_overall_and_store", "generate_reports")
    g.add_edge("generate_reports", END)

    print("✅ Graph built successfully")
    return g.compile()




