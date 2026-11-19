"""FastAPI application entry point.

Run with ``python -m app.main`` or ``uvicorn app.main:app``.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import HOST, PORT
from app.core.log import configure
from app.core.origin import TRUSTED_ORIGINS, same_origin_only
from app.routes import router


def create_app() -> FastAPI:
    configure()
    # CORS only for FRONTEND_ORIGIN (separate front-end service); all others are refused.
    application = FastAPI()
    application.middleware("http")(same_origin_only)
    application.include_router(router)
    if TRUSTED_ORIGINS:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=TRUSTED_ORIGINS,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
    return application


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
