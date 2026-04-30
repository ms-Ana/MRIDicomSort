
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
                "workers": 6
            }
        }