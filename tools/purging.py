import os

lst = []


for f in lst:
    filepath = f"/opt/geoserver/data_dir/{f}"
    if os.path.exists(filepath):
        os.remove(filepath)
        print("deleted")
