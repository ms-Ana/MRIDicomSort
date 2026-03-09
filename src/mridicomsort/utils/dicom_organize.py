"""Script to reorganize DICOM files into a structured directory based on patient names and study dates."""

import hashlib

import click
import pydicom
import os
import shutil
from pathlib import Path
from tqdm import tqdm


def md5sum(path):
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def validate_copy(original_folder, output_folder, patients_to_year):
    for patient, years in tqdm(
        patients_to_year.items(), desc="Validating copied files per patient"
    ):
        for year, dirs in tqdm(years.items(), desc="Validating copied files per year"):
            for d_path in dirs:
                d, d1, d2 = d_path.split("/")
                orig_dir = os.path.join(original_folder, d, d1, d2)
                new_dir = os.path.join(output_folder, patient, year, d2)

                orig_files = sorted(os.listdir(orig_dir))
                new_files = sorted(os.listdir(new_dir))

                if orig_files != new_files:
                    raise RuntimeError(f"Filename mismatch in {orig_dir} vs {new_dir}")

                for filename in orig_files:
                    orig_path = os.path.join(orig_dir, filename)
                    new_path = os.path.join(new_dir, filename)
                    if md5sum(orig_path) != md5sum(new_path):
                        raise RuntimeError(
                            f"Checksum mismatch for {orig_path} vs {new_path}"
                        )

    print("Validation passed. All files copied correctly.")


def reorganize_dicoms(
    input_folder: str | Path, output_folder: str | Path
) -> dict[str, dict[str, list[str]]]:
    patients_to_year = {}
    failures = 0

    for d in tqdm(os.listdir(input_folder), desc="Processing MRI directories"):
        d_path = os.path.join(input_folder, d)
        if not os.path.isdir(d_path):
            continue

        for d1 in os.listdir(d_path):
            d1_path = os.path.join(d_path, d1)
            if not os.path.isdir(d1_path):
                continue

            for d2 in os.listdir(d1_path):
                d2_path = os.path.join(d1_path, d2)
                if not os.path.isdir(d2_path):
                    continue

                files = os.listdir(d2_path)
                if not files:
                    continue

                try:
                    first_file_path = os.path.join(d2_path, files[0])
                    ds = pydicom.dcmread(first_file_path)
                    patient = str(ds.PatientName)
                    year = ds.StudyDate
                except Exception:
                    failures += 1
                    continue

                patients_to_year.setdefault(patient, {}).setdefault(year, []).append(
                    "/".join([d, d1, d2])
                )
                dest = os.path.join(output_folder, patient, year, d2)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copytree(d2_path, dest)

    print(patients_to_year)
    print(f"Failed to read {failures} files.")
    return patients_to_year


@click.command()
@click.argument("input_folder", type=Path)
@click.argument("output_folder", type=Path)
def main(input_folder: Path, output_folder: Path):
    patients_to_year = reorganize_dicoms(input_folder, output_folder)
    validate_copy(input_folder, output_folder, patients_to_year)


if __name__ == "__main__":
    main()
