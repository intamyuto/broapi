from uuid import UUID, uuid4
from datetime import datetime

import enum

from sqlmodel import SQLModel, Field, MetaData, Enum
from sqlalchemy import JSON, Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB


class User(SQLModel, table=True):
    __tablename__ = "users"

    sid: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    username: str
    ref_code: str | None
    refs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    score: int | None
    last_score: int | None
    energy: int
    tickets: int | None
    boxes: int | None
    ton_balanse: float
    mining_claim: bool | None
    last_tap: datetime | None
    last_login: datetime | None
    reward_streak: int | None
    region: str | None
    ip_addr: str | None
    advertising_limit: int | None

class ReferalScore(SQLModel, table=True):
    __tablename__ = "referals_score"

    username: str = Field(primary_key=True)
    score: int

class PVPCharacter(SQLModel, table=True):
    __tablename__ = "characters"

    metadata = MetaData(schema="pvp")

    user_id: int = Field(primary_key=True)
    username: str | None

    ts_updated: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    abilities: dict = Field(sa_type=JSONB, nullable=False)
    level: int
    experience: int
    power: float

    ts_last_match: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    energy_last_match: int
    energy_max: int
    energy_boost: int

    ts_invulnerable_until: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    ts_defences_today: int 

class MatchResult(str, enum.Enum):
    win = 'win'
    lose = 'lose'

class PVPMatch(SQLModel, table=True):
    __tablename__ = 'matches'

    metadata = MetaData(schema="pvp")

    uuid: UUID = Field(default_factory=uuid4, primary_key=True, index=True, nullable=False)
    ts_created: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    ts_updated: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    player_id: int # = Field(foreign_key="characters.user_id")
    opponent_id: int # = Field(foreign_key="characters.user_id")

    ts_finished: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    result: MatchResult | None = Field(sa_column=Column(Enum(MatchResult, name="match_result", inherit_schema=True), nullable=True))
    loot: dict = Field(sa_type=JSONB, nullable=True)

    stats: dict = Field(sa_type=JSONB, nullable=True)
