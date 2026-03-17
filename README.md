# MRIDicomSort

Sort and curate raw MRI DICOM exports into a reproducible dataset preparation pipeline.

This repository provides:

- DICOM metadata extraction and structural validation
- Rule-based filtering for obvious exclusions
- Heuristic clustering of scan series by metadata
- LLM-based cluster naming into standardized modality labels
- MRI quality scoring and static HTML visual review
- Utility scripts for organizing, comparing, and merging DICOM folders

## Table of Contents

- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [End-to-End Pipeline](#end-to-end-pipeline)
- [Step 1: Preprocessing](#step-1-preprocessing)
- [Step 2: Modality Detection](#step-2-modality-detection)
- [Step 3: Postprocessing](#step-3-postprocessing)
- [Utility Scripts](#utility-scripts)
- [Known Limitations](#known-limitations)

## Overview

The core flow is:

1. Discover all leaf DICOM folders and extract robust metadata.
2. Apply pre-filter rules from YAML.
3. Cluster included scans using metadata-driven heuristics.
4. Name terminal clusters using an LLM into clinical sequence labels.
5. Flatten results into a training-friendly summary table.
6. Optionally score quality and generate an HTML viewer for review.

Main source package: [src/mridicomsort](src/mridicomsort)

## Repository Structure

- [src/mridicomsort/step1_preprocessing](src/mridicomsort/step1_preprocessing): metadata extraction and filtering
- [src/mridicomsort/step2_modality_detection](src/mridicomsort/step2_modality_detection): clustering and LLM naming
- [src/mridicomsort/step3_postprocessing](src/mridicomsort/step3_postprocessing): quality scoring and HTML viewer
- [src/mridicomsort/utils](src/mridicomsort/utils): data organization and integrity helpers
- [src/mridicomsort/config.yaml](src/mridicomsort/config.yaml): filtering rules
- [scripts](scripts): helper scripts for remote vLLM serving

## Requirements

- Python 3.12+
- Linux environment (recommended)
- Optional GPU/cluster access for local vLLM serving

Project dependencies are declared in [pyproject.toml](pyproject.toml).

## Installation

### Option A: pip + virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### Option B: PDM-style workflow

If you use PDM, this project already contains compatible metadata in [pyproject.toml](pyproject.toml).

## Configuration

Runtime settings are loaded in [src/mridicomsort/config.py](src/mridicomsort/config.py) from environment variables.

Create a .env file at repository root:

```dotenv
RESULTS_DIR=/absolute/path/to/results
IMAGE_DIR=/absolute/path/to/images_or_dataset
CONFIG_PATH=/home/your_user/MRIDicomSort/src/mridicomsort/config.yaml

# LLM config
LLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_API_KEY=EMPTY
MODEL_NAME=gpt-4o-mini

# Optional
NUM_WORKERS=8
```

Filtering logic is controlled by [src/mridicomsort/config.yaml](src/mridicomsort/config.yaml), including SOP class, modality, image type, series description, and slice-count constraints.

## End-to-End Pipeline

Below is a typical execution order from raw DICOM folders to final curated CSV.

Assume:

- Raw root folder: /data/UMR_MRI
- Working output folder: /data/outputs

### 1) Metadata extraction

```bash
python -m mridicomsort.step1_preprocessing.run_metadata_extraction \
	/data/UMR_MRI \
	--output /data/outputs/dicom_metadata.csv \
	--workers 8
```

### 2) Apply pre-filters

```bash
python -m mridicomsort.step1_preprocessing.run_filtering \
	/data/outputs/dicom_metadata.csv \
	--output_file /data/outputs/dicom_filtered.csv \
	--config_path src/mridicomsort/config.yaml
```

### 3) Heuristic clustering

```bash
python -m mridicomsort.step2_modality_detection.heuristic_clustering \
	/data/outputs/dicom_filtered.csv \
	--output /data/outputs/dicom_clusters.json
```

### 4) LLM-based modality naming

```bash
python -m mridicomsort.step2_modality_detection.llm_modality_assignment \
	/data/outputs/dicom_filtered.csv \
	/data/outputs/dicom_clusters.json \
	--output /data/outputs/named_dicom_clusters.json
```

### 5) Flatten clusters to tabular dataset

```bash
python -m mridicomsort.step2_modality_detection.convert_clusters2dataset \
	/data/outputs/named_dicom_clusters.json \
	/data/outputs/dicom_filtered.csv \
	--output /data/outputs/dicom_clusters_summary.csv
```

### 6) Optional quality scoring

```bash
python -m mridicomsort.step3_postprocessing.quality_scoring \
	/abs/path/to/series_dir_1 \
	/abs/path/to/series_dir_2 \
	--output /data/outputs/mri_quality_scores.csv \
	--use_pixel_data \
	--find_histogram_outliers
```

### 7) Optional HTML review viewer

Use a CSV containing a path column and metadata columns.

```bash
python -m mridicomsort.step3_postprocessing.build_mri_html_viewer \
	/data/outputs/mri_quality_scores.csv \
	--path-column path \
	--action-column suggested_action \
	--output-dir /data/outputs/mri_html_viewer_output \
	--serve --port 8000
```

## Step 1: Preprocessing

Folder: [src/mridicomsort/step1_preprocessing](src/mridicomsort/step1_preprocessing)

### Metadata extraction

Script: [run_metadata_extraction.py](src/mridicomsort/step1_preprocessing/run_metadata_extraction.py)

- Recursively finds leaf folders.
- Attempts to read each DICOM file.
- Flags geometry issues, potential 4D stacks, and NIfTI safety.
- Extracts curated metadata fields from [dicom_metadata.py](src/mridicomsort/step1_preprocessing/dicom_metadata.py).

Primary output columns include:

- DirectoryPath
- Status
- NumberOfSlices
- NiftiSafe
- Is4D
- Orientation
- Contrast
- Acquisition and sequence metadata fields

### Filtering

Scripts:

- [run_filtering.py](src/mridicomsort/step1_preprocessing/run_filtering.py)
- [filtering.py](src/mridicomsort/step1_preprocessing/filtering.py)

Actions assigned per scan:

- include
- check
- exclude

Reasons are recorded in pre-filters-reason.

## Step 2: Modality Detection

Folder: [src/mridicomsort/step2_modality_detection](src/mridicomsort/step2_modality_detection)

### Heuristic clustering

Script: [heuristic_clustering.py](src/mridicomsort/step2_modality_detection/heuristic_clustering.py)

- Uses filled metadata fields from included scans.
- Applies categorical split for low-cardinality values.
- Applies numeric binning for numeric high-cardinality fields.
- Produces a hierarchical cluster tree JSON.

### LLM-based cluster naming

Script: [llm_modality_assignment.py](src/mridicomsort/step2_modality_detection/llm_modality_assignment.py)

- Traverses terminal clusters.
- Sends split criteria + selected context to OpenAI-compatible endpoint.
- Returns concise labels such as T1_GRE, T2_SE, DWI.

This script depends on:

- LLM_BASE_URL
- LLM_API_KEY
- MODEL_NAME

### Dataset conversion

Script: [convert_clusters2dataset.py](src/mridicomsort/step2_modality_detection/convert_clusters2dataset.py)

- Flattens named cluster tree.
- Merges labels and split criteria back to metadata rows.
- Exports summary CSV for downstream curation/training.

## Step 3: Postprocessing

Folder: [src/mridicomsort/step3_postprocessing](src/mridicomsort/step3_postprocessing)

### Quality scoring

Script: [quality_scoring.py](src/mridicomsort/step3_postprocessing/quality_scoring.py)

Computes:

- slice-count and dynamic-range checks
- inter-slice stability checks
- optional voxel-level proxies (SNR/CNR/clipping)
- optional histogram outlier detection
- final quality_score, quality_grade, suggested_action

### HTML viewer

Script: [build_mri_html_viewer.py](src/mridicomsort/step3_postprocessing/build_mri_html_viewer.py)

- Builds static HTML + PNG thumbnails for first/middle/last slices.
- Groups series by patient/date.
- Displays rich hover metadata.
- Optional local serving mode.

Generated example outputs are present under:

- [src/mridicomsort/step3_postprocessing/mri_html_viewer_output](src/mridicomsort/step3_postprocessing/mri_html_viewer_output)
- [src/mridicomsort/step3_postprocessing/mri_pre-contrast](src/mridicomsort/step3_postprocessing/mri_pre-contrast)

## Utility Scripts

Folder: [src/mridicomsort/utils](src/mridicomsort/utils)

Related note: [src/mridicomsort/utils/README.md](src/mridicomsort/utils/README.md)

### Reorganize raw DICOM exports

Script: [dicom_organize.py](src/mridicomsort/utils/dicom_organize.py)

```bash
python -m mridicomsort.utils.dicom_organize /path/input /path/output
```

### Compare two folders by checksum

Script: [compare_folders.py](src/mridicomsort/utils/compare_folders.py)

```bash
python -m mridicomsort.utils.compare_folders /path/dirA /path/dirB --output comparison_result.json
```

### Merge folder trees

Script: [merge_folders.py](src/mridicomsort/utils/merge_folders.py)

```bash
python -m mridicomsort.utils.merge_folders /path/src /path/dst
```

### Convert DICOM to NIfTI (standalone helper)

Script: [dicom2niiti.py](src/mridicomsort/utils/dicom2niiti.py)

This helper supports recursive DICOM-to-NIfTI conversion with include/exclude rules and metadata sidecar JSON.


## Known Limitations

- The pipeline assumes leaf-folder series organization; mixed directory conventions may require adaptation.

## License

MIT (see [pyproject.toml](pyproject.toml)).
