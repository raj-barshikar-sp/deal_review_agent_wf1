"""FastAPI application entry point.

Run with ``python -m app.main`` or ``uvicorn app.main:app``.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, HOST, PORT
from app.routes import router


def create_app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    return application


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
