"""Existing upload, parser capacity, embedding, and recall bounds."""

from datetime import timedelta
import os
from zoneinfo import ZoneInfo


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_LORE_FILE_BYTES = 10 * 1024 * 1024
LORE_UPLOAD_READ_CHUNK_BYTES = 64 * 1024
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
MAX_DOCX_ENTRIES = 500
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
MAX_DOCX_ENTRY_BYTES = 10 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 100
MAX_PDF_PAGES = 200
MAX_PDF_OBJECTS = 20_000
MAX_PARSED_TEXT_CHARS = 100_000
# Windows uses the spawn multiprocessing start method and must import the
# application module graph in the isolated child.  Real-time antivirus scanning
# can make that startup alone exceed the POSIX parser budget even for a tiny,
# valid document.  Keep the parser isolated and bounded while allowing the
# measured Windows startup overhead.
LORE_PARSER_TIMEOUT_SECONDS = 15.0 if os.name == "nt" else 8.0
LORE_PARSER_MEMORY_BYTES = 512 * 1024 * 1024
LORE_PARSER_CPU_SECONDS = 6
MAX_LORE_SOURCES_PER_CHARACTER = 1
MAX_LORE_TEXT_CHARS_PER_CHARACTER = 50_000
MAX_LORE_CHUNKS_PER_CHARACTER = 100
TARGET_CHUNK_MIN_CHARS = 500
TARGET_CHUNK_TARGET_CHARS = 750
TARGET_CHUNK_MAX_CHARS = 1000
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSION = 768
RETRIEVAL_CANDIDATE_LIMIT = 30
RETRIEVAL_FINAL_LIMIT = 5
RECENT_LORE_USAGE_LIMIT = 12
RECENT_LORE_STRONG_PENALTY_WINDOW = timedelta(days=2)
RECENT_LORE_SOFT_PENALTY_WINDOW = timedelta(days=7)
APP_TIMEZONE = ZoneInfo("Asia/Seoul")

GLOBAL_ACTIVE_LIMIT = 2
SUBJECT_ACTIVE_LIMIT = 1
LEASE_SECONDS = 30
RETRY_AFTER_SECONDS = 2
