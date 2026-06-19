from typing import Optional, TypedDict


class CommunicationAgentState(TypedDict):
    case_id:           str
    notification_type: str
    case_data:         dict        # customer-safe case fields
    context:           dict        # extra context (requested docs, resolution summary, etc.)
    subject:           str         # generated subject line
    body:              str         # generated HTML body
    recipient:         str         # intended recipient email
    status:            str         # SENT / FAILED / PENDING
    error:             Optional[str]
    agent_start_time:  float
