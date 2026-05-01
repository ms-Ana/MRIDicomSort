import json
import click
import pandas as pd


def extract_rows(node, rows_list):
    """Recursively traverses the named cluster tree to extract flat rows."""
    if isinstance(node, dict) and "cluster_name" in node:
        cluster_name = node["cluster_name"]
        split_criteria = node.get("split_criteria", {})

        for path in node.get("paths", []):
            row = {
                "DirectoryPath": path,
                "LLM_Assigned_Name": cluster_name,
            }
            for param, value in split_criteria.items():
                row[param] = value

            rows_list.append(row)

    elif isinstance(node, dict) and "branches" in node:
        # We are at a split node, keep digging
        for branch_node in node["branches"].values():
            extract_rows(branch_node, rows_list)


@click.command()
@click.argument("named_clusters_json", type=click.Path(exists=True, dir_okay=False))
@click.argument("meta_csv", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--output",
    type=click.Path(file_okay=True),
    default="dicom_clusters_summary.csv",
    help="Output CSV filename",
)
def main(named_clusters_json, meta_csv, output):
    print("Loading files...")

    with open(named_clusters_json, "r") as f:
        tree_data = json.load(f)

    print(f"Loading metadata from {meta_csv}...")
    df = pd.read_csv(meta_csv)
    df_clean = df.where(pd.notnull(df), None)

    metadata_lookup = df_clean.set_index("DirectoryPath").to_dict(orient="index")

    print("Flattening cluster tree...")
    raw_rows = []
    extract_rows(tree_data, raw_rows)

    print("Merging data and formatting CSV...")

    all_columns = set()

    for row in raw_rows:
        path = row["DirectoryPath"]

        meta = metadata_lookup.get(path, {})
        row.update(meta)
        all_columns.update(row.keys())

    base_columns = [
        "DirectoryPath",
        "LLM_Assigned_Name",
        "MRAcquisitionType",
        "Orientation",
        "Contrast",
        "SeriesDescription",
        "Action",
        "Pre Filter Reason",
    ]

    all_columns = base_columns + sorted(
        [col for col in all_columns if col not in base_columns]
    )
    result_df = pd.DataFrame(raw_rows, columns=all_columns)

    result_df.to_csv(output, index=False)
    print(f"Success! Exported {len(raw_rows)} directories to {output}")


if __name__ == "__main__":
    main()
