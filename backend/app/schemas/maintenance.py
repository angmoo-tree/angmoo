from pydantic import BaseModel


class AgentActivityMaintenanceRead(BaseModel):
    enabled: bool
    title: str
    message: str
    blocks_auto_ticks: bool
    blocks_run_now: bool
    blocks_feed_cues: bool
    auto_tick_allowlist_active: bool = False
    auto_tick_allowed_count: int = 0
    notice_enabled: bool = False
    notice_title: str = ""
    notice_message: str = ""
