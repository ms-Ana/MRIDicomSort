from logging.config import dictConfig


def setup_logging():
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(processName)s: %(process)d] [%(levelname)s] %(name)s: %(message)s"
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "uvicorn_access": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "uvicorn_error": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["uvicorn_error"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["uvicorn_access"],
                "level": "INFO",
                "propagate": False,
            },
            "__main__": {
                "handlers": ["default"],
                "level": "DEBUG",
                "propagate": False,
            },
            "": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }
    dictConfig(config)