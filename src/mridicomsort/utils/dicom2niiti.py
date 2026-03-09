#!/usr/bin/env python3
# dicom2nifti.py
import argparse
import json
import re
import sys
from pathlib import Path
import SimpleITK as sitk
import os

EXCLUDE_TOKENS = {
    "DERIVED",
    "SECONDARY",
    "CSA REPORT",
    "MPR",
    "MIP",
    "PROJECTION IMAGE",
    "LOCALIZER",
    "ADC",
    "TRACE",
    "COMPOSITE",
}

TAG_MAP = {
    "0008|0060": "Modality",
    "0008|0070": "Manufacturer",
    "0008|1090": "ModelName",
    "0018|0081": "EchoTime",
    "0018|0080": "RepetitionTime",
    "0018|0091": "EchoTrainLength",
    "0018|0087": "MagneticFieldStrength",
    "0018|1314": "FlipAngle",
    "0018|0088": "SpacingBetweenSlices",
    "0018|0026": "SequenceVariant",
    "0018|0022": "ScanOptions",
    "0018|0050": "SliceThickness",
    "0020|0011": "SeriesNumber",
    "0020|000e": "SeriesInstanceUID",
    "0018|0023": "MRAcquisitionType",
    "0008|103e": "SeriesDescription",
    "0008|0021": "SeriesDate",
    "0008|0031": "SeriesTime",
    "0028|0030": "PixelSpacing",
    "0020|0037": "ImageOrientationPatient",
    "0020|0032": "ImagePositionPatient",
    "0018|0020": "ScanningSequence",
    "0008|0008": "ImageType",
}


def read_first_tags(dcm_path: str) -> dict:
    r = sitk.ImageFileReader()
    r.SetFileName(dcm_path)
    r.ReadImageInformation()
    meta = {}
    for tag, name in TAG_MAP.items():
        if r.HasMetaDataKey(tag):
            meta[name] = r.GetMetaData(tag)
    # ImageType is multi-valued
    if r.HasMetaDataKey("0008|0008"):
        meta["ImageType"] = r.GetMetaData("0008|0008")
    return meta


def sanitize(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:80] or "series"


def should_exclude(
    meta: dict, exclude_regex: re.Pattern | None, skip_derived: bool
) -> bool:
    sd = (meta.get("SeriesDescription") or "").upper()
    it = (meta.get("ImageType") or "").upper()
    if exclude_regex and exclude_regex.search(sd):
        return True
    if skip_derived:
        toks = set([t.strip() for t in it.replace("\\", "^").split("^") if t.strip()])
        if toks & EXCLUDE_TOKENS:
            return True
    if "LOCALIZER" in sd:
        return True
    return False


def series_iter(dicom_root: Path):
    """Yield (series_uid, file_list) grouped by SeriesInstanceUID recursively."""
    series_ids = []
    # use GDCM to find series IDs across subdirs
    for sub in [str(dicom_root)] + [
        str(p) for p in dicom_root.rglob("*") if p.is_dir()
    ]:
        ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(sub) or []
        for sid in ids:
            files = sitk.ImageSeriesReader.GetGDCMSeriesFileNames(sub, sid)
            if files:
                series_ids.append((sid, files))
    # de-dup by UID (keep longest file list)
    best = {}
    for sid, files in series_ids:
        if sid not in best or len(files) > len(best[sid]):
            best[sid] = files
    for sid, files in best.items():
        yield sid, files


def load_series(files: list[str]) -> sitk.Image:
    rdr = sitk.ImageSeriesReader()
    rdr.SetFileNames(files)
    rdr.MetaDataDictionaryArrayUpdateOn()
    rdr.LoadPrivateTagsOn()
    return rdr.Execute()


def write_nifti(img: sitk.Image, out_nii: Path):
    out_nii.parent.mkdir(parents=True, exist_ok=True)
    sitk.WriteImage(img, str(out_nii), useCompression=True)


