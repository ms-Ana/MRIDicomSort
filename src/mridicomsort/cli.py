import click 







@click.group()
def cli():
    """MRIDicomSort: A tool for sorting MRI DICOM files."""
    pass

cli.add_command()







if __name__ == "__main__":
    cli()