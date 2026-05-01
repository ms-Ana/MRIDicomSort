import json
from collections import defaultdict

import click
import pandas as pd
from openai import OpenAI
from tqdm import tqdm

from mridicomsort.config import LLM_API_KEY, LLM_BASE_URL, MODEL_NAME

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


# sequence acronyms (taken from https://www.imaios.com/en/e-mri/sequences/sequences-acronyms)
def generate_cluster_name(
    split_history: dict, additional_context: dict, model_name: str = MODEL_NAME
) -> str:
    """Calls OpenAIClient  to generate a short, clinical name for the modality cluster."""

    prompt = f"""
    You are given a cluster of MRI series that share similar acquisition parameters and metadata.
    --- SPLIT-DEFINING PARAMETERS ---
    {json.dumps(split_history, indent=2)}

    --- Additional Context ---
    {json.dumps(additional_context, indent=2)}


    Your task is to assign a single standardized clinical label for this cluster.

    Follow these rules strictly:

    1. Determine the PRIMARY contrast weighting using acquisition parameters:
    DWI, T1, T2

    2. Identify the sequence family if possible:
    The sequence family is determined by the combination of parameters and can be one of the following:
    - SE (Spin Echo) including:
        - Fast SE: 	Phillips:Turbo SE; Siemens: Turbo SE; GE: Fast SE; Hitachi: Fast SE; Toshiba: Fast SE
        - Ultra fast SE: Phillips: SSH-TSE, UFSE; Siemens: SSTSE, HASTE; GE: SS-FSE; Hitachi: FSE - ADA, Toshiba: (Super)FASE DIET

    - Multi SE (Multi Spin Echo): Phillips: Multi SE; Siemens: Multi écho MS; GE: SE, Hitachi: SE; Toshiba: Multi écho

    - IR (Inversion Recovery): Phillips: IR, IR TSE; Siemens: IR/IRM, TurboIR/TIRM; GE: IR, FSE-IR; Hitachi: IR, FIR; Toshiba: IR, Fast IR
    - STIR (Short Tau Inversion Recovery): Phillips: STIR, STIR TSE; Siemens: STIR, Turbo STIR; GE: STIR, Fast STIR; Hitachi: STIR; Toshiba: STIR
    - FLAIR (Fluid Attenuated Inversion Recovery): Phillips: FLAIR, FLAIR TSE; Siemens: FLAIR, Turbo FLAIR; GE: FLAIR, Fast FLAIR; Hitachi: FLAIR, Fast FLAIR; Toshiba: FLAIR, Fast FLAIR

    - GRE (Gradient Echo): Phillips: FFE; Siemens: GRE; GE: GRE; Hitachi: GE; Toshiba: FE including:
        - Spoiled GRE: Phillips: T1 FFE; Siemens: FLASH; GE: SPGR, MPSPGR; Hitachi: RSSG; Toshiba: RF-spoiled, FE
        - Ultra fast GRE: Phillips: T1-TFE, T2-TFE, THRIVE; Siemens: TurboFLASH, VIBE; GE: FGRE, Fast SPGR, FMPSPGR, VIBRANT, FAME, LAVA; Hitachi: SARGE; Toshiba: Fast FE, RADIANCE, QUICK 3D
        - Steady stage GRE: Phillips: FFE; Siemens: FISP; GE: MPGR, GRE; Hitachi: TRSG; Toshiba: FE
        - Ultrafast GE with magnetization preparation: Phillips: IR-TFE; Siemens: T1/T2-TurboFLASH; GE:	IR-FSPGR, DE-FSPGR; Toshiba: Fast FE
        - Contrast-enhanced GRE: 	Phillips: T2-FFE T2, Siemens: PSIF, GE:SSFP, Toshiba: FE
        - Balanced GRE: Phillips: Balanced FFE; Siemens:	Turbo FISP;	GE: FIESTA;	Hitachi: BASG; Toshiba:	True SSFP

    - SE-EPI (Echo Planar Imaging):	Phillips:SE-EPI; Siemens: EPI SE; GE: SE EPI; Hitachi: SE EPI; Toshiba:	 EPI
    - GRE-EPI (Echo Planar Imaging): Phillips: FFE-EPI, TFE-EPI; Siemens: EPI Perf, EPIFI; GE: GRE EPI; Hitachi: SG-EPI; Toshiba: FE-EPI


    Use manufacturer independent terminology: SE insted of Turbo SE, GRE instead of FFE, etc. (SE, Multi SE, IR, STIR, FLAIR, GRE,  SE-EPI, GRE-EPI)

    4. Do NOT include:
    - acquisition plane (axial, sagittal, coronal)
    - dimensionality (2D/3D)
    - contrast

    6. Output format:
    - Use underscores as separators
    - Keep it concise and standardized
    - Response should be a single string label that captures the primary contrast and sequence family if applicable.

    Examples: T1_GRE, T2_SE, T2_GRE, DWI, DWI_MULTI_B
    """

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "  You are an expert radiologist and MRI physicist.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return "Unknown_Cluster"


