import os

import click
import dicom2nifti
import pandas as pd
from tqdm import tqdm


@click.command()
@click.argument("dicom_summary", type=str)
@click.option("--directory_column", type=str, default="DirectoryPath")
@click.option("--final_modality_name", type=str)
@click.option("--output_directory", type=str)
@click.option("--suffix", type=str)
def dicom_to_nifti(
    dicom_summary: str,
    directory_column: str,
    final_modality_name: str,
    output_directory: str,
    suffix: str,
):
    df = pd.read_csv(dicom_summary)
    # df = df[df["final_modality"] == final_modality_name]
    suffix = f"_{suffix}" if suffix else ""
    for directory_path in tqdm(df[directory_column]):
        target_path = directory_path.split("/")[-3:]
        target_path = os.path.join(
            output_directory, "_".join(target_path) + f"{suffix}.nii.gz"
        )
        try:
            dicom2nifti.dicom_series_to_nifti(
                directory_path, target_path, reorient_nifti=True
            )
        except Exception as e:
            print(f"Error converting {directory_path}: {e}")


if __name__ == "__main__":
    dicom_to_nifti()
