from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class DisputeAgentState(TypedDict):
    messages:            Annotated[list, add_messages]  # tool-call / response history
    dispute_input:       dict                            # raw submission from API
    document_texts:      List[str]                      # OCR-extracted evidence files
    final_case:          dict                            # assembled case record for DB
    error:               Optional[str]