def get_cluster_context(
    cluster_paths: list, leaves_lookup: dict, split_keys: set
) -> dict:
    """Gathers non-split attributes from the CSV columns for the scans in a cluster."""
    context_agg = defaultdict(set)

    target_keys = [
        "SeriesDescription",
        "StudyDescription",
        "SequenceName",
        "ImageType",
        "ScanningSequence",
        "SequenceVariant",
        "ScanOptions",
    ]

    for path in cluster_paths:
        row_data = leaves_lookup.get(path, {})

        for k in target_keys:
            if k in split_keys:
                continue  # Skip attributes we already know from the split history

            v = row_data.get(k)
            if k == "SeriesDescription":
                v = str(v).lower().replace(" ", "_") if v is not None else None

            if v is None or str(v).strip() == "" or str(v).lower() == "nan":
                continue

            context_agg[k].add(str(v))

    summary = {}
    for k in target_keys:
        if k in context_agg and len(context_agg[k]) > 0:
            if len(context_agg[k]) <= 5:
                summary[k] = list(context_agg[k])

    return summary


def traverse_and_name(node, split_history, leaves_lookup, progress_bar):
    """Recursively walks the tree, calling the LLM at the terminal leaves."""

    if isinstance(node, list):
        split_keys = set(split_history.keys())
        additional_context = get_cluster_context(node, leaves_lookup, split_keys)

        cluster_name = generate_cluster_name(split_history, additional_context)
        progress_bar.update(1)

        return {
            "cluster_name": cluster_name,
            "split_criteria": split_history,
            "scan_count": len(node),
            "paths": node,
        }

    result = {
        "split_attribute": node.get("split_attribute"),
        "split_type": node.get("split_type"),
        "branches": {},
    }

    for branch_val, child_node in node.get("branches", {}).items():
        new_history = split_history.copy()
        new_history[node["split_attribute"]] = branch_val
        result["branches"][branch_val] = traverse_and_name(
            child_node, new_history, leaves_lookup, progress_bar
        )

    return result


def count_leaves(node):
    """Helper to count terminal leaves for the progress bar."""
    if isinstance(node, list):
        return 1
    return sum(count_leaves(child) for child in node.get("branches", {}).values())


@click.command()
@click.argument("meta_csv", type=click.Path(exists=True, dir_okay=False))
@click.argument("cluster_json", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output", type=click.Path(file_okay=True), default="named_dicom_clusters.json"
)
def main(meta_csv, cluster_json, output):
    print(f"Loading metadata from {meta_csv}...")

    df = pd.read_csv(meta_csv)
    df_clean = df.where(pd.notnull(df), None)

    leaves_lookup = df_clean.set_index("DirectoryPath").to_dict(orient="index")

    print(f"Loading cluster tree from {cluster_json}...")
    with open(cluster_json, "r") as f:
        cluster_tree = json.load(f)

    total_clusters = count_leaves(cluster_tree)
    print(f"Found {total_clusters} terminal clusters to name. Contacting OpenAI...")

    with tqdm(total=total_clusters, desc="Naming Clusters") as pbar:
        named_tree = traverse_and_name(cluster_tree, {}, leaves_lookup, pbar)

    with open(output, "w") as f:
        json.dump(named_tree, f, indent=2)

    print(f"\nDone! Named cluster tree saved to {output}.")


if __name__ == "__main__":
    main()
