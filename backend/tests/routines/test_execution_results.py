from app.domains.routines.service import execution_results as agent_run_service


def test_combined_runtime_audit_post_prefers_actual_inbox_target() -> None:
    result = {
        "publish_result": {
            "inbox": {
                "public_action_count": 1,
                "target_post_id": "post-inbox-target",
            },
            "routine": {
                "public_action_count": 1,
                "post_id": "post-routine-root",
            },
            "feed": {
                "public_action_count": 1,
                "target_post_id": "post-feed-target",
            },
        }
    }

    assert (
        agent_run_service._combined_runtime_evidence_post_id(result)
        == "post-inbox-target"
    )


def test_combined_runtime_audit_post_uses_root_or_none() -> None:
    root_only = {
        "publish_result": {
            "routine": {
                "public_action_count": 1,
                "post_id": "post-routine-root",
            },
            "feed": {"public_action_count": 0},
        }
    }
    no_action = {
        "publish_result": {
            "routine": {"public_action_count": 0},
            "feed": {"public_action_count": 0},
        }
    }

    assert (
        agent_run_service._combined_runtime_evidence_post_id(root_only)
        == "post-routine-root"
    )
    assert agent_run_service._combined_runtime_evidence_post_id(no_action) is None
