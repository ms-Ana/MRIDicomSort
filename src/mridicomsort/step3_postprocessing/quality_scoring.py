from pathlib import Path
from typing import Any

import click
import numpy as np
import pandas as pd
import pydicom
from tqdm import tqdm

from mridicomsort.utils.MRIScan import MRIScan


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float_array(value: Any) -> np.ndarray:
    if not isinstance(value, list):
        return np.array([], dtype=float)
    numeric = [_safe_float(v) for v in value]
    numeric = [v for v in numeric if v is not None]
    return np.array(numeric, dtype=float)


class MRIQualityChecker:
    def __init__(
        self,
        low_slice_threshold: int = 10,
        use_pixel_data: bool = False,
        find_histogram_outliers: bool = False,
    ):
        self.low_slice_threshold = low_slice_threshold
        self.find_histogram_outliers = find_histogram_outliers
        self.use_pixel_data = use_pixel_data or find_histogram_outliers

    def _extract_metadata(self, dicom_dir: Path) -> dict[str, Any]:
        """Dynamically extract necessary metadata from a DICOM directory."""
        files = [f for f in dicom_dir.iterdir() if f.is_file()]

        largest_pixels = []
        window_widths = []
        valid_slices = 0

        for file_path in files:
            try:
                ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                valid_slices += 1

                if "LargestImagePixelValue" in ds:
                    largest_pixels.append(ds.LargestImagePixelValue)

                if "WindowWidth" in ds:
                    ww = ds.WindowWidth
                    if isinstance(ww, pydicom.multival.MultiValue):
                        window_widths.append(ww[0])
                    else:
                        window_widths.append(ww)
            except pydicom.errors.InvalidDicomError:
                continue
            except Exception:
                continue

        return {
            "SliceCount": valid_slices,
            "LargestImagePixelValue (0028,0107)": largest_pixels,
            "WindowWidth (0028,1051)": window_widths,
            "DifferingFiles": {},
            "DeterminedOrientationMatches": True,
        }

    def _compute_voxel_quality(self, volume: np.ndarray) -> dict[str, float]:
        vol = volume.astype(np.float32)
        finite_mask = np.isfinite(vol)
        if not np.any(finite_mask):
            return {
                "snr_proxy": 0.0,
                "cnr_proxy": 0.0,
                "clipping_fraction": 1.0,
                "signal_score": 0.0,
                "cnr_score": 0.0,
                "clipping_score": 0.0,
            }

        vox = vol[finite_mask]
        p20 = float(np.percentile(vox, 20))
        p70 = float(np.percentile(vox, 70))

        background = vox[vox <= p20]
        foreground = vox[vox >= p70]

        noise_std = float(np.std(background)) if background.size else 0.0
        signal_mean = float(np.mean(foreground)) if foreground.size else 0.0

        # SNR Proxy calculation
        snr_proxy = signal_mean / (noise_std + 1e-6)

        # CNR Proxy calculation
        # We proxy two distinct tissue intensities (e.g., Gray/White matter)
        # by taking the 20th and 80th percentile of the meaningful tissue/foreground.
        tissue_vox = vox[vox > p20]
        if tissue_vox.size > 0:
            tissue_high = float(np.percentile(tissue_vox, 80))
            tissue_low = float(np.percentile(tissue_vox, 20))
            cnr_proxy = (tissue_high - tissue_low) / (noise_std + 1e-6)
        else:
            cnr_proxy = 0.0

        clipping_fraction = float(np.mean((vox == np.min(vox)) | (vox == np.max(vox))))

        signal_score = min(1.0, snr_proxy / 20.0)
        cnr_score = min(1.0, cnr_proxy / 10.0)
        clipping_score = max(0.0, 1.0 - min(clipping_fraction / 0.02, 1.0))

        return {
            "snr_proxy": snr_proxy,
            "cnr_proxy": cnr_proxy,
            "clipping_fraction": clipping_fraction,
            "signal_score": signal_score,
            "cnr_score": cnr_score,
            "clipping_score": clipping_score,
        }

    def _compute_quality(self, dicom_dir: Path) -> dict[str, Any]:
        reasons: list[str] = []
        metadata = self._extract_metadata(dicom_dir)

        slice_count = metadata.get("SliceCount", 0)
        largest_pixels = _as_float_array(
            metadata.get("LargestImagePixelValue (0028,0107)")
        )
        window_width = _as_float_array(metadata.get("WindowWidth (0028,1051)"))

        if slice_count < self.low_slice_threshold:
            reasons.append(
                f"Low slice count ({slice_count} < {self.low_slice_threshold})."
            )

        if largest_pixels.size:
            p05 = float(np.percentile(largest_pixels, 5))
            p95 = float(np.percentile(largest_pixels, 95))
            dynamic_range = p95 - p05
            if dynamic_range < 100:
                reasons.append(
                    f"Low signal dynamic range (p95-p05={dynamic_range:.1f})."
                )

            diffs = np.diff(largest_pixels)
            instability = (
                float(np.mean(np.abs(diffs)) / (dynamic_range + 1.0))
                if diffs.size
                else 0.0
            )
            if instability > 0.45:
                reasons.append(f"High inter-slice instability ({instability:.2f}).")
        else:
            dynamic_range = 0.0
            instability = 1.0
            reasons.append("Missing per-slice pixel statistics.")

        if window_width.size:
            median_window_width = float(np.median(window_width))
            if median_window_width <= 0:
                reasons.append("Non-positive window width values.")
        else:
            median_window_width = 0.0
            reasons.append("Missing WindowWidth metadata.")

        differing_files = metadata.get("DifferingFiles", {})
        differing_count = len(differing_files)
        if differing_count > 0:
            reasons.append(
                f"Found differing DICOM tags across files ({differing_count} files)."
            )

        orientation_matches = metadata.get("DeterminedOrientationMatches")
        if orientation_matches is False:
            reasons.append(
                "Orientation does not match orientation token in SeriesDescription."
            )

        voxel_metrics: dict[str, float] = {
            "snr_proxy": np.nan,
            "cnr_proxy": np.nan,
            "clipping_fraction": np.nan,
            "signal_score": np.nan,
            "cnr_score": np.nan,
            "clipping_score": np.nan,
        }

        voxel_enabled = False
        histogram = None

        if self.use_pixel_data:
            if not dicom_dir.exists():
                reasons.append(f"Pixel QC missing source directory: {dicom_dir}")
            else:
                try:
                    volume = MRIScan(str(dicom_dir)).volume
                    if volume is None or getattr(volume, "ndim", 0) < 3:
                        reasons.append("Pixel QC unavailable: invalid or empty volume.")
                    else:
                        voxel_metrics = self._compute_voxel_quality(volume)
                        voxel_enabled = True

                        # Compute normalized histogram for outlier detection
                        if self.find_histogram_outliers:
                            finite_vol = volume[np.isfinite(volume)]
                            if finite_vol.size > 0:
                                p01 = float(np.percentile(finite_vol, 1))
                                p99 = float(np.percentile(finite_vol, 99))
                                if p99 > p01:
                                    vol_clipped = np.clip(finite_vol, p01, p99)
                                    vol_norm = (vol_clipped - p01) / (p99 - p01)
                                    hist, _ = np.histogram(
                                        vol_norm, bins=100, range=(0, 1), density=True
                                    )
                                    histogram = hist

                except Exception as exc:
                    reasons.append(f"Pixel QC failed: {exc}")

        range_score = min(1.0, dynamic_range / 500.0)
        stability_score = max(0.0, 1.0 - min(instability / 0.7, 1.0))
        window_score = 1.0 if median_window_width > 0 else 0.2

        if voxel_enabled:
            quality_score = 100.0 * (
                0.15 * range_score
                + 0.15 * window_score
                + 0.3 * voxel_metrics["signal_score"]
                + 0.20 * voxel_metrics["cnr_score"]
                + 0.20 * voxel_metrics["clipping_score"]
            )
            if voxel_metrics["snr_proxy"] < 5.0:
                reasons.append(
                    f"Low voxel SNR proxy ({voxel_metrics['snr_proxy']:.2f})."
                )
            if voxel_metrics["cnr_proxy"] < 2.0:
                reasons.append(
                    f"Low voxel CNR proxy ({voxel_metrics['cnr_proxy']:.2f})."
                )
            if voxel_metrics["clipping_fraction"] > 0.01:
                reasons.append(
                    f"High clipping fraction ({100.0 * voxel_metrics['clipping_fraction']:.2f}%)."
                )
        else:
            quality_score = 100.0 * (
                0.40 * range_score + 0.40 * stability_score + 0.20 * window_score
            )

        if quality_score >= 80:
            quality_grade = "good"
            suggested_action = "include"
        elif quality_score >= 60:
            quality_grade = "usable"
            suggested_action = "include"
        elif quality_score >= 40:
            quality_grade = "poor"
            suggested_action = "check"
        else:
            quality_grade = "exclude"
            suggested_action = "exclude"

        return {
            "path": str(dicom_dir),
            "slice_count": slice_count,
            "dynamic_range": round(dynamic_range, 3),
            "slice_instability": round(instability, 4),
            "median_window_width": round(median_window_width, 3),
            "differing_files_count": differing_count,
            "orientation_matches": orientation_matches,
            "snr_proxy": round(float(voxel_metrics["snr_proxy"]), 4)
            if np.isfinite(voxel_metrics["snr_proxy"])
            else np.nan,
            "cnr_proxy": round(float(voxel_metrics["cnr_proxy"]), 4)
            if np.isfinite(voxel_metrics["cnr_proxy"])
            else np.nan,
            "clipping_fraction": round(float(voxel_metrics["clipping_fraction"]), 6)
            if np.isfinite(voxel_metrics["clipping_fraction"])
            else np.nan,
            "pixel_qc_enabled": voxel_enabled,
            "quality_score": round(quality_score, 3),
            "quality_grade": quality_grade,
            "suggested_action": suggested_action,
            "quality_flags": " | ".join(reasons) if reasons else "",
            "histogram": histogram,  
        }

    def process_directories(
        self,
        dicom_dirs: list[str] | list[Path],
        output_file: str | None = None,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []

        for dicom_path in tqdm(dicom_dirs, desc="Scoring MRI quality"):
            dicom_dir_path = Path(dicom_path).resolve()
            if not dicom_dir_path.exists() or not dicom_dir_path.is_dir():
                print(f"Skipping invalid directory: {dicom_dir_path}")
                continue

            result = self._compute_quality(dicom_dir_path)
            rows.append(result)

        # ---------------------------------------------------------
        # Histogram Outlier Detection
        # ---------------------------------------------------------
        if self.find_histogram_outliers:
            valid_idx = []
            hists = []

            for i, row in enumerate(rows):
                hist = row.pop("histogram", None)
                if hist is not None:
                    valid_idx.append(i)
                    hists.append(hist)

            if len(hists) > 2:
                hist_array = np.array(hists)
                mean_hist = np.mean(hist_array, axis=0)

                distances = np.linalg.norm(hist_array - mean_hist, axis=1)
                mean_dist = np.mean(distances)
                std_dist = np.std(distances)

                threshold = mean_dist + 2.5 * std_dist if std_dist > 1e-6 else np.inf

                for idx, dist in zip(valid_idx, distances):
                    rows[idx]["histogram_distance"] = round(dist, 4)

                    if dist > threshold:
                        rows[idx]["quality_grade"] = "exclude"
                        rows[idx]["suggested_action"] = "exclude"

                        flag_text = (
                            f"Histogram outlier (Z-score > 2.5, dist={dist:.2f})"
                        )
                        existing_flags = rows[idx]["quality_flags"]
                        rows[idx]["quality_flags"] = (
                            existing_flags + " | " + flag_text
                            if existing_flags
                            else flag_text
                        )
            else:
                for row in rows:
                    row["histogram_distance"] = np.nan
        else:
            for row in rows:
                row.pop("histogram", None)

        quality_df = pd.DataFrame(rows)

        if output_file is not None and not quality_df.empty:
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            quality_df.to_csv(output_file, index=False)

        return quality_df


@click.command(
    short_help="Compute per-series MRI quality scores directly from DICOM directories"
)
@click.argument("dicom_dirs")
@click.option(
    "--output",
    type=click.Path(),
    default="mri_quality_scores.csv",
    show_default=True,
    help="Path to save quality score CSV.",
)
@click.option(
    "--low_slice_threshold",
    type=int,
    default=10,
    show_default=True,
    help="Slice count below this threshold is penalized.",
)
@click.option(
    "--use_pixel_data/--no-use_pixel_data",
    default=False,
    show_default=True,
    help="Enable voxel-level quality metrics from DICOM volumes.",
)
@click.option(
    "--find_histogram_outliers/--no-find_histogram_outliers",
    default=False,
    show_default=True,
    help="Compute volume histograms and flag statistical outliers (forces pixel data loading).",
)
def main(
    dicom_dirs: tuple[str, ...],
    output: str | None,
    low_slice_threshold: int,
    use_pixel_data: bool,
    find_histogram_outliers: bool,
):
    if not dicom_dirs:
        click.echo(
            "Error: Please provide at least one absolute path to a DICOM directory."
        )
        return
    if use_pixel_data and find_histogram_outliers:
        click.echo(
            "Note: Enabling histogram outlier detection will automatically enable pixel data analysis."
        )

    dicom_dirs = (
        pd.read_csv(dicom_dirs)["DirectoryPath"] if ".csv" in dicom_dirs else dicom_dirs
    )

    checker = MRIQualityChecker(
        low_slice_threshold=low_slice_threshold,
        use_pixel_data=use_pixel_data,
        find_histogram_outliers=find_histogram_outliers,
    )

    checker.process_directories(list(dicom_dirs), output_file=output)
    click.echo(f"Quality scoring complete. Results saved to {output}")


if __name__ == "__main__":
    main()
