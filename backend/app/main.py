from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import cors_origins
from .database import init_db
from .routes import analytics, health, leads

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="LeadIQ – AI-Based Lead Scoring API",
    description=("Deterministic, explainable lead scoring. Scores come from a weighted rule "
                 "engine; Google Gemini only generates explanations and recommendations."),
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(health.router)
app.include_router(leads.router)
app.include_router(analytics.router)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    logging.getLogger("leadiq").exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
