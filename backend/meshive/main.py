from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from meshive import __version__
from meshive.api.auth import router as auth_router
from meshive.api.backups import router as backups_router
from meshive.api.catalog import admin_router as catalog_admin_router
from meshive.api.catalog import router as catalog_router
from meshive.api.creator_links import router as creator_links_router
from meshive.api.favorites import router as favorites_router
from meshive.api.library_sources import router as library_sources_router
from meshive.api.recovery import router as recovery_router
from meshive.api.scans import router as scans_router
from meshive.api.setup import router as setup_router
from meshive.api.system import router as system_router
from meshive.api.tags import admin_router as tags_admin_router
from meshive.api.tags import router as tags_router
from meshive.api.users import router as users_router
from meshive.config import get_settings
from meshive.services.backup_scheduler import start_scheduler, stop_scheduler
from meshive.services.scan_scheduler import (
    start_scheduler as start_scan_scheduler,
    stop_scheduler as stop_scan_scheduler,
)
from meshive.security import is_cross_site_api_request

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    start_scan_scheduler()
    yield
    stop_scan_scheduler()
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    license_info={"name": "AGPL-3.0-only", "identifier": "AGPL-3.0-only"},
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.environment != "production" else None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(
    _request: Request, call_next: RequestResponseEndpoint
) -> Response:
    if is_cross_site_api_request(_request):
        response = JSONResponse(
            {"detail": "Cross-site state-changing requests are not allowed"},
            status_code=403,
        )
    else:
        response = await call_next(_request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "script-src 'self'; "
        "style-src 'self'"
    )
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


app.include_router(system_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(catalog_admin_router, prefix="/api")
app.include_router(creator_links_router, prefix="/api")
app.include_router(favorites_router, prefix="/api")
app.include_router(library_sources_router, prefix="/api")
app.include_router(recovery_router, prefix="/api")
app.include_router(setup_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(tags_router, prefix="/api")
app.include_router(tags_admin_router, prefix="/api")
app.include_router(backups_router, prefix="/api")

frontend_dist = settings.frontend_dist.resolve()
frontend_assets = frontend_dist / "assets"

if frontend_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_assets), name="frontend-assets")


@app.get("/meshhive_logo.png", include_in_schema=False)
def brand_logo() -> FileResponse:
    return FileResponse(frontend_dist / "meshhive_logo.png")


@app.get("/meshhive_with_name.png", include_in_schema=False)
def brand_wordmark() -> FileResponse:
    return FileResponse(frontend_dist / "meshhive_with_name.png")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> FileResponse:
    if path == "api" or path.startswith("api/"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API endpoint not found",
        )
    index = Path(frontend_dist, "index.html")
    if not index.is_file():
        return FileResponse(Path(__file__).parent / "static" / "not-built.html", status_code=503)
    return FileResponse(index)
