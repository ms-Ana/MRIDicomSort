import os
import sys
from pathlib import Path
from typing import List
import pydicom
import click
from tqdm import tqdm
import concurrent.futures
import pandas as pd
from mridicomsort.step1_preprocessing.dicom_metadata import METADATA
from mridicomsort.step1_preprocessing.dicom_utils import (
    detect_4d_analysis,
    get_nifti_validity,
    determine_orientation,
    normalize_value,
    format_image_type,
    check_contrast,
)


def process_leaf_dir(leaf_path: Path) -> dict[str, str]:
    """Processes a single leaf directory containing DICOM files."""
    files = [
        f for f in leaf_path.iterdir() if f.is_file() and not f.name.startswith(".")
    ]
    num_files = len(files)

    row = {
        "DirectoryPath": str(leaf_path.absolute()),
        "Status": "error",
        "NumberOfSlices": str(num_files),
        "MultipleStacks": "NaN",
        "Contrast": "NaN",
        "Orientation": "NaN",
        "NiftiSafe": "False",
        "Is4D": "NaN",
        "StackCount": "NaN",
        "TriggerType": "NaN",
        "DetailedParams": "NaN",
        "ValidationNote": "No valid DICOMs",
    }

    for key in METADATA:
        row[key] = "NaN"

    if num_files == 0:
        return row

    spatial_datasets = []
    stack_ids = set()

    # Read files to check validity and find multiple stacks
    for f in files:
        try:
            ds = pydicom.dcmread(str(f), stop_before_pixels=True, force=False)
            if "ImagePositionPatient" not in ds or "ImageOrientationPatient" not in ds:
                continue

            spatial_datasets.append(ds)

            if "StackID" in ds and ds.StackID:
                stack_ids.add(str(ds.StackID))
                
        except Exception:
            pass  # File is corrupted or not DICOM

    if not spatial_datasets:
        row["ValidationNote"] = "No datasets with spatial metadata found (Cannot convert to 3D)"
        return row
    
    analysis4d = detect_4d_analysis(spatial_datasets)
    is_valid_grid, grid_reason = get_nifti_validity(spatial_datasets)

    row["NiftiSafe"] = str(is_valid_grid and not analysis4d["Is4D"])
    row["Is4D"] = str(analysis4d["Is4D"])
    row["StackCount"] = str(analysis4d["StackCount"])
    row["TriggerType"] = str(analysis4d.get("Trigger", "None"))
    row["DetailedParams"] = str(analysis4d.get("Parameters", "NaN"))
    row["ValidationNote"] = str(grid_reason)
  
    ds_rep = spatial_datasets[0]

    row["MultipleStacks"] = len(stack_ids) > 1
    
    if len(stack_ids) > 1:
        row["Status"] = "check_multiple_stacks"
    elif row["NiftiSafe"] == "False":
        row["Status"] = "check_geometry"
    else:
        row["Status"] = "ok"

    for key in METADATA:
        if key == "ImageType":
            val = ds_rep.get(key)
            row[key] = format_image_type(val)
        else:
            row[key] = normalize_value(ds_rep.get(key))

    row["Contrast"] = str(check_contrast(ds_rep))
    row["Orientation"] = determine_orientation(ds_rep.get("ImageOrientationPatient"))

    return row


def walk_leaves(root: Path) -> List[Path]:
    """Finds all lowest-level directories."""
    leaves = []
    for dirpath, dirnames, _ in os.walk(root):
        if not dirnames:
            leaves.append(Path(dirpath))
    return sorted(set(leaves))


@click.command()
@click.argument("root", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--output",
    type=click.Path(file_okay=True),
    default="dicom_metadata.csv",
    help="Output CSV path",
)
@click.option("--workers", type=int, default=8, help="Number of CPU cores to use")
def main(root: str, output: str, workers: int):
    root_path = Path(root)
    leaves = walk_leaves(root_path)

    if not leaves:
        print(f"ERROR: No leaf directories found under {root_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(leaves)} leaf directories. Extracting metadata...")

    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_leaf_dir, leaf): leaf for leaf in leaves}

        for future in tqdm(concurrent.futures.as_completed(futures), total=len(leaves)):
            results.append(future.result())

    df = pd.DataFrame(results)
    df.to_csv(output, index=False)

    print(f"Done! Report saved to {output}")


if __name__ == "__main__":
    main()
