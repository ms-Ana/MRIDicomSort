from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.routes import router


async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a json dict that aligns with other API errors."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please try again."},
    )


def build_app():
    app = FastAPI(
        title="MRI Dicom Labeling API", 
        description=(
            "API for labeling MRI dicom images."
        ),
        version="0.1.0",
    )
    app.include_router(router)
    app.add_exception_handler(Exception, handler=global_exception_handler)
    return app