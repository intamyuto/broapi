from datetime import timedelta
from uuid import UUID
from enum import Enum

import math

from typing import Optional
from pydantic import BaseModel, Field

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


class GetEnergy(BaseModel):
    energy: int

class GetEnergyResponse(BaseModel):
    link: str

_coeffecients = {
    'strength': 2.595,
    'defence': 2.3425,
    'speed': 2.270,
    'weight': 2.380,
    'combinations': 2.470
}

class AbilityScoresDelta(BaseModel):
    strength: int | None = None
    defence: int | None = None
    speed: int | None = None
    weight: int | None = None
    combinations: int | None = None

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
        return self.strength * _coeffecients['strength'] \
            + self.defence * _coeffecients['defence'] \
            + self.speed * _coeffecients['speed'] \
            + self.weight * _coeffecients['weight'] \
            + self.combinations * _coeffecients['combinations']

    def upgrade_cost(self, delta: AbilityScoresDelta) -> int:
        cost = 0
        if delta.strength is not None:
            cost += self._ability_cost('strength', self.strength + delta.strength)
        if delta.defence is not None:
            cost += self._ability_cost('defence', self.defence + delta.defence)
        if delta.speed is not None:
            cost += self._ability_cost('speed', self.speed + delta.speed)
        if delta.weight is not None:
            cost += self._ability_cost('weight', self.weight + delta.weight)
        if delta.combinations is not None:
            cost += self._ability_cost('combinations', self.combinations + delta.combinations)
        return cost
    
    def upgrade(self, delta: AbilityScoresDelta):
        if delta.strength:
            self.strength += delta.strength
        if delta.defence:
            self.defence += delta.defence
        if delta.speed:
            self.speed += delta.speed
        if delta.weight:
            self.weight += delta.weight
        if delta.combinations:
            self.combinations += delta.combinations

    def _ability_cost(self, ability_name: str, level_target: int) -> int:
        level_current, cost = getattr(self, ability_name), 0
        for level in range(level_current, level_target):
            cost += math.pow(level, _coeffecients[ability_name])
        return math.ceil(cost)
    
class LevelupResponse(BaseModel):
    abilities: AbilityScores
    power: int

class CharacterEnergy(BaseModel):
    remaining: int
    maximum: int
    time_to_restore: timedelta

class CharacterProfile(BaseModel):
    abilities: AbilityScores
    energy: CharacterEnergy
    level: int
    experience: int
    power: int

class MatchCompetitioner(BaseModel):
    user_id: int
    username: str
    level: int
    power: int
    abilities: AbilityScores

class PVPMatch(BaseModel):
    match_id: UUID
    player: MatchCompetitioner
    opponent: MatchCompetitioner

class MatchResult(str, Enum):
    win = "win"
    lose = "lose"

class MatchLoot(BaseModel):
    coins: int

class PVPMatchResult(BaseModel):
    result: MatchResult
    loot: Optional[MatchLoot] = Field(None)

