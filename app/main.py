import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import ENV_EXAMPLE_PATH, ENV_PATH, reload_settings
from app.database import init_db
from app.routes import links, news, settings, status, weather

BASE_DIR = Path(__file__).resolve().parent


async def _watch_env():
    """Poll env file mtimes so changes apply without restarting the server."""
    def latest_mtime():
        mtimes = []
        for path in (ENV_PATH, ENV_EXAMPLE_PATH):
            if path.exists():
                mtimes.append(path.stat().st_mtime)
        return max(mtimes) if mtimes else None

    last_mtime = latest_mtime()
    while True:
        await asyncio.sleep(1.0)
        try:
            current = latest_mtime()
        except OSError:
            continue
        if current != last_mtime:
            reload_settings()
            last_mtime = current


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    reload_settings()
    task = asyncio.create_task(_watch_env())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Personal Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(links.router)
app.include_router(weather.router)
app.include_router(news.router)
app.include_router(settings.router)
app.include_router(status.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )
