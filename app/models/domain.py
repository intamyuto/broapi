from uuid import UUID
from enum import Enum

from typing import Optional
from pydantic import BaseModel

class UserMining(BaseModel):
    left: str
    claim: bool

class UserAdvertising(BaseModel):
    limit: int
    total: int

class User(BaseModel):
    score: int
    tickets: int
    boxes: int
    ton_balance: float
    mining: UserMining
    advertising: UserAdvertising

class CreateUser(BaseModel):
    username: str
    user_id: str
    ref_code: Optional[str] = None
    premium: Optional[bool] = None


class AbilityScores(BaseModel):
    strength: int
    defence: int
    speed: int
    weight: int
    combinations: int

class AbilityScoresDelta(BaseModel):
    strength: int | None
    defence: int | None
    speed: int | None
    weight: int | None
    combinations: int | None

class LevelupRequest(BaseModel):
    abilities_delta: AbilityScoresDelta

class CharacterProfile(BaseModel):
    abilities: AbilityScores
    level: int
    experience: int
    power: float

class MatchCompetitioner(BaseModel):
    user_id: str
    power: float

class PVPMatch(BaseModel):
    match_id: UUID
    player: MatchCompetitioner
    enemy: MatchCompetitioner

class MatchResult(str, Enum):
    win = "win"
    lose = "lose"

class MatchPrize(BaseModel):
    experience: int
    coins: int

class PVPMatchResult(BaseModel):
    match_id: UUID
    result: MatchResult
    prize: MatchPrize | None

