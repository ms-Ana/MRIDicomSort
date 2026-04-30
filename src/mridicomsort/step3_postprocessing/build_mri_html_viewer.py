#!/usr/bin/env python3
"""Build a static HTML viewer for MRI series thumbnails with metadata hover."""

from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import nibabel as nib
import numpy as np
import pandas as pd
from PIL import Image
import click
# from mridicomsort.utils.MRIScan import MRIScan


@dataclass
class SeriesEntry:
    patient: str
    date: str
    series: str
    target_path: Path
    action: str
    metadata: Dict[str, Any]


def safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_grouping_info(
    row: pd.Series, path: Path, patient_col: str, date_col: str
) -> Tuple[str, str, str]:
    """Intelligently extract Patient, Date, and Series from CSV or filename."""
    patient = row.get(patient_col)
    date = row.get(date_col)
    series = row.get("SeriesNumber") or row.get("Series")

    def is_valid(val: Any) -> bool:
        return val is not None and not pd.isna(val) and str(val).strip() != ""

    patient_valid = is_valid(patient)
    date_valid = is_valid(date)

    if not patient_valid or not date_valid:
        stem = path.name.replace(".nii.gz", "").replace(".nii", "")
        parts = stem.rsplit("_", 2)
        if len(parts) == 3 and parts[1].isdigit() and len(parts[1]) == 8:
            p_part, d_part, s_part = parts
            if not patient_valid:
                patient = p_part
            if not date_valid:
                date = d_part
            if not is_valid(series):
                series = s_part

    if not is_valid(patient) or not is_valid(date):
        parts = path.parts
        if path.is_file() and len(parts) >= 4:
            if not is_valid(patient):
                patient = parts[-4]
            if not is_valid(date):
                date = parts[-3]
        elif path.is_dir() and len(parts) >= 3:
            if not is_valid(patient):
                patient = parts[-3]
            if not is_valid(date):
                date = parts[-2]

    final_patient = str(patient) if is_valid(patient) else "UnknownPatient"
    final_date = str(date) if is_valid(date) else "UnknownDate"
    final_series = str(series) if is_valid(series) else path.name

    return final_patient, final_date, final_series


def load_entries_from_csv(
    csv_path: str, path_col: str, action_col: str, patient_col: str, date_col: str
) -> List[SeriesEntry]:
    df = pd.read_csv(csv_path)
    entries: List[SeriesEntry] = []

    display_fields = [
        path_col,
        "LLM_Assigned_Name",
        "Original_DICOM_Modality",
        "SeriesDescription",
        "AngioFlag",
        "Contrast",
        "EchoNumbers",
        "EchoTime",
        "EchoTrainLength",
        "FlipAngle",
        "ImagingFrequency",
        "MRAcquisitionType",
        "MagneticFieldStrength",
        "NumberOfAverages",
        "NumberOfPhaseEncodingSteps",
        "Orientation",
        "PixelBandwidth",
        "RepetitionTime",
        "ScanningSequence",
        "SliceThickness",
        "SpacingBetweenSlices",
        "quality_score",
        action_col,
        patient_col,
        date_col,
    ]
    for _, row in df.iterrows():
        if pd.isna(row.get(path_col)):
            continue

        target_path = Path(str(row[path_col])).resolve()
        action = str(row.get(action_col, "")).lower()

        meta = {}
        for col in display_fields:
            if col in df.columns and not pd.isna(row[col]):
                meta[col] = row[col]

        patient, date, series = parse_grouping_info(
            row, target_path, patient_col, date_col
        )

        entries.append(
            SeriesEntry(
                patient=patient,
                date=date,
                series=series,
                target_path=target_path,
                action=action,
                metadata=meta,
            )
        )
    return entries


def read_volume(path: Path) -> Optional[np.ndarray]:
    if not path.exists():
        return None

    try:
        if path.is_file() and path.name.endswith((".nii", ".nii.gz")):
            img = nib.load(str(path))
            vol = img.get_fdata()
            if vol.ndim >= 3:
                vol = np.transpose(vol, (2, 0, 1))
            return vol
        # elif path.is_dir():
        #     scan = MRIScan(str(path))
        #     volume = scan.volume
        #     if volume is None or getattr(volume, "ndim", 0) < 3:
        #         return None
        #     return volume
    except Exception as e:
        print(f"      DEBUG: Failed to read {path}: {e}")
        return None

    return None


