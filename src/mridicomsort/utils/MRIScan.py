import SimpleITK as sitk
import numpy as np
from pathlib import Path
import json


class MRIScan:
    def __init__(self, file_path: str | Path, meta: dict[str, any] = None):
        self.__meta = {}
        self.__volume = None
        self.__file_path = Path(file_path)
        self.target_orientation = "LPS"

        self.__read_and_standardize()

        if meta is not None:
            self.__meta.update(meta)

    def __read_and_standardize(self):
        """
        Reads the image regardless of format and forces it into
        Axial (LPS) orientation.
        """
        try:
            if self.__file_path.is_dir():
                reader = sitk.ImageSeriesReader()
                dicom_names = reader.GetGDCMSeriesFileNames(str(self.__file_path))
                reader.SetFileNames(dicom_names)
                img = reader.Execute()
            else:
                img = sitk.ReadImage(str(self.__file_path))

            img = sitk.DICOMOrient(img, self.target_orientation)

            if img.GetDirection()[8] < 0:
                img = sitk.Flip(img, [False, False, True])

            self.__volume = sitk.GetArrayFromImage(img)
            self.__meta = {
                "Spacing": img.GetSpacing(),
                "Origin": img.GetOrigin(),
                "Direction": img.GetDirection(),
                "Shape": img.GetSize(),
                "OrientationCode": "LPS (Axial)",
                "FileOrigin": self.__file_path.suffix or "DICOM Folder",
            }

            for key in img.GetMetaDataKeys():
                self.__meta[key] = img.GetMetaData(key)

        except Exception as e:
            raise RuntimeError(f"Failed to process {self.__file_path}: {e}")

    @property
    def volume(self) -> np.ndarray:
        return self.__volume

    @property
    def meta(self) -> dict:
        return self.__meta

    @property
    def num_slices(self) -> int:
        return self.__volume.shape[0] if self.__volume is not None else 0

    def to_nii(self, output_path: str | Path):
        """
        Saves the standardized volume as a .nii.gz file
        and the metadata as a .json file.
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        out_img = sitk.GetImageFromArray(self.__volume)

        out_img.SetSpacing(self.__meta.get("Spacing", (1.0, 1.0, 1.0)))
        out_img.SetOrigin(self.__meta.get("Origin", (0.0, 0.0, 0.0)))
        out_img.SetDirection(self.__meta.get("Direction", (1, 0, 0, 0, 1, 0, 0, 0, 1)))

        nii_path = out_p.with_suffix(".nii.gz")
        sitk.WriteImage(out_img, str(nii_path))
        print(f"Saved NIfTI to: {nii_path}")

        json_path = out_p.with_suffix(".json")

        serializable_meta = {}
        for k, v in self.__meta.items():
            if isinstance(v, (np.ndarray, np.generic)):
                serializable_meta[k] = v.tolist()
            elif isinstance(v, (tuple, list)):
                serializable_meta[k] = list(v)
            elif isinstance(v, (str, int, float, bool)) or v is None:
                serializable_meta[k] = v
        
        with open(json_path, "w") as f:
            json.dump(serializable_meta, f, indent=4)
        print(f"Saved Metadata to: {json_path}")
