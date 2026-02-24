"""
Environment and runtime configuration for the Envelope Estimator Agent.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnthropicConfig:
    api_key: str = ""
    model_vision: str = "claude-opus-4-6"       # primary - PDF blueprint reading
    model_verify: str = "claude-sonnet-4-6"      # verification pass
    model_fast: str = "claude-haiku-4-5-20251001"  # lightweight tasks
    max_tokens: int = 8192


@dataclass
class QdrantConfig:
    host: str = "localhost"
    port: int = 6333
    collection: str = "ddc_cwicr_en"  # default to English/Toronto pricing
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    top_k: int = 5  # number of search results per query


@dataclass
class OpenAIConfig:
    """For DDC-CWICR embedding generation (vector search)."""
    api_key: str = ""
    embedding_model: str = "text-embedding-3-large"


@dataclass
class EmailConfig:
    """IMAP configuration for monitoring ITB emails."""
    imap_server: str = ""
    imap_port: int = 993
    username: str = ""
    password: str = ""
    watched_folder: str = "INBOX"
    itb_label: str = "ITB"  # label/folder to watch for bids
    check_interval_seconds: int = 300  # 5 minutes
    allowed_senders: list[str] = field(default_factory=list)


@dataclass
class CompanyProfile:
    """Your company info for proposals."""
    name: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""
    email: str = ""
    license_number: str = ""
    logo_path: str = ""
    # Default financial markups
    overhead_percent: float = 0.10       # 10% overhead
    profit_percent: float = 0.10         # 10% profit
    bond_percent: float = 0.0            # bonding if required
    tax_rate: float = 0.0                # sales tax on materials
    # Proposal defaults
    proposal_validity_days: int = 30
    default_payment_terms: str = "Net 30"
    warranty_years: int = 1


@dataclass
class WatchedFolderConfig:
    """Watch a local folder for dropped-in plan PDFs."""
    enabled: bool = False
    path: str = ""
    check_interval_seconds: int = 30
    archive_processed: bool = True


@dataclass
class Settings:
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    company: CompanyProfile = field(default_factory=CompanyProfile)
    watched_folder: WatchedFolderConfig = field(default_factory=WatchedFolderConfig)

    # Runtime
    output_dir: str = "./output"
    log_level: str = "INFO"
    enabled_phases: list[int] = field(default_factory=lambda: [1])  # start with Phase 1
    region: str = "en"  # DDC-CWICR region code
    currency: str = "USD"

    # Validation thresholds
    max_variance_percent: float = 2.0    # 4-way validation tolerance
    confidence_threshold: float = 0.85   # minimum confidence for auto-accept
    require_human_review: bool = True     # require approval before sending


def load_settings() -> Settings:
    """Load settings from environment variables."""
    settings = Settings()

    # Anthropic
    settings.anthropic.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    # OpenAI (for embeddings)
    settings.openai.api_key = os.getenv("OPENAI_API_KEY", "")

    # Qdrant
    settings.qdrant.host = os.getenv("QDRANT_HOST", "localhost")
    settings.qdrant.port = int(os.getenv("QDRANT_PORT", "6333"))
    settings.qdrant.collection = os.getenv(
        "QDRANT_COLLECTION", "ddc_cwicr_en"
    )

    # Email
    settings.email.imap_server = os.getenv("IMAP_SERVER", "")
    settings.email.username = os.getenv("IMAP_USERNAME", "")
    settings.email.password = os.getenv("IMAP_PASSWORD", "")

    # Company
    settings.company.name = os.getenv("COMPANY_NAME", "")
    settings.company.phone = os.getenv("COMPANY_PHONE", "")
    settings.company.email = os.getenv("COMPANY_EMAIL", "")
    settings.company.license_number = os.getenv("COMPANY_LICENSE", "")
    settings.company.overhead_percent = float(
        os.getenv("OVERHEAD_PERCENT", "0.10")
    )
    settings.company.profit_percent = float(
        os.getenv("PROFIT_PERCENT", "0.10")
    )

    # Watched folder
    watched = os.getenv("WATCHED_FOLDER_PATH", "")
    if watched:
        settings.watched_folder.enabled = True
        settings.watched_folder.path = watched

    # Output
    settings.output_dir = os.getenv("OUTPUT_DIR", "./output")
    settings.log_level = os.getenv("LOG_LEVEL", "INFO")
    settings.region = os.getenv("DDC_REGION", "en")
    settings.currency = os.getenv("CURRENCY", "USD")

    # Phases
    phases = os.getenv("ENABLED_PHASES", "1")
    settings.enabled_phases = [int(p.strip()) for p in phases.split(",")]

    return settings
