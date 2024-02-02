# ERMES Importer and Mapper

ERMES Importer and Mapper are integral components of the ERMES infrastructure designed to ingest and serve maps as layers through OGC services. The system comprises two main modules:

- **Importer**: Reads notifications from a message broker (currently RabbitMQ), retrieves data from a Data Lake (implemented in a CKAN component), and publishes geospatial data (NetCDF, GeoJSON, GeoTIFF, Shapefile) into the Mapper module.

  Supported File Formats:
  - GeoTiff (.tif, .tiff)
  - GeoJSON (.json, .geojson)
  - Shapefiles (.zip file with all the .shp & Co. files)
  - KML (.kml)
  - NetCDF (.nc, .ncml)

- **Mapper**: Serves maps as layers through OGC services standards. Implements a customized Geoserver version with plugins.

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

## Installation

### Environment Variables

Create `env/prod.env` or `env/dev.env` copying from [this template file](envs/template.env.example):

- **Importer settings**:
Limit the number of active layers by configuring the following:
  - `delete_after_days`: Purges the layer after # days from the importing.
  - `delete_after_count`: Purges the layer after # layers of the same datatype uploaded.
  
  To gain more granularity, consider setting up settings for each datatype ID in the `layer_settings` table in the DB.

- **Broker settings**: Set the connection params to the message broker for notifications on new data to publish. The notification is expected with the specified format:

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

- **Oauth settings**:
The Data Lake implementation (CKAN) uses Oauth2 for authentication and authorization.
This is required to download non-public files from the Data Lake.

- **Database settings**:
The database is shared among Geoserver and Importer, implemented in PostGIS.

-**Geoserver settings**:
Settings for the Geoserver instance. Currently supports just one workspace.

## Deployment

The repository can be deployed following these steps:

1. [Install Docker Compose](https://docs.docker.com/compose/install/)
2. Clone this repository
3. Create the required environment file, following the templates.
4. Use the provided makefile to configure, build, and run the solution:
    - Use `make config TARGET=dev|prod` to double check the resulting configuration
    - Use `make build TARGET=dev|prod [ARGS=...]` to build the containers
    - Use `make up TARGET=dev [ARGS=...]` to run the solution
    - E.g., with `make up TARGET=prod ARGS="--build -d"` the solution will build and start in detached mode.

6. Visit the running Geoserver at `http://localhost:<chosen_port>/geoserver` with `admin:geoserver` credentials and change them with the ones set in the `.env` file
7. The webserver documentation is available at `http://localhost:<chosen_port>/docs`

8. **Optional**: Specific settings for each layer can be adjusted from the DB table `layer-settings`.

> **Note**
> 
> For a clean start, use the command `make down TARGET=dev ARGS="-v --remove-orphans"`

### Styles

Styles are used to control the appearance of geospatial data. They need to be set up through the [GUI](https://docs.geoserver.org/latest/en/user/styling/webadmin/index.html). Styles used are uploaded in `importer/styles`.

### Migrations

The repository comes with a [migrations](migrations) folder included. These can be generated using `alembic`.

### Manual Imports

For manual file imports regarding a specific `datatype_id`, use the `notifier.py` script in the `tools` directory. Follow the provided steps in the script for setup and execution.

### Known Issues and Notes

- **Bounding Box Filtering**: When searching layers or getting time series through APIs, bounding box filtering is applied on the geometry saved in the "geoserver_resource" table of the PostGIS database. If the declared geometry does not coincide with the actual geometry of the resource, the result may get filtered out. Trust that the source that uploaded the resource compiled the geometry field accurately.

- **Tile Layers Error**: If the Tile Layers page cannot be loaded due to an error, follow the provided steps to resolve the issue:

  * Go to `<geoserver_url>/geoserver/gwc/service/wmts?REQUEST=GetCapabilities`, if Tile Layers is broken, you should see an error e.g. `400: Could not locate a layer or layer group with id LayerInfoImpl-58993b92:17f078c520d:7635 within GeoServer configuration, the GWC configuration seems to be out of synch`
  , keep note of the layer name.
  * Go to <data_dir>/gsvdata/gwc-layers and open the xml with the same name of the broken layer, keep notes of the original name of the layer in GeoServerTileLayer[name] (e.g. `ermes:33203_d2m_33002_89e73b8a-f72e-4787-b9fd-ec56b8fc3308`)
  * Use the rest API DELETE <geoserver_url>/geoserver/gwc/rest/layers/<layer_name> to successfully remove the layer
  * repeat until the url at the first bullet works

