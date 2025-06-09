FROM python:3.11-slim

# Install system dependencies for OpenCV
RUN apt-get update && \
    apt-get install -y \
        iputils-ping \
        zlib1g-dev \
        build-essential \
        cmake \
        git \
        pkg-config \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY app /app
RUN python -m pip install /app --extra-index-url https://www.piwheels.org/simple && \
    python -m pip install fastapi uvicorn requests apriltag && \
    python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless && \
    python -m pip install opencv-python==4.10.0.84 --extra-index-url https://www.piwheels.org/simple

EXPOSE 8000/tcp

# application version.  This should match the register_service file's version
LABEL version="0.0.1"

# Permissions for the container
# "Binds" section maps the host PC directories to the application directories
LABEL permissions='\
{\
  "ExposedPorts": {\
    "8000/tcp": {}\
  },\
  "HostConfig": {\
    "NetworkMode": "host",\
    "Binds":[\
      "/usr/blueos/extensions/precision-landing/settings:/app/settings",\
      "/usr/blueos/extensions/precision-landing/logs:/app/logs"\
    ],\
    "ExtraHosts": ["host.docker.internal:host-gateway"],\
    "CapAdd": ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"],\
    "Privileged": false,\
    "PortBindings": {\
      "8000/tcp": [\
        {\
          "HostPort": ""\
        }\
      ]\
    }\
  }\
}'

LABEL authors='[\
    {\
        "name": "Randy Mackay",\
        "email": "rmackay9@yahoo.com"\
    }\
]'

LABEL company='{\
    "about": "ArduPilot",\
    "name": "ArduPilot",\
    "email": "rmackay9@yahoo.com"\
}'

LABEL readme='https://github.com/rmackay9/blueos-precision-landing/blob/main/README.md'
LABEL type="device-integration"
LABEL tags='[\
  "data-collection"\
]'
LABEL links='{\
        "source": "https://github.com/rmackay9/blueos-precision-landing"\
    }'
LABEL requirements="core >= 1.1"

ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
