from typing import Optional
from datetime import datetime
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


        