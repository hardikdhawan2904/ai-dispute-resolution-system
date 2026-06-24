"""
Shared thread pool executor for heavy AI operations.

Kept separate from FastAPI's default web executor so long-running agent
calls (re-analysis, LLM inference) never starve simple DB reads like listCases.
"""
from concurrent.futures import ThreadPoolExecutor

analysis_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="analysis")

