from os.path import join

from hdx.utilities.downloader import Download
from hdx.utilities.path import temp_dir
from hdx.utilities.retriever import Retrieve

from hdx.scraper.hydrosheds.pipeline import Pipeline


class TestPipeline:
    def test_pipeline(
        self, configuration, read_dataset, fixtures_dir, input_dir, config_dir
    ):
        with temp_dir(
            "TestHydrosheds",
            delete_on_success=True,
            delete_on_failure=False,
        ) as tempdir:
            with Download(user_agent="test") as downloader:
                retriever = Retrieve(
                    downloader=downloader,
                    fallback_dir=tempdir,
                    saved_dir=input_dir,
                    temp_dir=tempdir,
                    save=False,
                    use_saved=True,
                )
                pipeline = Pipeline(configuration, retriever, tempdir)
                metadata = pipeline.get_metadata()
                global_boundaries = pipeline.get_global_boundaries(["bfa"])

                datasets = pipeline.generate_datasets(
                    "HydroBASINS", metadata["HydroBASINS"], global_boundaries
                )
                dataset = datasets[0]
                dataset.update_from_yaml(
                    path=join(config_dir, "hdx_dataset_static.yaml")
                )
                resources = dataset.get_resources()
                assert dataset == {
                    "name": "hydrobasins-bfa",
                    "title": "Burkina Faso: HydroBASINS",
                    "notes": "HydroBASINS represents a series of vectorized polygon layers that depict sub-basin boundaries at a global scale. The goal of this product is to provide a seamless global coverage of consistently sized and hierarchically nested sub-basins at different scales (from tens to millions of square kilometers), supported by a coding scheme that allows for analysis of catchment topology such as up- and downstream connectivity. HydroBASINS has been extracted from the gridded HydroSHEDS core layers at 15 arc-second resolution.  \n  \nAn important characteristic of any sub-basin delineation is the sub-basin breakdown, i.e. the decision of when and how to subdivide a larger basin into multiple tributary basins. At its highest level of sub-basin breakdown, HydroBASINS divides a basin into two sub-basins at every location where two river branches meet which each have an individual upstream area of at least 100 km². A second critical feature of sub-basin delineations is the way the sub-basins are grouped or coded to allow for the creation of nested sub-basins at different scales, or to navigate within the sub-basin network from up- to downstream. To support these functionalities and topological concepts, the ‘Pfafstetter’ coding system has been implemented in the HydroBASINS product offering 12 hierarchically nested sub-basin breakdowns globally.  \n  \nAt its highest level of sub-basin breakdown, HydroBASINS encompasses 1.0 million individual sub-basin polygons with an average area of 130.6 km², representing a total of 135.0 million km² of global land area (excluding Antarctica). HydroBASINS only includes a limited amount of (mostly geometric) attribute information, such as the sub-basin area, the distance from upstream headwaters and ocean outlet, and the Pfafstetter coding.",
                    "dataset_date": "[2013-01-01T00:00:00 TO 2013-12-31T23:59:59]",
                    "tags": [
                        {
                            "name": "hydrology",
                            "vocabulary_id": "b891512e-9516-4bf5-962a-7a289772a2a1",
                        }
                    ],
                    "subnational": "1",
                    "groups": [{"name": "bfa"}],
                    "methodology": "Other",
                    "methodology_other": "See [technical documentation](https://data.hydrosheds.org/file/technical-documentation/HydroBASINS_TechDoc_v1c.pdf) for more information.",
                    "license_id": "cc-by",
                    "dataset_source": "HydroSHEDS",
                    "package_creator": "HDX Data Systems Team",
                    "private": False,
                    "maintainer": "aa13de36-28c5-47a7-8d0b-6d7c754ba8c8",
                    "owner_org": "hdx",
                    "data_update_frequency": 365,
                }
                assert resources == [
                    {
                        "name": "HydroBASINS_bfa.zip",
                        "description": "HydroBASINS zipped shapefile for Burkina Faso",
                        "format": "shp",
                    },
                    {
                        "name": "HydroBASINS_TechDoc_v1c.pdf",
                        "description": "Technical documentation",
                        "format": "pdf",
                    },
                ]
