from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .migrate import run_migrations
from .seed import seed_exercises
from .routers import profile, program, sessions, exercises, pain, stats, review

run_migrations()
Base.metadata.create_all(bind=engine)
run_migrations()  # ensure new columns on newly-created or pre-existing tables
seed_exercises()

app = FastAPI(title="Workout Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router, prefix="/api")
app.include_router(program.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(exercises.router, prefix="/api")
app.include_router(pain.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(review.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
