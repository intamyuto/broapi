import os

from fastapi import FastAPI, APIRouter, Request
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from .routers import users

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

@app.middleware('http')
async def fitler_orgins(request: Request, call_next):
    origin = request.headers.get('Origin')
    print(origin)
    print(origins)
    if origin not in origins:
        return JSONResponse({'error': 'invalid origin'}, status_code=403)
    return await call_next(request)

api = APIRouter()
api.include_router(users.router)

app.include_router(api, prefix='/api/v1')