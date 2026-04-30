import os
import sys
import json
import asyncio
import pandas as pd
import concurrent.futures
from pathlib import Path

import logging
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import StreamingResponse
from src.models import FilterRequest
from mridicomsort.step1_preprocessing.filtering import process_single_row
from mridicomsort.step1_preprocessing.run_metadata_extraction import process_leaf_dir, walk_leaves
import yaml

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get(
    "/health",
    tags=["Health"],
    summary="Service health probe",
    description="Simple liveness endpoint to verify the API is running.",
)
def health_check():
    return {"status": "ok"}


def stream_extraction(root_dir: str,
                      output_file: str, 
                      workers: int = 6): 
    
    leaves = walk_leaves(Path(root_dir))

    if not leaves:
        yield f"data: {json.dumps({'status': 'error', 'message': f'No directories found in {root_dir}'})}\n\n"
        return
    
    yield f"data: {json.dumps({'status': 'start', 'total': len(leaves)})}\n\n"

    results = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_leaf_dir, leaf): leaf for leaf in leaves}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            try:
                row_data = future.result()
                results.append(row_data)
                completed += 1
                
                # Stream the newly extracted row to the frontend
                yield f"data: {json.dumps({'status': 'progress', 'completed': completed, 'row': row_data})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    # Save to CSV at the end
    try:
        df = pd.DataFrame(results)
        df.to_csv(output_file, index=False)
        yield f"data: {json.dumps({'status': 'done', 'message': f'Saved to {output_file}'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'status': 'error', 'message': f'Failed to save CSV: {str(e)}'})}\n\n"


@router.get("/api/extract")
async def extract_metadata(root: str, output: str, workers: int = 6):
    """Endpoint that returns a stream of Server-Sent Events"""
    return StreamingResponse(
        stream_extraction(root, output, workers), 
        media_type="text/event-stream"
    )

@router.post("/api/filter")
async def apply_filter(request: FilterRequest):
    try:
        # Parse the YAML string sent from the frontend
        config = yaml.safe_load(request.config_yaml)
        if config is None:
            config = {}
    except yaml.YAMLError as e:
        return {"error": f"Invalid YAML format: {str(e)}"}

    updated_data = []
    for row in request.data:
        # Run your existing filtering logic
        path, action, reason = process_single_row(row, config)
        
        # Append the new filter results to the row
        row["action"] = action
        row["pre_filters_reason"] = reason
        updated_data.append(row)

    return {"status": "success", "data": updated_data}