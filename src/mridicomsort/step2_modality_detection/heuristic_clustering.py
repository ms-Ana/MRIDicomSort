import json
import click
import numpy as np
import pandas as pd
from collections import defaultdict

EXCLUDED_COLUMNS = [
    "DirectoryPath",
    "Status",
    "NumberOfSlices",
    "MultipleStacks",
    "Orientation",
    "NiftiSafe",
    "Is4D",
    "StackCount",
    "TriggerType",
    "DetailedParams",
    "ZSpacing",
    "ValidationNote",
    "MRAcquisitionType",
    "ImageType",
    "SOPClassUID",
    "Modality",
    "StudyDescription",
    "SeriesDescription",
    "ContrastBolusAgent",
    "ContrastBolusRoute",
    "ContrastBolusVolume",
    "ContrastBolusTotalDose",
    "ContrastBolusIngredient",
    "ContrastBolusIngredientConcentration",
    "Action",
    "Pre Filter Reason",
    "Contrast",
    "SeriesNumber",
    "AcquisitionNumber",
]


def is_numeric_list(values):
    """Check if a list of unique values can all be safely cast to floats."""
    if not values:
        return False

    for v in values:
        if pd.isna(v):
            continue
        if isinstance(v, bool) or str(v).strip().lower() in ["true", "false"]:
            return False
        if isinstance(v, str) and "\\" in v:
            return False
        try:
            float(v)
        except (ValueError, TypeError):
            return False
    return True


def assign_to_bin(value, bin_edges):
    """Helper to place a numeric value into the correct bin string."""
    if pd.isna(value) or value is None:
        return "Missing"
    try:
        val = float(value)
        if val <= bin_edges[0]:
            return f"<= {bin_edges[0]}"
        if val >= bin_edges[-1]:
            return f">= {bin_edges[-1]}"

        for i in range(len(bin_edges) - 1):
            if bin_edges[i] <= val <= bin_edges[i + 1]:
                return f"{bin_edges[i]} to {bin_edges[i + 1]}"
        return "Unknown"
    except (ValueError, TypeError):
        return "Invalid/Missing"


def build_cluster_tree(leaves, rules, current_index=0):
    """
    Recursively builds a tree by splitting leaves according to the sorted rules.
    """
    if not leaves:
        return []

    if current_index >= len(rules) or len(leaves) <= 1:
        return [leaf.get("DirectoryPath", "Unknown") for leaf in leaves]

    rule = rules[current_index]
    attr = rule["attribute"]
    action = rule["action"]

    clusters = defaultdict(list)

    for leaf in leaves:
        val = leaf.get(attr)

        if pd.isna(val) or val is None or val == "":
            group_key = "Missing"
        elif action == "categorical_split":
            group_key = str(val)
        elif action == "numeric_binning":
            group_key = assign_to_bin(val, rule["bin_edges"])
        else:
            group_key = "Other"

        clusters[group_key].append(leaf)

    if len(clusters) <= 1:
        return build_cluster_tree(leaves, rules, current_index + 1)

    node = {"split_attribute": attr, "split_type": action, "branches": {}}

    for key, group_leaves in clusters.items():
        node["branches"][key] = build_cluster_tree(
            group_leaves, rules, current_index + 1
        )

    return node


def compute_dataset_statistics(df):
    """Computes completion rates and unique values using Pandas."""
    total_valid_scans = len(df)
    stats = {}

    if total_valid_scans == 0:
        return stats
    for col in df.columns:
        if col in EXCLUDED_COLUMNS:
            continue

        valid_series = df[col].dropna()
        if valid_series.dtype == object:
            valid_series = valid_series[valid_series.astype(str).str.strip() != ""]
            valid_series = valid_series[valid_series.astype(str).str.lower() != "nan"]

        count = len(valid_series)
        unique_vals = valid_series.unique().tolist()

        stats[col] = {
            "scan_count": count,
            "percent_filled": (count / total_valid_scans) * 100
            if total_valid_scans
            else 0,
            "unique_values_count": len(unique_vals),
            "unique_values": unique_vals,
        }
    return stats


def determine_split_rules(stats):
    """Applies heuristics to determine how (and if) to split attributes."""
    split_rules = []

    for attr, data in stats.items():
        if data["percent_filled"] <= 50.0:
            continue

        if data["unique_values_count"] <= 1:
            continue

        unique_count = data["unique_values_count"]
        is_numeric = is_numeric_list(data["unique_values"])

        rule = {
            "attribute": attr,
            "unique_count": unique_count,
            "is_numeric": is_numeric,
            "action": None,
        }

        if unique_count < 10:
            rule["action"] = "categorical_split"
            rule["split_values"] = data["unique_values"]
        else:
            if is_numeric:
                rule["action"] = "numeric_binning"
                float_vals = [float(x) for x in data["unique_values"]]
                bins = np.histogram_bin_edges(float_vals, bins=min(10, len(float_vals)))
                rule["bin_edges"] = [round(b, 3) for b in bins.tolist()]
            else:
                rule["action"] = "drop_high_cardinality_categorical"

        if rule["action"] in ["categorical_split", "numeric_binning"]:
            split_rules.append(rule)

    split_rules.sort(key=lambda x: x["unique_count"])
    return split_rules


@click.command()
@click.argument("input_csv", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output",
    type=click.Path(file_okay=True),
    default="dicom_clusters.json",
    help="Output JSON filename",
)
def main(input_csv, output):
    print(f"Loading metadata from {input_csv}...")
    df = pd.read_csv(input_csv)

    initial_count = len(df)
    df = df[df["action"] == "include"] if "action" in df.columns else df

    print(
        f"Filtered out excluded scans. Processing {len(df)} included scans (out of {initial_count} total)."
    )

    if df.empty:
        print("No valid 'include' scans found to cluster.")
        return

    stats = compute_dataset_statistics(df)
    rules = determine_split_rules(stats)

    print("\n--- HEURISTIC CLUSTERING RULES ---")
    if not rules:
        print("No rules generated. The dataset might be too uniform or sparse.")
    for rule in rules:
        print(f"\nAttribute: {rule['attribute']}")
        print(f"  Action: {rule['action']}")
        print(
            f"  Unique Values: {rule['unique_count']} (Numeric: {rule['is_numeric']})"
        )

        if rule["action"] == "categorical_split":
            print(f"  Split Paths: {rule['split_values'][:5]}...")
        elif rule["action"] == "numeric_binning":
            print(f"  Bin Edges: {rule['bin_edges']}")

    print("\nBuilding hierarchical clustering tree...")

    df_clean = df.where(pd.notnull(df), None)
    leaves = df_clean.to_dict(orient="records")

    cluster_tree = build_cluster_tree(leaves, rules)

    with open(output, "w") as f:
        json.dump(cluster_tree, f, indent=2)

    print(f"Clustering complete. Tree saved to {output}.")


if __name__ == "__main__":
    main()