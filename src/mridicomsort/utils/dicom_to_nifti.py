import click
import pandas as pd
import os
import dicom2nifti
import dicom2nifti.settings as settings

settings.disable_validate_slice_increment()

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
    df = df[df["final_modality"] == final_modality_name]
    for directory_path in df[directory_column]:
        target_path = directory_path.split("/")[-3:]
        target_path = os.path.join(
            output_directory, "_".joint(target_path) + f"{suffix}.nii.gz"
        )
        dicom2nifti.dicom_series_to_nifti(
            directory_path, 
            target_path, 
            reorient_nifti=True
        )


if __name__ == "__main__":
    dicom_to_nifti()