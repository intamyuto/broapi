import os

from fastapi import FastAPI, APIRouter, Request
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from .routers import users, pvp

origins = os.getenv('BROAPI_ALLOW_ORIGINS').split(',')

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=['GET', 'POST']
    )
]

app = FastAPI(middleware=middleware)

whitelist = [
    "/favicon.ico",
    "/openapi.json",
    "/docs",
    "/redoc"
]

@app.middleware('http')
async def fitler_orgins(request: Request, call_next):
    origin = request.headers.get('Origin')
    if origin not in origins and request.url.path not in whitelist:
        return JSONResponse({'error': 'invalid origin'}, status_code=403)
    return await call_next(request)

api = APIRouter()
api.include_router(users.router)
api.include_router(pvp.router)

app.include_router(api, prefix='/api/v1')