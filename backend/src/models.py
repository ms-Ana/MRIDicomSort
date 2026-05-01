from typing import Any

from pydantic import BaseModel


class ExtractionRequest(BaseModel):
    root_dir: str
    output_file: str
    workers: int = 6

    class Config:
        json_schema_extra = {
            "example": {
                "root_dir": "/path/to/your/directory",
                "output_file": "/path/to/output/file.json",
                "workers": 6,
            }
        }


class FilterRequest(BaseModel):
    config_yaml: str
    data: list[dict[str, Any]]

    class Config:
        json_schema_extra = {
            "example": {
                "config_yaml": "Orientation: sag\nContrast: true",
                "data": [
                    {
                        "DirectoryPath": "/path/to/dir1",
                        "Orientation": "sag",
                        "Contrast": True,
                        # ... other metadata fields ...
                    },
                    {
                        "DirectoryPath": "/path/to/dir2",
                        "Orientation": "cor",
                        "Contrast": False,
                        # ... other metadata fields ...
                    },
                ],
            }
        }
