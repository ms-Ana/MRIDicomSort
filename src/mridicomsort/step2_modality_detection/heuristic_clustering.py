import json

import click
import numpy as np
import pandas as pd

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

ROUNDING_RULES = {
    "MagneticFieldStrength": 1,
    "FlipAngle": 0,
    "RepetitionTime": 0,
    "EchoTime": 0,
    "InversionTime": 0,
    "PixelSpacing": 3,
    "SliceThickness": 2,
}


def assign_to_bin(value, bin_edges):
    """Helper to place a numeric value into the correct bin string."""
    if pd.isna(value) or value is None or value == "":
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


def build_cluster_tree(df, rules, current_index=0):
    if df.empty:
        return []

    if current_index >= len(rules) or len(df) <= 1:
        return df["DirectoryPath"].tolist()

    rule = rules[current_index]
    attr = rule["attribute"]
    action = rule["action"]

    if attr not in df.columns:
        return build_cluster_tree(df, rules, current_index + 1)

    if action == "categorical_split":
        if rule.get("is_numeric"):
            precision = ROUNDING_RULES.get(attr, 2)
            group_keys = (
                pd.to_numeric(df[attr], errors="coerce")
                .round(precision)
                .fillna("Missing")
                .astype(str)
            )
        else:
            group_keys = df[attr].fillna("Missing").astype(str)

    elif action == "numeric_binning":
        precision = ROUNDING_RULES.get(attr, 2)
        rounded_series = pd.to_numeric(df[attr], errors="coerce").round(precision)
        group_keys = rounded_series.apply(lambda x: assign_to_bin(x, rule["bin_edges"]))

    else:
        group_keys = pd.Series("Other", index=df.index)

    clusters = dict(tuple(df.groupby(group_keys)))

    if len(clusters) <= 1:
        return build_cluster_tree(df, rules, current_index + 1)

    node = {"split_attribute": attr, "split_type": action, "branches": {}}

    for key, subset_df in clusters.items():
        node["branches"][key] = build_cluster_tree(subset_df, rules, current_index + 1)

    return node


def count_clusters(node):
    """Recursively counts the number of final leaf clusters in the tree."""
    if isinstance(node, list):
        return 1

    if isinstance(node, dict) and "branches" in node:
        return sum(count_clusters(branch) for branch in node["branches"].values())

    return 0


def compute_dataset_statistics(df):
    """Computes completion rates and unique values, rounding floats to fix scanner jitter."""
    total_valid_scans = len(df)
    stats = {}

    if total_valid_scans == 0:
        return stats

    for col in df.columns:
        if col in EXCLUDED_COLUMNS:
            continue

        valid_series = df[col].dropna()
        if valid_series.empty:
            continue

        is_numeric = False
        try:
            float_series = valid_series.astype(float)
            precision = ROUNDING_RULES.get(col, 2)
            valid_series = float_series.round(precision)

            is_numeric = True
        except (ValueError, TypeError):
            valid_series = valid_series.astype(str).str.strip()
            valid_series = valid_series[valid_series.str.lower() != "nan"]

        count = len(valid_series)
        unique_vals = valid_series.unique().tolist()

        stats[col] = {
            "scan_count": count,
            "percent_filled": (count / total_valid_scans) * 100
            if total_valid_scans
            else 0,
            "unique_values_count": len(unique_vals),
            "unique_values": unique_vals,
            "is_numeric": is_numeric,
        }
    return stats


def print_cluster_sizes(node, path=""):
    """Recursively prints the size of each final cluster."""
    if isinstance(node, list):
        print(f"Cluster: [{path.strip(' -> ')}] - {len(node)} scans")
        return

    if isinstance(node, dict) and "branches" in node:
        for branch_name, branch_node in node["branches"].items():
            new_path = f"{path}{node['split_attribute']}={branch_name} -> "
            print_cluster_sizes(branch_node, new_path)


def determine_split_rules(df, stats):
    """Applies heuristics using the FULL data distribution for correct binning."""
    split_rules = []

    for attr, data in stats.items():
        if data["percent_filled"] <= 50.0:
            continue
        if data["unique_values_count"] <= 1:
            continue

        unique_count = data["unique_values_count"]
        is_numeric = data["is_numeric"]

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

                precision = ROUNDING_RULES.get(attr, 2)
                full_numeric_series = df[attr].dropna().astype(float).round(precision)

                bins = np.histogram_bin_edges(
                    full_numeric_series, bins=min(10, unique_count)
                )
                rule["bin_edges"] = [round(b, precision) for b in bins.tolist()]
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
    df = df[df["Action"] == "include"] if "Action" in df.columns else df

    print(
        f"Filtered out excluded scans. Processing {len(df)} included scans (out of {initial_count} total)."
    )

    if df.empty:
        print("No valid 'include' scans found to cluster.")
        return

    stats = compute_dataset_statistics(df)
    rules = determine_split_rules(df, stats)

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

    cluster_tree = build_cluster_tree(df, rules)

    with open(output, "w") as f:
        json.dump(cluster_tree, f, indent=2)

    print(
        f"Clustering complete. Tree saved to {output}. Total clusters: {count_clusters(cluster_tree)}"
    )

    print("\n--- Cluster Breakdown ---")
    print_cluster_sizes(cluster_tree)


if __name__ == "__main__":
    main()
