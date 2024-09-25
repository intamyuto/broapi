from fastapi import FastAPI, APIRouter

from .routers import users

app = FastAPI()

api = APIRouter()
api.include_router(users.router)

app.include_router(api, prefix='/api/v1')