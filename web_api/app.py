from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.db_management import create_db_and_tables
from modules.client_store import bootstrap_clients_from_json
from web_api.routes import build_router

LOGGER = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception as exc:
    LOGGER.warning(
        "Unable to load .env via python-dotenv; continuing with current environment: %s",
        exc,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    bootstrap_clients_from_json()
    yield


app = FastAPI(title="Lotbook Web API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(build_router())
