#!/usr/bin/python
"""
Top level script. Calls other functions that generate datasets that this
script then creates in HDX.

"""

import logging
from os.path import expanduser, join
from pathlib import Path

from hdx.api.configuration import Configuration
from hdx.data.location import Location
from hdx.data.user import User
from hdx.facades.infer_arguments import facade
from hdx.utilities.downloader import Download
from hdx.utilities.path import (
    script_dir_plus_file,
    wheretostart_tempdir_batch,
)
from hdx.utilities.retriever import Retrieve

from hdx.scraper.hydrosheds._version import __version__
from hdx.scraper.hydrosheds.pipeline import Pipeline

logger = logging.getLogger(__name__)

_LOOKUP = "hdx-scraper-hydrosheds"
_SAVED_DATA_DIR = "saved_data"  # Keep in repo to avoid deletion in /tmp
_UPDATED_BY_SCRIPT = "HDX Scraper: Hydrosheds"


def main(
    save: bool = False,
    use_saved: bool = False,
) -> None:
    """Generate datasets and create them in HDX

    Args:
        save: Save downloaded data. Defaults to False.
        use_saved: Use saved data. Defaults to False.

    Returns:
        None
    """
    logger.info(f"##### {_LOOKUP} version {__version__} ####")
    configuration = Configuration.read()
    User.check_current_user_write_access("hdx")

    with wheretostart_tempdir_batch(folder=_LOOKUP) as info:
        tempdir = info["folder"]
        with Download() as downloader:
            retriever = Retrieve(
                downloader=downloader,
                fallback_dir=tempdir,
                saved_dir=_SAVED_DATA_DIR,
                temp_dir=tempdir,
                save=save,
                use_saved=use_saved,
            )
            pipeline = Pipeline(configuration, retriever, tempdir)
            metadata = pipeline.get_metadata()
            countries = Location.get_data_grid_countries()
            global_boundaries = pipeline.get_global_boundaries(countries)
            for data_type, download_links in metadata.items():
                datasets = pipeline.generate_datasets(
                    data_type, download_links, global_boundaries
                )
                for dataset in datasets:
                    dataset.update_from_yaml(
                        script_dir_plus_file(
                            join("config", "hdx_dataset_static.yaml"), main
                        )
                    )
                    dataset.create_in_hdx(
                        remove_additional_resources=True,
                        match_resource_order=False,
                        updated_by_script=_UPDATED_BY_SCRIPT,
                        batch=info["batch"],
                    )
                for f in pipeline.get_last_temp_files():
                    Path(f).unlink(missing_ok=True)


if __name__ == "__main__":
    facade(
        main,
        user_agent_config_yaml=join(expanduser("~"), ".useragents.yaml"),
        user_agent_lookup=_LOOKUP,
        project_config_yaml=script_dir_plus_file(
            join("config", "project_configuration.yaml"), main
        ),
    )