def main():
    ap = argparse.ArgumentParser(
        description="Convert a DICOM folder (recursively) to NIfTI per SeriesInstanceUID."
    )
    ap.add_argument("dicom_root", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument(
        "--only_mod",
        default="",
        help="Keep only this Modality (e.g., MR, CT). Empty=any.",
    )
    ap.add_argument(
        "--include",
        default="",
        help="Regex to include SeriesDescription (applied before exclude).",
    )
    ap.add_argument("--exclude", default="", help="Regex to exclude SeriesDescription.")
    ap.add_argument(
        "--keep_derived",
        action="store_true",
        help="Do not auto-skip DERIVED/SECONDARY etc.",
    )
    ap.add_argument("--prefix", default="{Patient}_{SeriesNumber}_{SeriesDescription}")
    args = ap.parse_args()

    inc_re = re.compile(args.include, re.I) if args.include else None
    exc_re = re.compile(args.exclude, re.I) if args.exclude else None

    converted = 0
    for sid, files in series_iter(args.dicom_root):
        first_meta = read_first_tags(files[0])

        if (
            args.only_mod
            and first_meta.get("Modality", "").upper() != args.only_mod.upper()
        ):
            continue
        sd = first_meta.get("SeriesDescription", "")
        if inc_re and not inc_re.search(sd):
            continue
        if should_exclude(first_meta, exc_re, skip_derived=(not args.keep_derived)):
            continue

        # load volume
        try:
            img = load_series(files)
        except Exception as e:
            print(f"[SKIP] {sid}: load failed: {e}", file=sys.stderr)
            continue

        # filename
        patient = sanitize(Path(args.dicom_root).name)
        serno = sanitize(first_meta.get("SeriesNumber", ""))
        sdesc = sanitize(sd)
        fname = args.prefix.format(
            Patient=patient, SeriesNumber=serno, SeriesDescription=sdesc
        )
        out_nii = args.out_dir / f"{fname or 'series'}__{sid[-6:]}.nii.gz"
        write_nifti(img, out_nii)

        meta_out = {
            k: v
            for k, v in first_meta.items()
            if k
            in {
                "Modality",
                "Manufacturer",
                "ModelName",
                "EchoTime",
                "RepetitionTime",
                "EchoTrainLength",
                "MagneticFieldStrength",
                "SpacingBetweenSlices",
                "SequenceVariant",
                "ScanOptions",
                "SliceThickness",
                "SeriesNumber",
                "SeriesInstanceUID",
                "MRAcquisitionType",
                "SeriesDescription",
                "SeriesDate",
                "SeriesTime",
                "PixelSpacing",
                "ImageOrientationPatient",
                "ImagePositionPatient",
                "ScanningSequence",
                "ImageType",
            }
        }
        with open(out_nii.with_suffix(".json"), "w") as f:
            json.dump(meta_out, f, indent=2)

        sz = img.GetSize()
        sp = img.GetSpacing()
        print(
            f"[OK] {out_nii.name}  size={sz}  spacing={tuple(round(s, 6) for s in sp)}"
        )
        converted += 1

    if converted == 0:
        print("No series converted.", file=sys.stderr)


if __name__ == "__main__":
    root_dir = "/home/anastasiia/MasterThesis/UMR_MRI"
    out_root_dir = "/home/anastasiia/MasterThesis/UMR_nifti"
    os.makedirs(out_root_dir, exist_ok=True)
    for patient_dir in Path(root_dir).iterdir():
        for date_dir in patient_dir.iterdir():
            for series_dir in date_dir.iterdir():
                if "T1_post-contrast" in series_dir.name:
                    dicom_root = series_dir
                    out_dir = (
                        Path(out_root_dir)
                        / patient_dir.name
                        / date_dir.name
                        / series_dir.name
                    )
                    sys.argv = [
                        "dicom2nifti.py",
                        str(dicom_root),
                        str(out_dir),
                        "--only_mod",
                        "MR",
                    ]
                    main()
