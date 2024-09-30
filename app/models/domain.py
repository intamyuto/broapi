from datetime import timedelta
from uuid import UUID
from enum import Enum

import json

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

    @classmethod
    def default(cls):
        return cls(strength=1, defence=1, speed=1, weight=1, combinations=1)
    
    def power(self) -> float:
        return self.strength * 2.595 \
            + self.defence * 2.3425 \
            + self.speed * 2.27 \
            + self.weight * 2.38 \
            + self.combinations * 2.47

class AbilityScoresDelta(BaseModel):
    strength: int | None
    defence: int | None
    speed: int | None
    weight: int | None
    combinations: int | None

class LevelupRequest(BaseModel):
    abilities_delta: AbilityScoresDelta

class CharacterEnergy(BaseModel):
    remaining: int
    maximum: int
    time_to_restore: timedelta

class CharacterProfile(BaseModel):
    abilities: AbilityScores
    energy: CharacterEnergy
    level: int
    experience: int
    power: float

class MatchCompetitioner(BaseModel):
    user_id: str
    username: str
    level: int
    power: float
    abilities: AbilityScores

class PVPMatch(BaseModel):
    match_id: UUID
    player: MatchCompetitioner
    opponent: MatchCompetitioner

class MatchResult(str, Enum):
    win = "win"
    lose = "lose"

class MatchLoot(BaseModel):
    experience: int
    coins: int

class PVPMatchResult(BaseModel):
    match_id: UUID
    result: MatchResult
    loot: MatchLoot | None

