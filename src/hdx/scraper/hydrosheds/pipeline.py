#!/usr/bin/python
"""Hydrosheds scraper"""

import logging
import re
import zipfile
from os.path import basename, join
from pathlib import Path

from bs4 import BeautifulSoup
from geopandas import GeoDataFrame, read_file, sjoin
from hdx.api.configuration import Configuration
from hdx.data.dataset import Dataset
from hdx.data.resource import Resource
from hdx.location.country import Country
from hdx.utilities.retriever import Retrieve
from pandas import isna
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, configuration: Configuration, retriever: Retrieve, tempdir: str):
        self._configuration = configuration
        self._retriever = retriever
        self._tempdir = tempdir
        self._last_temp_files = []

    def get_last_temp_files(self) -> list:
        return self._last_temp_files

    def get_metadata(self) -> dict:
        metadata = {}
        for data_type, data_info in self._configuration["data_types"].items():
            logger.info(f"Processing data type: {data_type}")
            url = f"{self._configuration['base_url']}{data_type.lower()}"
            text = self._retriever.download_text(url)
            soup = BeautifulSoup(text, "html.parser")
            lines = soup.find_all("a", href=True)
            download_links = []
            documentation_link = None
            for line in lines:
                href = line["href"]
                if re.search(
                    f"{data_type.lower()}\\stechnical\\sdocumentation",
                    str(line),
                    re.IGNORECASE,
                ):
                    documentation_link = href
                if re.search(data_info["file_pattern"], href, re.IGNORECASE):
                    download_links.append(href)
            metadata[data_type] = {
                "download_links": download_links,
                "documentation_link": documentation_link,
            }
        return metadata

    def get_global_boundaries(self, countries: list[str]) -> GeoDataFrame:
        dataset = Dataset.read_from_hdx(self._configuration["boundary_dataset"])
        resources = dataset.get_resources()
        resource = [
            r
            for r in resources
            if self._configuration["boundary_resource"] in r["name"]
        ]
        resource = resource[0]
        if self._retriever.use_saved:
            file_path = self._retriever.download_file(
                resource["url"], filename=resource["name"]
            )
        else:
            folder = (
                self._retriever.saved_dir if self._retriever.save else self._tempdir
            )
            _, file_path = resource.download(folder)
        lyr = read_file(file_path)
        for i, row in lyr.iterrows():
            if not lyr.geometry[i].is_valid:
                lyr.loc[i, "geometry"] = make_valid(lyr.geometry[i])
            if not isna(row["STATUS"]) and row["STATUS"][:4] == "Adm.":
                lyr.loc[i, "ISO_3"] = row["Color_Code"]

        countries = [c.upper() for c in countries]
        lyr = lyr[lyr["ISO_3"].isin(countries)]
        lyr = lyr.dissolve(by="ISO_3", as_index=False)
        lyr = lyr.drop(
            [f for f in lyr.columns if f.lower() not in ["iso_3", "geometry"]],
            axis=1,
        )

        return lyr

    def generate_datasets(
        self, data_type: str, metadata: dict, global_boundaries: GeoDataFrame
    ) -> list[Dataset]:
        datasets = []
        data_info = self._configuration["data_types"][data_type]

        # download and unzip data
        unzip_folder = join(self._tempdir, data_type)
        for download_link in metadata["download_links"]:
            zipfile_path = self._retriever.download_file(download_link)
            self._last_temp_files.append(zipfile_path)
            with zipfile.ZipFile(zipfile_path, "r") as z:
                z.extractall(unzip_folder)
        unzipped_files = [f for f in Path(unzip_folder).rglob("*") if f.is_file()]
        self._last_temp_files.extend(unzipped_files)
        file_list = list(Path(unzip_folder).rglob("*.shp"))
        input_datas = {
            basename(file_path): read_file(file_path) for file_path in file_list
        }

        # download technical documentation
        tech_doc_link = metadata["documentation_link"]
        tech_doc = self._retriever.download_file(
            tech_doc_link,
            basename(tech_doc_link),
        )

        # subset data
        subset_method = data_info["subset_method"]
        attribute = data_info["attribute"]

        # Add iso3 attribute if necessary
        if subset_method == "subset":
            for _, input_data in input_datas.items():
                iso3s = []
                for cname in input_data[attribute]:
                    ciso, _ = Country.get_iso3_country_code_fuzzy(cname)
                    iso3s.append(ciso)
                input_data["ISO3"] = iso3s

        for iso3 in global_boundaries["ISO_3"]:
            country_name = Country.get_country_name_from_iso3(iso3)
            logger.info(f"Processing country: {country_name}")

            country_folder = join(self._tempdir, f"{data_type}_{iso3}")
            Path(country_folder).mkdir(exist_ok=True)

            for file_name, input_data in input_datas.items():
                if subset_method == "subset":
                    data = input_data.loc[input_data["ISO3"] == iso3]
                else:
                    if len(input_datas) > 1:
                        continent_data = self._configuration["continents"][
                            file_name[6:8]
                        ]
                        continent_country = Country.get_country_info_from_iso3(iso3)[
                            "Region Name"
                        ]
                        if continent_country != continent_data:
                            continue
                    iso_geometry = global_boundaries[global_boundaries["ISO_3"] == iso3]
                    joined_df = sjoin(
                        input_data, iso_geometry, how="inner", predicate="intersects"
                    )
                    ids = joined_df[attribute]
                    data = input_data[input_data[attribute].isin(ids)]
                if len(data) == 0:
                    continue
                data.to_file(
                    join(country_folder, f"{file_name.split('.')[0]}_{iso3}.shp")
                )

            to_zip_file_list = list(Path(country_folder).iterdir())
            self._last_temp_files.extend(to_zip_file_list)
            output_zip = join(self._tempdir, f"{data_type}_{iso3.lower()}.zip")
            self._last_temp_files.append(output_zip)
            with zipfile.ZipFile(
                output_zip, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as zip_file:
                for file in to_zip_file_list:
                    zip_file.write(file, arcname=basename(file))
                zip_file.write(tech_doc, arcname=basename(tech_doc))

            # Dataset info
            dataset = Dataset(
                {
                    "name": f"{data_type.lower()}-{iso3.lower()}",
                    "title": f"{country_name}: {data_type}",
                    "notes": data_info["notes"],
                }
            )

            dataset.set_time_period_year_range(
                data_info["year_start"], data_info["year_end"]
            )
            dataset.add_tags(self._configuration["tags"])
            dataset.set_subnational(True)
            dataset.add_country_location(iso3)
            dataset["methodology"] = "Other"
            dataset["methodology_other"] = (
                f"See [technical documentation]({tech_doc_link}) for more information."
            )

            resource = Resource(
                {
                    "name": basename(output_zip),
                    "description": f"{data_type} zipped shapefile for {country_name}",
                }
            )
            resource.set_format("SHP")
            resource.set_file_to_upload(output_zip)
            dataset.add_update_resource(resource)

            resource = Resource(
                {
                    "name": basename(tech_doc),
                    "description": "Technical documentation",
                }
            )
            resource.set_format("pdf")
            resource.set_file_to_upload(tech_doc)
            dataset.add_update_resource(resource)

            datasets.append(dataset)

        return datasets
