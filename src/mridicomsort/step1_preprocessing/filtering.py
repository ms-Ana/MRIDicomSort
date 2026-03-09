import os
import yaml
import pandas as pd
from mridicomsort.config import CONFIG, NUM_WORKERS

from tqdm import tqdm
import concurrent.futures


def process_single_row(row: dict, config: dict) -> tuple[str, str, str]:
    """
    Applies config rules to a single row from the DICOM metadata CSV report.
    """
    path_key = str(row.get("DirectoryPath", "unknown_path"))
    exclude_action = config.get("exclude_action", "exclude")

    if str(row.get("Status")).lower() == "error":
        return path_key, exclude_action, "Scan failed validation (Status != ok)"

    for filter_name, filter_config in config.get("PRE-FILTERS", {}).items():
        parameter = filter_config["parameter"]
        raw_value = row.get(parameter)

        if (
            pd.isna(raw_value)
            or str(raw_value).strip().lower() == "nan"
            or raw_value == ""
        ):
            continue  

        if isinstance(raw_value, str) and "\\" in raw_value:
            raw_value = raw_value.split("\\")

        if isinstance(raw_value, list):
            str_value = " ".join(str(x) for x in raw_value).lower()
        else:
            str_value = str(raw_value).lower()

        if "exclude" in filter_config:
            for excluded in filter_config["exclude"]:
                if str(excluded).lower() in str_value:
                    return (
                        path_key,
                        exclude_action,
                        f"{filter_name} - Excluded value found: {excluded}",
                    )

        if "include" in filter_config:
            rules = filter_config["include"]

            if isinstance(rules[0], dict):
                try:
                    if isinstance(raw_value, list):
                        num_values = [float(x) for x in raw_value]
                    else:
                        num_values = [float(raw_value)]
                except (ValueError, TypeError):
                    return (
                        path_key,
                        exclude_action,
                        f"{filter_name} - Value is not a number: {raw_value}",
                    )

                for rule in rules:
                    min_val = rule.get("min", float("-inf"))
                    max_val = rule.get("max", float("inf"))

                    for num_value in num_values:
                        if num_value < min_val:
                            return (
                                path_key,
                                exclude_action,
                                f"{filter_name} - Value below minimum: {num_value}",
                            )
                        if num_value > max_val:
                            return (
                                path_key,
                                exclude_action,
                                f"{filter_name} - Value above maximum: {num_value}",
                            )

            else:
                filter_values = [str(v).lower() for v in rules]

                if isinstance(raw_value, list):
                    raw_list_lower = [str(x).lower() for x in raw_value]
                    if not any(f_val in raw_list_lower for f_val in filter_values):
                        return (
                            path_key,
                            exclude_action,
                            f"{filter_name} - Value not included: {raw_value}",
                        )
                else:
                    if str_value not in filter_values:
                        return (
                            path_key,
                            exclude_action,
                            f"{filter_name} - Value not included: {raw_value}",
                        )
    if "check" in str(row.get("Status")).lower():
        return (
            path_key,
            "check",
            "Scan is not excluded but requires manual review (Status = check)",
        )

    return path_key, "include", "All filters passed"


class Filter:
    def __init__(self, config_path: str = None):
        if config_path:
            with open(config_path, "r") as file:
                self.config = yaml.safe_load(file)
        else:
            self.config = CONFIG
        self.workers = NUM_WORKERS

    def fit(self, report_path: str, output_file: str = None, rerun: bool = False):
        """
        Analyze the consolidated metadata CSV and create a file specifying actions.
        """
        if not report_path or not os.path.exists(report_path):
            raise FileNotFoundError(f"Report file not found: {report_path}")

        if output_file and os.path.exists(output_file) and not rerun:
            print(f"Output file {output_file} already exists. Skipping fit step.")
            return

        print(f"Loading DICOM metadata from {report_path}...")

        df_report = pd.read_csv(report_path)

        if df_report.empty:
            print("No scans/rows found in the report.")
            return

        actions = {"DirectoryPath": [], "action": [], "pre-filters-reason": []}

        rows = df_report.to_dict(orient="records")

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=self.workers
        ) as executor:
            futures = {
                executor.submit(process_single_row, row, self.config): row
                for row in rows
            }

            for future in tqdm(
                concurrent.futures.as_completed(futures),
                total=len(futures),
                desc="Applying pre-filters",
            ):
                path_key, action, reason = future.result()

                actions["DirectoryPath"].append(path_key)
                actions["action"].append(action)
                actions["pre-filters-reason"].append(reason)

        df_actions = pd.DataFrame(actions)
        if output_file:
            df_actions.to_csv(output_file, index=False)
        else:
            output_file = report_path
            df_actions = pd.merge(df_report, df_actions, on="DirectoryPath", how="left")
            df_actions.to_csv(output_file, index=False)
        print(
            f"Filtering complete. Processed {len(df_actions)} scans. Actions saved to {output_file}"
        )
