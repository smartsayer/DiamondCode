from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.api.routes import games

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: could warm caches or init DB here
    yield
    # Shutdown cleanup if needed


app = FastAPI(
    title="DiamondCode API",
    description="Daily MLB under betting scanner — scores every game 0-100 across 5 weighted factors.",
    version="1.0.0",
    lifespan=lifespan,
)

import os
_extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:3001", *_extra_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
