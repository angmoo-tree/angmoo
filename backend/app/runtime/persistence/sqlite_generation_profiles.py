"""Schema additions shared by current metadata and the v9-to-v10 migration."""

ADDED_COLUMNS = {
    "llm_credentials": {"thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
    "agent_creation_drafts": {"thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
    "user_message_preferences": {"default_thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
    "message_threads": {"selected_thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
    "chat_response_requests": {"selected_thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
    "memory_batch_profiles": {"thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
    "memory_batch_settings": {
        "execution_version": "INTEGER DEFAULT '1' NOT NULL",
        "retry_request_key": "VARCHAR(128)",
    },
    "memory_batch_runs": {"thinking_level": "VARCHAR(8) DEFAULT 'high' NOT NULL"},
}
