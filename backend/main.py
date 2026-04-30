import os

from fastapi.middleware.cors import CORSMiddleware

from app import build_app
from src.logging_conf import setup_logging

setup_logging()
app = build_app()

# CORS configuration - support both dev and production
cors_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:80,http://localhost"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)