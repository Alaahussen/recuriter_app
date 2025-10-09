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


def evaluate_cv_node(state: PipelineState) -> PipelineState
    """
    Evaluate candidates based on the configured evaluation mode and update their status.
    Supports re-evaluation when new test results appear or evaluation mode changes.
    """

    evaluation_mode = os.getenv("EVALUATION_MODE", "تقييم السيرة الذاتية فقط")
    interview_threshold = float(os.getenv("INTERVIEW_THRESHOLD", "0.6"))

    for candidate in state.candidates:
        # --- Safe extraction ---
        candidate.cv_score = float(getattr(candidate, "cv_score", 0.0) or 0.0)
        candidate.test_score = float(getattr(candidate, "test_score", 0.0) or 0.0)
        previous_status = getattr(candidate, "status", "Pending")

        # --- Always recalc overall score (even if status already exists) ---
        if evaluation_mode == "تقييم السيرة الذاتية فقط":
            candidate.overall_score = candidate.cv_score

        elif evaluation_mode == "تقييم السيرة الذاتية + الاختبار":
            # Recalculate if test score available
            if candidate.test_score > 0:
                candidate.overall_score = 0.6 * candidate.cv_score + 0.4 * candidate.test_score
            else:
                candidate.overall_score = candidate.cv_score

        else:
            print(f"⚠️ Unknown evaluation mode: {evaluation_mode}, defaulting to CV score only.")
            candidate.overall_score = candidate.cv_score

        # --- Update status based on the *new* score ---
        if candidate.overall_score >= interview_threshold:
            candidate.status = "Interviewed"
        else:
            candidate.status = "Under Threshold"

        # --- Log changes ---
        print(f"✅ Evaluated {getattr(candidate, 'name', 'Unknown')}: "
              f"CV={candidate.cv_score}, Test={candidate.test_score}, "
              f"Overall={candidate.overall_score}, "
              f"Old Status={previous_status} → New Status={candidate.status}")

        # --- Sync to Google Sheets (optional) ---
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
    """
    Build ATS pipeline with flexible evaluation mode and test sending.
    Auto-detects when to re-evaluate after polling test answers.
    """
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
    g.add_node("evaluate_cv", evaluate_cv_node)  # ✅ Updated evaluation node
    g.add_node("compute_overall_and_store", node_compute_overall_and_store)
    g.add_node("generate_reports", node_generate_reports)

    # --- Flow ---
    g.set_entry_point("bootstrap")
    g.add_edge("bootstrap", "check_existing_candidates")
    g.add_edge("check_existing_candidates", "ingest_gmail")
    g.add_edge("ingest_gmail", "ingest_forms")

    # --- Determine next step dynamically ---
    def next_step(state: PipelineState) -> str:
        # 1️⃣ New candidates from Gmail or Forms
        new_candidates = [c for c in state.candidates if c.status == "received"]
        if new_candidates:
            return "classify_and_score"

        # 2️⃣ Test logic (if enabled)
        if send_tests_enabled:
            # Candidates classified but not yet sent tests
            needs_tests = any(c.status == "classified" and not getattr(c, "form_id", None) for c in state.candidates)
            if needs_tests:
                return "send_tests"

            # Candidates who have tests sent but no answers yet
            needs_polling = any(c.status == "test_sent" for c in state.candidates)
            if needs_polling:
                return "poll_test_answers"

            # ✅ Candidates who now have test answers ready (need re-evaluation)
            ready_for_eval = any(c.status in ["test_completed", "test_answered"] for c in state.candidates)
            if ready_for_eval:
                return "evaluate_cv"

        # Default: directly evaluate
        return "evaluate_cv"

    g.add_conditional_edges("ingest_forms", next_step, {
        "classify_and_score": "classify_and_score",
        "send_tests": "send_tests",
        "poll_test_answers": "poll_test_answers",
        "evaluate_cv": "evaluate_cv"
    })

    # --- Conditional progression depending on test config ---
    if send_tests_enabled:
        g.add_edge("classify_and_score", "send_tests")
        g.add_edge("send_tests", "poll_test_answers")
        g.add_edge("poll_test_answers", "evaluate_cv")
    else:
        g.add_edge("classify_and_score", "evaluate_cv")

    # ✅ Evaluation happens before storing & reporting
    g.add_edge("evaluate_cv", "compute_overall_and_store")
    g.add_edge("compute_overall_and_store", "generate_reports")
    g.add_edge("generate_reports", END)

    # --- Store selected mode globally ---
    os.environ["EVALUATION_MODE"] = evaluation_mode

    return g.compile()
