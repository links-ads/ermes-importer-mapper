FROM osgeo/gdal:ubuntu-small-3.6.3 AS base
ARG TARGET=dev

LABEL author="LINKS Foundation"
LABEL maintainer="LINKS Foundation"

WORKDIR /$PROJECT_NAME

# copy and install requirements
COPY requirements/ requirements/

RUN apt-get update -y
RUN apt-get install python3-pip software-properties-common -y
RUN add-apt-repository ppa:deadsnakes/ppa
RUN apt-get install python3.7 -y
RUN rm -rf /var/lib/apt/lists/*
RUN pip3 install --upgrade pip

RUN cd requirements && python3 -m pip install -r requirements.$TARGET.txt --no-cache-dir

# copy main library files
COPY pyproject.toml alembic.ini LICENSE README.md ./
COPY src/ src/
COPY migrations/ migrations/
RUN pip install -e .

# copy the main entrypoint and make it executable
COPY containers/importer/wait.py /
COPY containers/importer/docker-entrypoint.sh /
RUN mkdir temp
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
