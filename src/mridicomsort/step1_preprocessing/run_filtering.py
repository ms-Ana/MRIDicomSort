from pathlib import Path

import click
from mridicomsort.step1_preprocessing.filtering import Filter


@click.command()
@click.argument(
    "dicom_report",
    type=click.Path(exists=True, dir_okay=False),
    required=False,
)
@click.option(
    "--output_file",
    type=click.Path(dir_okay=False),
    help="Path to save the actions file.",
    required=False,
)
@click.option(
    "--config_path",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the filter configuration YAML file.",
    required=False,
)
@click.option(
    "--rerun",
    is_flag=True,
    help="Whether to rerun the fit step even if the output file already exists.",
)
def main(
    dicom_report: str | Path | None = None,
    output_file: str | Path | None = None,
    config_path: str | Path | None = None,
    rerun: bool = False,
):

    print(f"Applying filters using report: {dicom_report}...")
    filter_instance = Filter(config_path=config_path)
    filter_instance.fit(report_path=dicom_report, output_file=output_file, rerun=rerun)


if __name__ == "__main__":
    main()
