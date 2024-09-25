from uuid import UUID, uuid4
from datetime import datetime
from sqlmodel import SQLModel, Field

class User(SQLModel, table=True):
    __tablename__ = "users"

    sid: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    username: str
    score: int | None
    tickets: int | None
    boxes: int | None
    ton_balanse: float
    mining_claim: bool | None
    last_tap: datetime | None