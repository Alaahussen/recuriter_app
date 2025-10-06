import os
import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from Graph import build_graph
from dotenv import load_dotenv
from config import get_job_config

from models import *
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_pipeline")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


if __name__ == '__main__':
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set. LLM features will use safe fallbacks.")
    workflow = build_graph()
    initial = PipelineState()
    final_state = workflow.invoke(initial)
    # final_state could be object or dict (langgraph versions vary)
    if isinstance(final_state, dict):
        candidates = final_state.get('candidates', [])
        sheet = final_state.get('sheet_id')
    else:
        candidates = final_state.candidates
        sheet = final_state.sheet_id
    print(f"Processed {len(candidates)} candidates. Sheet: {sheet}")
    