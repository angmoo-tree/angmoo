from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OPENCLAW_AGENT_IDS = ",".join(f"angmoo-{index}" for index in range(1, 31))
DEFAULT_APP_SECRET = "angmoo-dev-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Angmoo"
    API_V1_PREFIX: str = "/api/v1"
    API_DOCS_ENABLED: bool = True
    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_SECRET: SecretStr = SecretStr(DEFAULT_APP_SECRET)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/angmoo"
    SEED_DEMO_DATA: bool = True
    SIGNUP_ENABLED: bool = False
    LOGIN_THROTTLE_HMAC_SECRET: SecretStr | None = None
    LOGIN_TRUSTED_PROXY_CIDRS: str = ""
    GOOGLE_AUTH_VERIFY_SOURCE_PER_MINUTE: int = 5
    GOOGLE_AUTH_VERIFY_SOURCE_PER_15_MINUTES: int = 20
    GOOGLE_AUTH_VERIFY_GLOBAL_PER_MINUTE: int = 60
    GOOGLE_AUTH_VERIFY_MAX_IN_FLIGHT: int = 8
    GOOGLE_AUTH_VERIFY_LEASE_SECONDS: int = 30
    GOOGLE_AUTH_VERIFY_RETENTION_HOURS: int = 24
    OFFICIAL_OPERATOR_USER_IDS: str = ""
    DEMO_USER_PASSWORD: SecretStr | None = None
    DEMO_LOGIN_ENABLED: bool = False
    DEMO_LOGIN_EMAIL: str = ""
    LOCKED_DEMO_USER_EMAILS: str = ""
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    TURNSTILE_ENABLED: bool = False
    TURNSTILE_SECRET_KEY: SecretStr | None = None
    TURNSTILE_TIMEOUT_SECONDS: float = 5.0
    OPENCLAW_GATEWAY_URL: str = "ws://127.0.0.1:18789"
    OPENCLAW_GATEWAY_TOKEN: SecretStr | None = None
    OPENCLAW_AGENT_ID: str = "angmoo-1"
    OPENCLAW_AGENT_IDS: str | None = DEFAULT_OPENCLAW_AGENT_IDS
    OPENCLAW_SESSION_KEY: str | None = None
    OPENCLAW_TIMEOUT_SECONDS: int = 300
    AGENT_ACTIVITY_ENGINE: str = "langgraph"
    SERVER_LLM_ENGINE: str = "direct"
    SERVER_LLM_AUTONOMY_MAX_ACTIVE_AGENTS: int = 100
    DIRECT_LLM_DEFAULT_RPM_LIMIT: int = 15
    DIRECT_LLM_RATE_LIMIT_BUFFER_SECONDS: float = 2.0
    DIRECT_LLM_MAX_WAIT_SECONDS: float = 75.0
    DIRECT_LLM_MAX_CALLS_PER_RUN: int = 20
    LANGGRAPH_MAX_STEPS_PER_RUN: int = 26
    LANGGRAPH_MAX_CONCURRENT_GRAPHS: int = 3
    LANGGRAPH_MAX_CONCURRENT_GEMMA_CALLS: int = 1
    LANGGRAPH_SUPERVISOR_THINKING_LEVEL: str = ""
    LANGGRAPH_PLANNER_THINKING_LEVEL: str = "medium"
    LANGGRAPH_RELATIONSHIP_THINKING_LEVEL: str = "medium"
    LANGGRAPH_WRITER_THINKING_LEVEL: str = "medium"
    LANGGRAPH_POST_WRITER_THINKING_LEVEL: str = "medium"
    TENDENCY_ANALYSIS_THINKING_LEVEL: str = "medium"
    RESIDENT_V6_FINAL_ACTION_TIMEOUT_SECONDS: int = 1500
    RESIDENT_V6_WRITING_COMPOSITION_TIMEOUT_SECONDS: int = 420
    OPENCLAW_AUTH_PROFILE_AGENTS_DIR: str | None = None
    OPENCLAW_AUTH_PROFILE_REMOTE_HOST: str | None = None
    OPENCLAW_AUTH_PROFILE_REMOTE_KEY_PATH: str | None = None
    OPENCLAW_AUTH_PROFILE_SSH_TIMEOUT_SECONDS: int = 20
    POLLINATIONS_API_KEY: SecretStr | None = None
    POLLINATIONS_TIMEOUT_SECONDS: int = 25
    POLLINATIONS_IMAGE_RELAY_URL: str = ""
    POLLINATIONS_IMAGE_RELAY_TOKEN: SecretStr | None = None
    POLLINATIONS_IMAGE_ROUTE_MODE: str = ""
    POLLINATIONS_SERVICE_IMAGE_ENABLED: bool = False
    POLLINATIONS_SERVICE_IMAGE_API_KEY: SecretStr | None = None
    POLLINATIONS_SERVICE_IMAGE_MODEL: str = "flux"
    POLLINATIONS_SERVICE_FREE_IMAGES_PER_USER_DAY: int = 3
    POLLINATIONS_SERVICE_MAX_IMAGES_PER_DAY: int = 0
    REPLICATE_IMAGE_API_TOKEN: SecretStr | None = None
    REPLICATE_ZIMAGE_TURBO_LORA_VERSION: str = (
        "197b2db2015aa366d2bc61a941758adf4c31ac66b18573f5c66dc388ab081ca2"
    )
    POLLINATIONS_PROFILE_IMAGE_ENABLED: bool = False
    POLLINATIONS_PROFILE_IMAGE_API_KEY: SecretStr | None = None
    POLLINATIONS_PROFILE_IMAGE_MODEL: str = "zimage"
    POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE: str = "lambda"
    TRANSLATION_PROVIDER: str | None = None
    AZURE_TRANSLATOR_KEY: SecretStr | None = None
    AZURE_TRANSLATOR_REGION: str | None = None
    AZURE_TRANSLATOR_ENDPOINT: str = "https://api.cognitive.microsofttranslator.com"
    TRANSLATION_TIMEOUT_SECONDS: int = 10
    TRANSLATION_MONTHLY_CHAR_LIMIT: int = 1_800_000
    RESIDENT_TICK_SCHEDULER_ENABLED: bool = False
    RESIDENT_TICK_INTERVAL_SECONDS: int = 60
    RESIDENT_TICK_MAX_RUNS: int = 5
    RESIDENT_TICK_POST_ID: str | None = None
    RESIDENT_TICK_INDIVIDUAL_TOOLS_ENABLED: bool = False
    RESIDENT_TICK_SINGLE_FLIGHT_ENABLED: bool = False
    RESIDENT_TICK_INTERVAL_JITTER_MAX_SECONDS: int = 900
    RESIDENT_TICK_ACTIVE_START_SPREAD_SECONDS: int = 1800
    RESIDENT_TICK_INITIAL_SPREAD_SECONDS: int = 600
    RESIDENT_TICK_RETRY_SPREAD_SECONDS: int = 300
    RESIDENT_TICK_BATCH_START_SPACING_SECONDS: int = 10
    POST_IMAGE_JOB_WORKER_ENABLED: bool = False
    POST_IMAGE_JOB_WORKER_INTERVAL_SECONDS: int = 5
    POST_IMAGE_JOB_STALE_SECONDS: int = 600
    RESIDENT_DAYPART_PERSISTENT_SESSION_ENABLED: bool = False
    RESIDENT_DAYPART_PERSISTENT_SESSION_CHARACTER_IDS: str = ""
    RESIDENT_DAYPART_SESSION_RETENTION_DAYS: int = 14
    AGENT_ACTIVITY_MAINTENANCE_ENABLED: bool = False
    AGENT_ACTIVITY_MAINTENANCE_TITLE: str = "앵무 활동 점검 중입니다."
    AGENT_ACTIVITY_MAINTENANCE_MESSAGE: str = (
        "앵무 활동 구조를 안정화하는 작업 중입니다. 작업 동안 자율 활동과 "
        "지금 한 번 활동을 잠시 멈춰두었고, 패치가 완료되면 다시 순차적으로 "
        "재개하겠습니다."
    )
    AGENT_ACTIVITY_MAINTENANCE_AUTO_TICK_ALLOWED_CHARACTER_IDS: str = ""
    AGENT_ACTIVITY_NOTICE_ENABLED: bool = False
    AGENT_ACTIVITY_NOTICE_TITLE: str = ""
    AGENT_ACTIVITY_NOTICE_MESSAGE: str = ""
    MEDIA_ROOT: str = str(BACKEND_DIR / "uploads")
    MEDIA_URL_PATH: str = "/media"
    PUBLIC_BASE_URL: str | None = None
    MEDIA_UPLOAD_MAX_BYTES: int = 5 * 1024 * 1024
    CREDENTIAL_ENCRYPTION_PROVIDER: str = "local"
    OCI_KMS_KEY_ID: str | None = None
    OCI_KMS_CRYPTO_ENDPOINT: str | None = None
    OCI_REGION: str | None = None
    OCI_AUTH_MODE: str = "instance_principal"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        url = str(value)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @field_validator("OPENCLAW_GATEWAY_URL", mode="before")
    @classmethod
    def normalize_openclaw_gateway_url(cls, value: str) -> str:
        url = str(value).strip()
        if url.startswith("http://"):
            return url.replace("http://", "ws://", 1)
        if url.startswith("https://"):
            return url.replace("https://", "wss://", 1)
        return url

    @property
    def project_name(self) -> str:
        return self.PROJECT_NAME

    @property
    def api_v1_prefix(self) -> str:
        return self.API_V1_PREFIX

    @property
    def api_docs_enabled(self) -> bool:
        return self.API_DOCS_ENABLED

    @property
    def app_env(self) -> str:
        return self.APP_ENV

    @property
    def app_secret(self) -> str:
        return self.APP_SECRET.get_secret_value()

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL

    @property
    def seed_demo_data(self) -> bool:
        return self.SEED_DEMO_DATA

    @property
    def signup_enabled(self) -> bool:
        return self.SIGNUP_ENABLED

    @property
    def password_signup_enabled(self) -> bool:
        return self.SIGNUP_ENABLED and self.app_env != "production"

    @property
    def login_throttle_hmac_secret(self) -> str:
        if self.LOGIN_THROTTLE_HMAC_SECRET is not None:
            value = self.LOGIN_THROTTLE_HMAC_SECRET.get_secret_value().strip()
            if value:
                return value
        return self.app_secret

    @property
    def official_operator_user_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                item.strip()
                for item in self.OFFICIAL_OPERATOR_USER_IDS.split(",")
                if item.strip()
            )
        )

    @property
    def demo_user_password(self) -> str | None:
        if self.DEMO_USER_PASSWORD is None:
            return None
        password = self.DEMO_USER_PASSWORD.get_secret_value()
        return password or None

    @property
    def demo_login_enabled(self) -> bool:
        return self.DEMO_LOGIN_ENABLED

    @property
    def demo_login_email(self) -> str | None:
        value = self.DEMO_LOGIN_EMAIL.strip().lower()
        return value or None

    @property
    def locked_demo_user_emails(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                item.strip().lower()
                for item in self.LOCKED_DEMO_USER_EMAILS.split(",")
                if item.strip()
            )
        )

    @property
    def google_oauth_client_id(self) -> str | None:
        value = self.GOOGLE_OAUTH_CLIENT_ID
        return value.strip() if value else None

    @property
    def turnstile_enabled(self) -> bool:
        return self.TURNSTILE_ENABLED

    @property
    def turnstile_secret_key(self) -> str | None:
        if self.TURNSTILE_SECRET_KEY is None:
            return None
        value = self.TURNSTILE_SECRET_KEY.get_secret_value().strip()
        return value or None

    @property
    def turnstile_timeout_seconds(self) -> float:
        return max(1.0, self.TURNSTILE_TIMEOUT_SECONDS)

    @property
    def openclaw_gateway_url(self) -> str:
        return self.OPENCLAW_GATEWAY_URL

    @property
    def openclaw_gateway_token(self) -> str | None:
        if self.OPENCLAW_GATEWAY_TOKEN is None:
            return None
        token = self.OPENCLAW_GATEWAY_TOKEN.get_secret_value().strip()
        return token or None

    @property
    def openclaw_agent_id(self) -> str:
        return self.OPENCLAW_AGENT_ID

    @property
    def openclaw_agent_ids(self) -> list[str]:
        raw = self.OPENCLAW_AGENT_IDS
        if raw is None:
            return [self.openclaw_agent_id]
        agent_ids = [item.strip() for item in raw.split(",") if item.strip()]
        return agent_ids or [self.openclaw_agent_id]

    @property
    def openclaw_session_key(self) -> str:
        return self.openclaw_session_key_for(self.openclaw_agent_id)

    def openclaw_session_key_for(self, agent_id: str) -> str:
        if self.OPENCLAW_SESSION_KEY:
            return self.OPENCLAW_SESSION_KEY
        return f"agent:{agent_id}:angmoo-community-poc"

    @property
    def openclaw_timeout_seconds(self) -> int:
        return self.OPENCLAW_TIMEOUT_SECONDS

    @property
    def agent_activity_engine(self) -> str:
        value = self.AGENT_ACTIVITY_ENGINE.strip().lower()
        return value if value in {"openclaw", "langgraph"} else "langgraph"

    @property
    def server_llm_engine(self) -> str:
        value = self.SERVER_LLM_ENGINE.strip().lower()
        return value if value in {"openclaw", "direct"} else "direct"

    @property
    def server_llm_autonomy_max_active_agents(self) -> int:
        return max(0, self.SERVER_LLM_AUTONOMY_MAX_ACTIVE_AGENTS)

    @property
    def direct_llm_default_rpm_limit(self) -> int:
        return max(1, self.DIRECT_LLM_DEFAULT_RPM_LIMIT)

    @property
    def direct_llm_rate_limit_buffer_seconds(self) -> float:
        return max(0.0, self.DIRECT_LLM_RATE_LIMIT_BUFFER_SECONDS)

    @property
    def direct_llm_max_wait_seconds(self) -> float:
        return max(0.0, self.DIRECT_LLM_MAX_WAIT_SECONDS)

    @property
    def direct_llm_max_calls_per_run(self) -> int:
        return max(1, self.DIRECT_LLM_MAX_CALLS_PER_RUN)

    @property
    def langgraph_max_steps_per_run(self) -> int:
        return max(3, self.LANGGRAPH_MAX_STEPS_PER_RUN)

    @property
    def langgraph_max_concurrent_graphs(self) -> int:
        return max(1, self.LANGGRAPH_MAX_CONCURRENT_GRAPHS)

    @property
    def langgraph_max_concurrent_gemma_calls(self) -> int:
        return max(1, self.LANGGRAPH_MAX_CONCURRENT_GEMMA_CALLS)

    def _normalized_langgraph_thinking_level(self, value: str) -> str | None:
        normalized = value.strip().lower()
        return normalized if normalized in {"minimal", "low", "medium", "high"} else None

    @property
    def langgraph_supervisor_thinking_level(self) -> str | None:
        return self._normalized_langgraph_thinking_level(
            self.LANGGRAPH_SUPERVISOR_THINKING_LEVEL
        )

    @property
    def langgraph_planner_thinking_level(self) -> str | None:
        return self._normalized_langgraph_thinking_level(
            self.LANGGRAPH_PLANNER_THINKING_LEVEL
        )

    @property
    def langgraph_relationship_thinking_level(self) -> str | None:
        return self._normalized_langgraph_thinking_level(
            self.LANGGRAPH_RELATIONSHIP_THINKING_LEVEL
        )

    @property
    def langgraph_writer_thinking_level(self) -> str | None:
        return self._normalized_langgraph_thinking_level(
            self.LANGGRAPH_WRITER_THINKING_LEVEL
        )

    @property
    def langgraph_post_writer_thinking_level(self) -> str | None:
        return self._normalized_langgraph_thinking_level(
            self.LANGGRAPH_POST_WRITER_THINKING_LEVEL
        )

    @property
    def tendency_analysis_thinking_level(self) -> str | None:
        return self._normalized_langgraph_thinking_level(
            self.TENDENCY_ANALYSIS_THINKING_LEVEL
        )

    @property
    def resident_v6_final_action_timeout_seconds(self) -> int:
        return max(self.openclaw_timeout_seconds, self.RESIDENT_V6_FINAL_ACTION_TIMEOUT_SECONDS)

    @property
    def resident_v6_writing_composition_timeout_seconds(self) -> int:
        return max(
            self.openclaw_timeout_seconds,
            self.RESIDENT_V6_WRITING_COMPOSITION_TIMEOUT_SECONDS,
        )

    @property
    def resident_daypart_persistent_session_enabled(self) -> bool:
        return self.RESIDENT_DAYPART_PERSISTENT_SESSION_ENABLED

    @property
    def resident_daypart_persistent_session_character_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                item.strip()
                for item in self.RESIDENT_DAYPART_PERSISTENT_SESSION_CHARACTER_IDS.split(",")
                if item.strip()
            )
        )

    @property
    def resident_daypart_session_retention_days(self) -> int:
        return max(1, self.RESIDENT_DAYPART_SESSION_RETENTION_DAYS)

    @property
    def openclaw_auth_profile_agents_dir(self) -> str | None:
        value = self.OPENCLAW_AUTH_PROFILE_AGENTS_DIR
        return value.strip() if value else None

    @property
    def openclaw_auth_profile_remote_host(self) -> str | None:
        value = self.OPENCLAW_AUTH_PROFILE_REMOTE_HOST
        return value.strip() if value else None

    @property
    def openclaw_auth_profile_remote_key_path(self) -> str | None:
        value = self.OPENCLAW_AUTH_PROFILE_REMOTE_KEY_PATH
        return value.strip() if value else None

    @property
    def openclaw_auth_profile_ssh_timeout_seconds(self) -> int:
        return self.OPENCLAW_AUTH_PROFILE_SSH_TIMEOUT_SECONDS

    @property
    def pollinations_api_key(self) -> str | None:
        if self.POLLINATIONS_API_KEY is None:
            return None
        value = self.POLLINATIONS_API_KEY.get_secret_value().strip()
        return value or None

    @property
    def pollinations_timeout_seconds(self) -> int:
        return max(10, self.POLLINATIONS_TIMEOUT_SECONDS)

    @property
    def pollinations_image_relay_url(self) -> str | None:
        value = self.POLLINATIONS_IMAGE_RELAY_URL.strip()
        if not value.startswith("https://"):
            return None
        return value

    @property
    def pollinations_image_relay_token(self) -> str | None:
        if self.POLLINATIONS_IMAGE_RELAY_TOKEN is None:
            return None
        value = self.POLLINATIONS_IMAGE_RELAY_TOKEN.get_secret_value().strip()
        return value or None

    @property
    def pollinations_image_route_mode(self) -> str:
        value = self.POLLINATIONS_IMAGE_ROUTE_MODE.strip().lower()
        return value if value in {"direct", "lambda"} else "direct"

    @property
    def pollinations_service_image_api_key(self) -> str | None:
        if self.POLLINATIONS_SERVICE_IMAGE_API_KEY is None:
            return None
        value = self.POLLINATIONS_SERVICE_IMAGE_API_KEY.get_secret_value().strip()
        return value or None

    @property
    def pollinations_service_image_enabled(self) -> bool:
        return (
            self.POLLINATIONS_SERVICE_IMAGE_ENABLED
            and self.pollinations_service_image_api_key is not None
        )

    @property
    def pollinations_service_image_model(self) -> str:
        return self.POLLINATIONS_SERVICE_IMAGE_MODEL.strip() or "flux"

    @property
    def replicate_image_api_token(self) -> str | None:
        if self.REPLICATE_IMAGE_API_TOKEN is None:
            return None
        value = self.REPLICATE_IMAGE_API_TOKEN.get_secret_value().strip()
        return value or None

    @property
    def replicate_zimage_turbo_lora_version(self) -> str:
        return self.REPLICATE_ZIMAGE_TURBO_LORA_VERSION.strip()

    @property
    def pollinations_service_free_images_per_user_day(self) -> int:
        return max(0, self.POLLINATIONS_SERVICE_FREE_IMAGES_PER_USER_DAY)

    @property
    def pollinations_service_max_images_per_day(self) -> int:
        return max(0, self.POLLINATIONS_SERVICE_MAX_IMAGES_PER_DAY)

    @property
    def pollinations_profile_image_api_key(self) -> str | None:
        if self.POLLINATIONS_PROFILE_IMAGE_API_KEY is None:
            return None
        value = self.POLLINATIONS_PROFILE_IMAGE_API_KEY.get_secret_value().strip()
        return value or None

    @property
    def pollinations_profile_image_enabled(self) -> bool:
        return (
            self.POLLINATIONS_PROFILE_IMAGE_ENABLED
            and self.pollinations_profile_image_api_key is not None
        )

    @property
    def pollinations_profile_image_model(self) -> str:
        return self.POLLINATIONS_PROFILE_IMAGE_MODEL.strip() or "zimage"

    @property
    def pollinations_profile_image_route_mode(self) -> str:
        value = self.POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE.strip().lower()
        return value if value in {"direct", "lambda"} else "lambda"

    @property
    def public_base_url(self) -> str | None:
        value = (self.PUBLIC_BASE_URL or "").strip().rstrip("/")
        if not value.startswith("https://"):
            return None
        return value

    @property
    def translation_provider(self) -> str | None:
        value = (self.TRANSLATION_PROVIDER or "").strip().lower()
        return value or None

    @property
    def azure_translator_key(self) -> str | None:
        if self.AZURE_TRANSLATOR_KEY is None:
            return None
        value = self.AZURE_TRANSLATOR_KEY.get_secret_value().strip()
        return value or None

    @property
    def azure_translator_region(self) -> str | None:
        value = (self.AZURE_TRANSLATOR_REGION or "").strip()
        return value or None

    @property
    def azure_translator_endpoint(self) -> str:
        return self.AZURE_TRANSLATOR_ENDPOINT.strip().rstrip("/")

    @property
    def translation_timeout_seconds(self) -> int:
        return max(3, self.TRANSLATION_TIMEOUT_SECONDS)

    @property
    def translation_monthly_char_limit(self) -> int:
        return max(0, self.TRANSLATION_MONTHLY_CHAR_LIMIT)

    @property
    def resident_tick_scheduler_enabled(self) -> bool:
        return self.RESIDENT_TICK_SCHEDULER_ENABLED

    @property
    def resident_tick_interval_seconds(self) -> int:
        return max(10, self.RESIDENT_TICK_INTERVAL_SECONDS)

    @property
    def resident_tick_max_runs(self) -> int:
        return max(1, min(10, self.RESIDENT_TICK_MAX_RUNS))

    @property
    def resident_tick_post_id(self) -> str | None:
        value = self.RESIDENT_TICK_POST_ID
        return value.strip() if value else None

    @property
    def resident_tick_individual_tools_enabled(self) -> bool:
        return self.RESIDENT_TICK_INDIVIDUAL_TOOLS_ENABLED

    @property
    def resident_tick_single_flight_enabled(self) -> bool:
        return self.RESIDENT_TICK_SINGLE_FLIGHT_ENABLED

    @property
    def resident_tick_interval_jitter_max_seconds(self) -> int:
        return max(0, self.RESIDENT_TICK_INTERVAL_JITTER_MAX_SECONDS)

    @property
    def resident_tick_active_start_spread_seconds(self) -> int:
        return max(0, self.RESIDENT_TICK_ACTIVE_START_SPREAD_SECONDS)

    @property
    def resident_tick_initial_spread_seconds(self) -> int:
        return max(0, self.RESIDENT_TICK_INITIAL_SPREAD_SECONDS)

    @property
    def resident_tick_retry_spread_seconds(self) -> int:
        return max(0, self.RESIDENT_TICK_RETRY_SPREAD_SECONDS)

    @property
    def resident_tick_batch_start_spacing_seconds(self) -> int:
        return max(0, self.RESIDENT_TICK_BATCH_START_SPACING_SECONDS)

    @property
    def post_image_job_worker_enabled(self) -> bool:
        return self.POST_IMAGE_JOB_WORKER_ENABLED

    @property
    def post_image_job_worker_interval_seconds(self) -> int:
        return max(1, self.POST_IMAGE_JOB_WORKER_INTERVAL_SECONDS)

    @property
    def post_image_job_stale_seconds(self) -> int:
        return max(60, self.POST_IMAGE_JOB_STALE_SECONDS)

    @property
    def agent_activity_maintenance_enabled(self) -> bool:
        return self.AGENT_ACTIVITY_MAINTENANCE_ENABLED

    @property
    def agent_activity_maintenance_auto_tick_allowed_character_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                item.strip()
                for item in self.AGENT_ACTIVITY_MAINTENANCE_AUTO_TICK_ALLOWED_CHARACTER_IDS.split(
                    ","
                )
                if item.strip()
            )
        )

    @property
    def agent_activity_maintenance_title(self) -> str:
        return self.AGENT_ACTIVITY_MAINTENANCE_TITLE.strip() or "앵무 활동 점검 중입니다."

    @property
    def agent_activity_maintenance_message(self) -> str:
        value = self.AGENT_ACTIVITY_MAINTENANCE_MESSAGE.strip()
        if value:
            return value
        return (
            "앵무 활동 구조를 안정화하는 작업 중입니다. 작업 동안 자율 활동과 "
            "지금 한 번 활동을 잠시 멈춰두었고, 패치가 완료되면 다시 순차적으로 "
            "재개하겠습니다."
        )

    @property
    def agent_activity_notice_enabled(self) -> bool:
        return self.AGENT_ACTIVITY_NOTICE_ENABLED

    @property
    def agent_activity_notice_title(self) -> str:
        return self.AGENT_ACTIVITY_NOTICE_TITLE.strip()

    @property
    def agent_activity_notice_message(self) -> str:
        return self.AGENT_ACTIVITY_NOTICE_MESSAGE.strip()

    @property
    def media_root_path(self) -> Path:
        return Path(self.MEDIA_ROOT).resolve()

    @property
    def media_url_path(self) -> str:
        path = self.MEDIA_URL_PATH.strip() or "/media"
        return "/" + path.strip("/")

    @property
    def media_upload_max_bytes(self) -> int:
        return max(1, self.MEDIA_UPLOAD_MAX_BYTES)

    @property
    def credential_encryption_provider(self) -> str:
        return self.CREDENTIAL_ENCRYPTION_PROVIDER.strip().lower() or "local"

    @property
    def oci_kms_key_id(self) -> str | None:
        value = self.OCI_KMS_KEY_ID
        return value.strip() if value else None

    @property
    def oci_kms_crypto_endpoint(self) -> str | None:
        value = self.OCI_KMS_CRYPTO_ENDPOINT
        return value.strip() if value else None

    @property
    def oci_region(self) -> str | None:
        value = self.OCI_REGION
        return value.strip() if value else None

    @property
    def oci_auth_mode(self) -> str:
        return self.OCI_AUTH_MODE.strip().lower() or "instance_principal"


settings = Settings()
