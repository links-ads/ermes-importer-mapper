import argparse
import os
import re
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

if __name__ == "__main__":
    """
    Utility script to delete GeoWebCache layers from GeoServer.
    """
    load_dotenv()
    parser = argparse.ArgumentParser(description="Delete all layers from GeoWebCache")
    parser.add_argument("--environment", "-e", type=str, help="Environment to delete layers from", default="test")
    parser.add_argument("--limit", "-l", type=int, help="Limit of layers to delete", default=100)
    args = parser.parse_args()
    environment = args.environment

    for i in range(args.limit):
        ans = requests.get(f'{os.getenv("GEOSERVER_URL")}/geoserver/gwc/service/wmts?REQUEST=GetCapabilities').text
        z = re.findall("LayerInfoImpl-.[^\s]*", ans)
        if len(z) == 1:
            path = f"/data/data-{environment}/gsvdata/gwc-layers/"
            filepath = f'{path}{z[0].replace(":","_")}.xml'

            tree = ET.parse(filepath)
            root = tree.getroot()
            layer = root.findall("name")[0].text

            url = f'{os.getenv("GEOSERVER_URL")}/geoserver/gwc/rest/layers/{layer}'

            payload = {}
            headers = {"Authorization": "Basic"}

            response = requests.request("DELETE", url, headers=headers, data=payload)
            print(response.text)
        else:
            break
