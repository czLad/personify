"""Personify FastAPI application entrypoint."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, autofill, health, history, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    print(f"🚀 Personify backend starting in {settings.environment} mode")
    yield
    print("👋 Personify backend shutting down")


app = FastAPI(
    title="Personify API",
    description="Backend for the Personify agentic Chrome extension.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the dashboard and the extension to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(upload.router, prefix="/upload", tags=["upload"])
app.include_router(autofill.router, prefix="/autofill", tags=["autofill"])
app.include_router(history.router, prefix="/history", tags=["history"])


@app.get("/")
def root():
    return {
        "service": "personify-backend",
        "version": "0.1.0",
        "docs": "/docs",
    }