def window_image(
    pixel_array: np.ndarray,
    center: Optional[float] = None,
    width: Optional[float] = None,
) -> np.ndarray:
    img = pixel_array.astype(np.float32)
    
    finite_mask = np.isfinite(img)
    if not np.any(finite_mask):
        return np.zeros_like(img, dtype=np.uint8)
    valid_pixels = img[finite_mask]

    if center is None or width is None or width <= 0:
        vmin = np.percentile(valid_pixels, 1) 
        vmax = np.percentile(valid_pixels, 99.8) 
        
        if vmax == vmin:
            return np.zeros_like(img, dtype=np.uint8)
            
        img = np.clip(img, vmin, vmax)
        scaled = (img - vmin) / (vmax - vmin)
        return (scaled * 255.0).astype(np.uint8)

    lower = center - width / 2.0
    upper = center + width / 2.0
    img = np.clip(img, lower, upper)
    scaled = (img - lower) / (upper - lower)
    return (scaled * 255.0).astype(np.uint8)


def render_slice_png(
    volume: np.ndarray,
    slice_index: int,
    window_center: Optional[float] = None,
    window_width: Optional[float] = None,
) -> Image.Image:
    pixel_array = volume[slice_index].astype(np.float32)
    pixel_array = np.rot90(pixel_array)
    windowed = window_image(pixel_array, window_center, window_width)
    return Image.fromarray(windowed, mode="L")


