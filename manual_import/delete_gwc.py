import os
import re
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

load_dotenv()

environment = 'test'
for i in range(100):
    ans = requests.get(f'{os.getenv("GEOSERVER_URL")}/geoserver/gwc/service/wmts?REQUEST=GetCapabilities').text
    z = re.findall("LayerInfoImpl-.[^\s]*", ans)
    if len(z) == 1:
        path = f'/data/data-{environment}/gsvdata/gwc-layers/'
        filepath = f'{path}{z[0].replace(":","_")}.xml'

        tree = ET.parse(filepath)
        root = tree.getroot()
        layer = root.findall('name')[0].text

        url = f'{os.getenv("GEOSERVER_URL")}/geoserver/gwc/rest/layers/{layer}'

        payload={}
        headers = {
        'Authorization': 'Basic '
        }

        response = requests.request("DELETE", url, headers=headers, data=payload)

        print(response.text)
    else:
        break
