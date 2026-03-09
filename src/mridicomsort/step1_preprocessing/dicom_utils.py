import pydicom
from pathlib import Path
from mridicomsort.step1_preprocessing.dicom_metadata import CONTRAST_METADATA
import numpy as np
from typing import Any


def determine_orientation(iop) -> str:
    """Determines image orientation via the cross product of the direction cosines."""
    if not iop or len(iop) != 6:
        return "NaN"
    try:
        iop = [float(x) for x in iop]
        n_x = (iop[1] * iop[5]) - (iop[2] * iop[4])
        n_y = (iop[2] * iop[3]) - (iop[0] * iop[5])
        n_z = (iop[0] * iop[4]) - (iop[1] * iop[3])
        abs_n = [abs(n_x), abs(n_y), abs(n_z)]
        dominant_axis = abs_n.index(max(abs_n))

        return "sag" if dominant_axis == 0 else "cor" if dominant_axis == 1 else "tra"

    except (ValueError, TypeError):
        return "NaN"


def format_image_type(image_type_val) -> str:
    if not image_type_val:
        return ""
    if isinstance(image_type_val, (list, tuple, pydicom.multival.MultiValue)):
        return "_".join(str(x) for x in image_type_val).upper().strip()
    return str(image_type_val).upper().strip()


def normalize_value(val) -> str:
    """Normalize DICOM values for CSV output."""
    if val is None:
        return "NaN"
    if isinstance(val, (pydicom.multival.MultiValue, list, tuple)):
        return "\\".join(normalize_value(x) for x in val)
    if isinstance(val, str):
        val = val.strip().strip("\x00")
        if not val:
            return "NaN"
    return str(val)


def is_leaf_dir(p: Path) -> bool:
    return p.is_dir() and not any(c.is_dir() for c in p.iterdir())


def check_contrast(ds) -> bool:
    for key in CONTRAST_METADATA:
        val = ds.get(key, None)
        if val is not None:
            try:
                val = float(val)
                if val > 0:
                    return True
            except (ValueError, TypeError):
                val_str = str(val).strip().lower()
                if val_str and val_str != "none":
                    return True
    return False


def get_nifti_validity(datasets: list[pydicom.Dataset]) -> tuple[bool, str, float]:
    """Validates 3D grid integrity (checks for gaps or mixed orientations)."""
    if len(datasets) < 2:
        return False, "Single Slice", 0.0

    orientations = set(
        tuple(round(float(x), 4) for x in ds.ImageOrientationPatient) for ds in datasets
    )
    if len(orientations) > 1:
        return False, f"Mixed Orientations ({len(orientations)})", 0.0

    iop = datasets[0].ImageOrientationPatient
    normal = np.cross(iop[:3], iop[3:])

    def get_projection(ds):
        return np.dot(ds.ImagePositionPatient, normal)

    datasets.sort(key=get_projection)

    projections = np.array([get_projection(ds) for ds in datasets])
    distances = np.diff(projections)

    if np.any(np.isclose(distances, 0, atol=1e-3)):
        return True, "Overlapping Slices (Potential 4D)", np.mean(np.abs(distances))

    unique_steps = np.unique(np.round(np.abs(distances), 3))
    avg_spacing = np.mean(unique_steps)

    if len(unique_steps) > 1:
        if (np.max(unique_steps) - np.min(unique_steps)) > 0.05:
            return False, f"Non-uniform Z-spacing: {unique_steps}", avg_spacing

    return True, "Valid 3D Grid", avg_spacing


def detect_4d_analysis(datasets: list[pydicom.Dataset]) -> dict[str, Any]:
    """Detects if series is 4D and extracts the specific varying parameters."""
    pos_map = {}
    for ds in datasets:
        pos = tuple(round(float(x), 3) for x in ds.ImagePositionPatient)
        pos_map.setdefault(pos, []).append(ds)

    sample_pos = next(iter(pos_map))
    overlaps = pos_map[sample_pos]
    stack_count = len(overlaps)

    if stack_count <= 1:
        return {
            "Is4D": False,
            "StackCount": 1,
            "Trigger": "None",
            "DetailedParams": "3D",
        }

    trigger_tags = [
        "EchoTime",
        "AcquisitionNumber",
        "ContentTime",
        "TriggerTime",
        "DiffusionBValue",
        "TemporalPositionIdentifier",
    ]

    found_triggers = []
    details = []
    for name in trigger_tags:
        vals = sorted(list(set(normalize_value(ds.get(name)) for ds in overlaps)))
        if len(vals) > 1:
            found_triggers.append(name)
            details.append(f"{name}:[{', '.join(vals)}]")

    return {
        "Is4D": True,
        "StackCount": stack_count,
        "Trigger": "|".join(found_triggers) if found_triggers else "Unknown",
        "DetailedParams": "; ".join(details) if details else "Unknown Sequence",
    }