def select_slice_indices(count: int) -> List[int]:
    if count <= 0:
        return []
    if count == 1:
        return [0]
    if count == 2:
        return [0, 1]
    return [0, count // 2, count - 1]


def format_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    return value


def build_output_tree(output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    return output_dir, assets_dir


def build_thumbnail_paths(
    assets_dir: Path,
    patient: str,
    date: str,
    series: str,
    label: str,
) -> Tuple[Path, str]:
    safe_series = "".join(c for c in series if c.isalnum() or c in "._-")
    rel_dir = Path("assets") / patient / date / safe_series
    full_dir = assets_dir / patient / date / safe_series
    full_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{label}.png"
    return full_dir / file_name, str(rel_dir / file_name).replace(os.sep, "/")


def html_escape_json(data: Dict[str, Any]) -> str:
    clean_data = {}
    for k, v in data.items():
        if isinstance(v, float) and not np.isfinite(v):
            clean_data[k] = str(v)
        else:
            clean_data[k] = v
    return html.escape(json.dumps(clean_data, ensure_ascii=True, indent=2))


def build_html(
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]],
    output_dir: Path,
) -> str:
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>MRI Scan QC Preview</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Fraunces:wght@600;700&display=swap');

    :root {{
      --bg: #0a0d12;
      --bg-2: #101625;
      --card: #121a2a;
      --accent: #ffb454;
      --accent-2: #7bdff2;
      --text: #eef3ff;
      --muted: #9aa6c4;
      --border: rgba(255, 255, 255, 0.08);
      --shadow: 0 24px 80px rgba(3, 6, 16, 0.5);
      --danger-border: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.08);
      --success-bg: rgba(34, 197, 94, 0.2);
      --success-text: #4ade80;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: 'Space Grotesk', sans-serif;
      color: var(--text);
      background: radial-gradient(1200px 600px at 80% -10%, rgba(123, 223, 242, 0.15), transparent),
                  radial-gradient(900px 500px at 10% 20%, rgba(255, 180, 84, 0.18), transparent),
                  linear-gradient(160deg, var(--bg), var(--bg-2));
      min-height: 100vh;
      overflow-x: hidden;
    }}

    header {{
      padding: 32px 40px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }}

    .header-titles h1 {{
      font-family: 'Fraunces', serif;
      font-weight: 700;
      font-size: clamp(1.8rem, 2vw + 1rem, 3rem);
      margin: 0;
      letter-spacing: 0.02em;
    }}

    .header-titles p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.95rem;
    }}

    .export-btn {{
      background: var(--accent);
      color: #000;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-family: 'Space Grotesk', sans-serif;
      font-weight: 700;
      cursor: pointer;
      transition: transform 0.2s, box-shadow 0.2s;
      /* New additions below to push it to the bottom */
      margin-top: auto;
      width: 100%;
      flex-shrink: 0;
    }}

    .export-btn:hover {{
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(255, 180, 84, 0.3);
    }}

    .layout {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 380px;
      gap: 24px;
      padding: 0 40px 48px;
    }}

    @media (max-width: 1000px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .meta-panel {{ position: static; }}
    }}

    .patient {{
      background: rgba(18, 26, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 20px;
      margin-bottom: 24px;
      box-shadow: var(--shadow);
    }}

    .patient summary {{
      list-style: none;
      padding: 20px 24px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 600;
      font-size: 1.1rem;
    }}

    .patient summary::-webkit-details-marker {{ display: none; }}

    .date-group {{
      border-top: 1px solid var(--border);
      padding: 20px 24px 24px;
    }}

    .date-group h3 {{
      margin: 0 0 16px;
      font-size: 1rem;
      color: var(--accent-2);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}

    .series-grid {{
    display: grid;
    /* Increase the minimum width from 280px to something like 380px or 400px */
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); 
    gap: 16px;
    }}

    .series-card {{
      background: var(--card);
      border-radius: 18px;
      padding: 16px;
      border: 2px solid transparent;
      position: relative;
      overflow: hidden;
      transition: all 0.2s ease;
      cursor: pointer; 
    }}

    .series-card:hover {{
      border-color: rgba(255, 255, 255, 0.2);
    }}

    .series-card.excluded {{
      border: 2px solid var(--danger-border);
      background: var(--danger-bg);
    }}

    .series-card.excluded .status-badge {{
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
    }}

    .status-badge {{
      position: absolute;
      top: 12px;
      right: 12px;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 4px;
      background: var(--success-bg);
      color: var(--success-text);
      transition: all 0.2s ease;
      pointer-events: none;
    }}

    .series-card h4 {{
      margin: 0 0 8px;
      font-size: 1rem;
      word-break: break-all;
      padding-right: 70px;
    }}

    .series-card p {{
      margin: 0 0 14px;
      color: var(--muted);
      font-size: 0.85rem;
    }}

    .slice-row {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}

    .slice-row figure {{ margin: 0; position: relative; }}

    .slice-row img {{
      width: 100%;
      height: auto;
      aspect-ratio: 1 / 1; /* Forces a perfect square */
      object-fit: contain; 
      background-color: #000;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      transition: transform 0.25s ease, box-shadow 0.25s ease;
    }}

    .slice-row img:hover {{
      transform: translateY(-4px) scale(1.02);
      box-shadow: 0 18px 40px rgba(5, 10, 20, 0.4);
    }}

    .slice-row figcaption {{
      margin-top: 6px;
      font-size: 0.7rem;
      color: var(--muted);
      text-align: center;
    }}

    .meta-panel {{
      position: sticky;
      top: 24px;
      align-self: start;
      background: rgba(15, 20, 30, 0.9);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      /* Changed to flexbox to push button to the bottom */
      height: calc(100vh - 48px);
      display: flex;
      flex-direction: column;
      box-shadow: var(--shadow);
    }}

    .meta-panel h2 {{ 
      margin: 0 0 12px; 
      font-size: 1.1rem; 
      font-weight: 600; 
      flex-shrink: 0;
    }}

    .meta-panel pre {{
      margin: 0 0 20px 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: 'Space Grotesk', monospace;
      font-size: 0.8rem;
      line-height: 1.4;
      color: #f2f4ff;
      background: rgba(255, 255, 255, 0.04);
      padding: 12px;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      /* Changed to fill available space and scroll internally */
      flex-grow: 1;
      overflow: auto;
    }}
  </style>
</head>
<body>
<header>
    <div class="header-titles">
      <h1>MRI QC Viewer</h1>
      <p>Click any card to toggle Include/Exclude. Hover slices for metadata.</p>
    </div>
  </header>

  <div class=\"layout\">
    <main>
      {build_patient_sections(grouped)}
    </main>
    <aside class=\"meta-panel\">
      <h2>Scan Metadata</h2>
      <pre id=\"meta-output\">Hover a slice to see detailed metadata.</pre>
      <button id="export-btn" class="export-btn">💾 Export Updated QC</button>
    </aside>
  </div>

  <script>
    const metaOutput = document.getElementById('meta-output');
    let pinned = false;

    function updateMetadata(raw) {{
      try {{
        const parsed = JSON.parse(raw);
        metaOutput.textContent = JSON.stringify(parsed, null, 2);
      }} catch (err) {{
        metaOutput.textContent = raw;
      }}
    }}

    document.querySelectorAll('[data-meta]').forEach((img) => {{
      img.addEventListener('mouseenter', () => {{
        if (pinned) return;
        updateMetadata(img.dataset.meta);
      }});

      img.addEventListener('click', (e) => {{
        e.stopPropagation(); 
        
        pinned = !pinned;
        if (pinned) {{
          updateMetadata(img.dataset.meta);
          img.style.outline = '2px solid var(--accent)';
        }} else {{
          img.style.outline = 'none';
        }}
      }});
    }});

    document.querySelectorAll('.series-card').forEach(card => {{
      card.addEventListener('click', () => {{
        const isExcluded = card.classList.contains('excluded');
        const badge = card.querySelector('.status-badge');
        
        if (isExcluded) {{
            card.classList.remove('excluded');
            card.dataset.action = 'include';
            badge.textContent = 'INCLUDED';
        }} else {{
            card.classList.add('excluded');
            card.dataset.action = 'exclude';
            badge.textContent = 'EXCLUDED';
        }}
      }});
    }});

    document.getElementById('export-btn').addEventListener('click', () => {{
      let csvContent = "DirectoryPath,action\\n";
      
      document.querySelectorAll('.series-card').forEach(card => {{
        const path = card.dataset.path;
        const action = card.dataset.action;
        const safePath = path.replace(/"/g, '""');
        csvContent += `"${{safePath}}","${{action}}"\\n`;
      }});

      const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", "updated_qc_actions.csv");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }});
  </script>
</body>
</html>
"""


def build_patient_sections(grouped: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> str:
    blocks: List[str] = []
    for patient_id, date_map in grouped.items():
        date_sections: List[str] = []
        for date_id, series_entries in sorted(date_map.items()):
            series_cards = "\n".join(series_entries)
            date_sections.append(
                f"""
                <section class=\"date-group\">
                  <h3>{html.escape(format_date(date_id))}</h3>
                  <div class=\"series-grid\">{series_cards}</div>
                </section>
                """
            )
        total_series = sum(len(value) for value in date_map.values())
        blocks.append(
            f"""
            <details class=\"patient\" open>
              <summary>
                <div>Patient: {html.escape(patient_id)}</div>
                <span>{total_series} series</span>
              </summary>
              {"".join(date_sections)}
            </details>
            """
        )
    return "\n".join(blocks)


def build_series_card(
    patient: str,
    date: str,
    series: str,
    target_path: Path,
    action: str,
    metadata: Dict[str, Any],
    slice_cards: List[str],
) -> str:
    title = (
        metadata.get("LLM_Assigned_Name")
        or metadata.get("Series_Description")
        or series
    )
    score = metadata.get("quality_score", "N/A")

    is_excluded = action == "exclude"
    card_class = "series-card excluded" if is_excluded else "series-card"
    status_label = "EXCLUDED" if is_excluded else "INCLUDED"

    return f"""
      <article class=\"{card_class}\" data-path=\"{html.escape(str(target_path))}\" data-action=\"{html.escape(action)}\">
        <div class=\"status-badge\">{status_label}</div>
        <h4>{html.escape(str(title))}</h4>
        <p>Score :{html.escape(str(score))}</p>
        <div class=\"slice-row\">
          {"".join(slice_cards)}
        </div>
      </article>
    """


def build_slice_card(label: str, img_src: str, meta_json: str) -> str:
    return f"""
      <figure>
        <img src=\"{html.escape(img_src)}\" alt=\"{html.escape(label)}\" loading=\"lazy\" data-meta=\"{meta_json}\" />
        <figcaption>{html.escape(label)}</figcaption>
      </figure>
    """


def process_series(
    entry: SeriesEntry,
    assets_dir: Path,
) -> Optional[Dict[str, Any]]:
    volume = read_volume(entry.target_path)
    if volume is None:
        return None

    slice_count = volume.shape[0]
    if slice_count <= 0:
        return None

    indices = select_slice_indices(slice_count)
    if not indices:
        return None

    slice_cards: List[str] = []
    for i, slice_idx in enumerate(indices):
        try:
            image = render_slice_png(
                volume, slice_idx, window_center=None, window_width=None
            )
        except Exception as e:
            print(
                f"      DEBUG: Failed to render slice {slice_idx} for {entry.target_path}: {e}"
            )
            continue

        label = (
            ["First", "Middle", "Last"][i]
            if len(indices) == 3
            else f"Slice {slice_idx + 1}"
        )
        thumb_path, thumb_rel = build_thumbnail_paths(
            assets_dir, entry.patient, entry.date, entry.series, label.lower()
        )
        image.save(thumb_path)

        hover_meta = entry.metadata.copy()
        hover_meta["Displayed_SliceIndex"] = slice_idx

        slice_cards.append(
            build_slice_card(label, thumb_rel, html_escape_json(hover_meta))
        )

    if not slice_cards:
        return None

    return {
        "patient": entry.patient,
        "date": entry.date,
        "series": entry.series,
        "target_path": entry.target_path,
        "action": entry.action,
        "metadata": entry.metadata,
        "slice_cards": slice_cards,
    }


def build_grouped_html(
    series_entries: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for entry in series_entries:
        patient = entry["patient"]
        date = entry["date"]

        series_card = build_series_card(
            patient=patient,
            date=date,
            series=entry["series"],
            target_path=entry["target_path"],
            action=entry["action"],
            metadata=entry["metadata"],
            slice_cards=entry["slice_cards"],
        )
        grouped.setdefault(patient, {}).setdefault(date, []).append(series_card)
    return grouped


@click.command()
@click.argument("input_csv", type=click.Path(dir_okay=False, exists=True))
@click.option(
    "--path-column",
    default="file",
    help="Column name in the CSV that contains the absolute path to the DICOM dir or .nii.gz file.",
)
@click.option(
    "--action-column",
    default="suggested_action",
    help="Column name for the suggested action (e.g., 'exclude', 'include', 'check').",
)
@click.option(
    "--patient-column",
    default="patient",
    help="Column name in the CSV for Patient grouping (if available).",
)
@click.option(
    "--date-column",
    default="date",
    help="Column name in the CSV for Date grouping (if available).",
)
@click.option(
    "--output-dir",
    default="./mri_html_viewer_output",
    help="Output folder for HTML and generated thumbnails.",
)
@click.option(
    "--max-series",
    type=int,
    default=0,
    help="Optional cap on number of series to process (0 = no limit).",
)
@click.option(
    "--serve/--no-serve",
    default=False,
    help="Start a local HTTP server after building the page.",
)
@click.option(
    "--port",
    type=int,
    default=8000,
    help="Port for the optional local HTTP server.",
)
def main(
    input_csv,
    path_column,
    action_column,
    patient_column,
    date_column,
    output_dir,
    max_series,
    serve,
    port,
) -> None:

    csv_path = Path(input_csv)
    output_dir, assets_dir = build_output_tree(Path(output_dir))

    print(f"📁 Input CSV: {csv_path}")
    print(f"📁 Output dir: {output_dir}\n")

    entries = load_entries_from_csv(
        str(csv_path),
        path_column,
        action_column,
        patient_column,
        date_column,
    )
    if max_series > 0:
        entries = entries[:max_series]

    print(f"✓ Found {len(entries)} valid paths in CSV\n")

    processed: List[Dict[str, Any]] = []
    skipped = 0
    for i, entry in enumerate(entries, 1):
        result = process_series(entry, assets_dir)
        if result:
            processed.append(result)
            print(f"  [{i}/{len(entries)}] ✓ Processed: {entry.target_path.name}")
        else:
            skipped += 1
            print(
                f"  [{i}/{len(entries)}] ✗ Skipped (No volume found): {entry.target_path.name}"
            )

    print(f"\n✓ Generated {len(processed)} series visualisations")
    print(f"✗ Skipped {skipped} entries\n")

    grouped = build_grouped_html(processed)
    html_content = build_html(grouped, output_dir)

    index_path = output_dir / "index.html"
    index_path.write_text(html_content, encoding="utf-8")
    print(f"✓ HTML viewer written to: {index_path}")

    if serve:
        import http.server
        import socketserver

        os.chdir(output_dir)
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            print(f"Serving at http://127.0.0.1:{port}")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("Stopping server...")


if __name__ == "__main__":
    main()
