Your README file provides a comprehensive overview of the ERMES Importer and Mapper. Here are a few minor improvements for clarity and formatting:

# ERMES IMPORTER and MAPPER #

ERMES Importer and Mapper are integral components of the ERMES infrastructure designed to ingest and serve maps as layers through OGC services. The system comprises two main modules:

- **IMPORTER**: Reads notifications from a message broker (currently RabbitMQ), retrieves data from a Data Lake (implemented in a CKAN component), and publishes geospatial data (NetCDF, GeoJSON, GeoTIFF, Shapefile) into the Mapper module.

  Supported File Formats:
  - GeoTiff (.tif, .tiff)
  - GeoJSON (.json, .geojson)
  - Shapefiles (.zip file with all the .shp & Co. files)
  - KML (.kml)
  - NetCDF (.nc, .ncml)

- **MAPPER**: Serves maps as layers through OGC services standards. Implements a customized Geoserver version with plugins.

This README document outlines the steps required to get your application up and running.

## Containers Overview

When deploying the service, Docker Compose will build the following containers:

- **geoserver**: Uses the `kartoza/geoserver` docker image, configured through environment variables in the docker-compose file. Supports extensions, with the current extension being the "netcdf-plugin" for NetCDF file format support.

- **database**: PostGIS database where records are saved. Utilizes a "geoserver_resource" table to store information needed to retrieve actual files.

- **importer**: Listens on a RabbitMQ queue for notifications from the Data Lake, retrieves resources, saves them, and interfaces with Geoserver to publish or remove them. Implements policies to remove old data after a configurable time or when a certain number of resources are present.

- **webserver**: Exposes APIs to explore data and extract information. Endpoints include:
  - `GET /resources`: Returns the list of all published resources, optionally filtered by "datatype_ids" and "resource_id" (params in query string).
  - `GET /layers`: Returns the list of Geoserver layer names based on specified requirements (bounding box, start date, end date).
  - `GET /time_series`: Retrieves the time series of the requested attribute for layers denoted by the specified datatype_id, at the "point" position.

## Setup

### ENVIRONMENT vars

Create `env/prod.env` file copying from [this template file](env-example/template.env.example). In the following the explanation of the different sections:

- IMPORTER SETTINGS:
Limit the quantity of active layers by configuring the following:
  - `delete_after_days`: Purges the layer after #days from the importing.
  - `delete_after_count`: Purges the layer after #layer of the same datatype uploaded.
  
  To gain more granularity, consider setting up settings for each datatype id in the `layer_settings` table in the DB.

- BROKER SETTINGS: Set the connection params to the message broker for notifications on new data to publish. The notification is expected with the specified format
```json
{
  "metadata_id": ckan_metadata_id,
  "id": ckan_file_id,
  "datatype_id": datatype_id,
  "type": ["delete", "update", "create"],
  "creation_date": creation_date,
  "start_date": file_validity_date_start,
  "end_date": file_validity_date_end,
  "geometry": WKT_geometry,
  "request_code": request_code_associated_to_a_map_request,
  "url": url_to_download_the_file
}
```

- OAUTH SETTINGS:
Data Lake CKAN implementation uses Oauth2 for authentication and authorization. This is required to download non-public files from the Data Lake.

- DB SETTINGS: The database is shared among Geoserver and Importer, implemented in PostGIS.

- GEOSERVER SETTINGS: Settings for the Geoserver instance. Currently supports just one workspace.

## Deployment

The repository is production-ready and can be deployed following these steps:

1. [Install Docker Compose](https://docs.docker.com/compose/install/)
2. Clone this repository
3. Create `env/prod.env` file copying from [this template file](env-example/template.env.example) and filling fields with proper values (view previous Section)
4. Run command `sh manage.sh build prod` to build docker images
5. Run command `sh manage.sh run prod -d` to run containers and detach them from the console
6. Visit the running Geoserver at `http://localhost:8600/geoserver` with `admin:geoserver` credentials and change them with the ones set in the .env file
7. The webserver is available at `http://localhost:7500/docs`

Customizations may slightly change the deployment; it's recommended to keep the [manage.sh](manage.sh) script updated.

Specific settings for each layer can be adjusted from the DB table `layer-settings`.

### STYLES

Styles are used to control the appearance of geospatial data. They need to be set up through the [GUI](https://docs.geoserver.org/latest/en/user/styling/webadmin/index.html). Styles used are uploaded in `importer/styles`.

### DB Migrations

The repository comes with a [migrations](migrations) folder included. Use `sh manage.sh db dev|prod` to obtain local migrations corresponding to changes made to the db models.

### Manual File Import

For manual file imports regarding a specific datatype_id, use the `manual_import` script in the `manual_import` folder. Follow the provided steps in the script for setup and execution.

### Known Issues and Notes

- **Bounding Box Filtering**: When searching layers or getting time series through APIs, bounding box filtering is applied on the geometry saved in the "geoserver_resource" table of the PostGIS database. If the declared geometry does not coincide with the actual geometry of the resource, the result may get filtered out. Trust that the source that uploaded the resource compiled the geometry field accurately.

- **Tile Layers Error**: If the Tile Layers page cannot be loaded due to an error, follow the provided steps to resolve the issue:

  * Go to `<geoserver_url>/geoserver/gwc/service/wmts?REQUEST=GetCapabilities`, if Tile Layers is broken, you should see an error e.g. `400: Could not locate a layer or layer group with id LayerInfoImpl-58993b92:17f078c520d:7635 within GeoServer configuration, the GWC configuration seems to be out of synch`
  , keep note of the layer name.
  * Go to <data_dir>/gsvdata/gwc-layers and open the xml with the same name of the broken layer, keep notes of the original name of the layer in GeoServerTileLayer[name] (e.g. `ermes:33203_d2m_33002_89e73b8a-f72e-4787-b9fd-ec56b8fc3308`)
  * Use the rest API DELETE <geoserver_url>/geoserver/gwc/rest/layers/<layer_name> to successfully remove the layer
  * repeat until the url at the first bullet works

