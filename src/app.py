"""
Main web application service. Serves the static frontend.
"""
from pathlib import Path
import modal
from .moshi import Moshi  # makes modal deploy also deploy moshi

from .common import app

static_path = Path(__file__).with_name("frontend").resolve()

@app.function(
    mounts=[modal.Mount.from_local_dir(static_path, remote_path="/assets")],
    container_idle_timeout=600,
    timeout=600,
    allow_concurrent_inputs=100,
)
@modal.asgi_app()
def web():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles

    # disable caching on static files
    StaticFiles.is_not_modified = lambda self, *args, **kwargs: False

    web_app = FastAPI()

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve static files, for the frontend
    web_app.mount("/", StaticFiles(directory="/assets", html=True))
    return web_app
