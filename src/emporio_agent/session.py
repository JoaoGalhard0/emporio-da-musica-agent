import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# Guessing order numbers must not be possible, so verification locks after a few misses.
MAX_FAILED_VERIFICATIONS = 3


@dataclass
class Session:
    """One customer conversation: message history plus the identity state the *code* controls.

    `verified_customers` is only ever written by the order tools after a successful check, never by the
    model, so a prompt injection cannot grant access.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    messages: list[dict] = field(default_factory=list)  # excludes the system prompt
    verified_customers: set[int] = field(default_factory=set)
    failed_verifications: int = 0

    @property
    def locked(self) -> bool:
        return self.failed_verifications >= MAX_FAILED_VERIFICATIONS

    def to_json(self) -> str:
        data = {
            "id": self.id,
            "messages": self.messages,
            "verified_customers": sorted(self.verified_customers),
            "failed_verifications": self.failed_verifications,
        }
        return json.dumps(data, ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, raw: str) -> "Session":
        data = json.loads(raw)
        return cls(
            id=data["id"],
            messages=data["messages"],
            verified_customers=set(data["verified_customers"]),
            failed_verifications=data["failed_verifications"],
        )

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.id}.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load(cls, directory: Path, session_id: str) -> "Session":
        return cls.from_json((directory / f"{session_id}.json").read_text(encoding="utf-8"))
