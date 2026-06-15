from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from resume_matcher.api.v1.analyze import router as analyze_router
from resume_matcher.api.v1.router import router as v1_router
from resume_matcher.core.exceptions import AppError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "out"


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Resume Matcher API",
        description="Resume-JD match scoring with NLP + Gemini",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message, "details": exc.details},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": str(exc)},
        )

    @app.get("/")
    async def root_meta():
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))

        return {
            "service": "AI Resume Matcher API",
            "version": app.version,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    app.include_router(v1_router, prefix="/api/v1")
    app.include_router(analyze_router, prefix="/api")

    if STATIC_DIR.exists():
        next_assets = STATIC_DIR / "_next"
        if next_assets.exists():
            app.mount("/_next", StaticFiles(directory=str(next_assets)), name="nextjs_assets")

        @app.get("/{full_path:path}")
        async def serve_frontend(request: Request, full_path: str):
            file_path = STATIC_DIR / full_path
            if file_path.is_file():
                return FileResponse(str(file_path))

            index = STATIC_DIR / "index.html"
            if index.exists():
                return FileResponse(str(index))

            return JSONResponse(status_code=404, content={"error": "not_found"})

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("resume_matcher.main:app", host="0.0.0.0", port=8000, reload=True)
