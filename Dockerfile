# Docker build instructions for scratchpurger
#
# This Dockerfile has four stages:
#
# base-image
#   Updates the base Python image with security patches and common system
#   packages. This image becomes the base of all other images.
# install-image
#   Installs third-party dependencies (requirements/main.txt)
#   into a virtual environment and then installs the app. This virtual
#   environment is the only thing copied into the runtime image.
# runtime-image
#   - Copies the virtual environment into place.
#   - Sets up the entrypoint.
#
# Note that the scratchpurger will typically run as root, because its job
#  is to use its privilege to clean up after people who did not clean up
#  after themselves.

FROM python:3.12.7-slim-bookworm as base-image

# Update system packages
COPY scripts/install-base-packages.sh .
RUN ./install-base-packages.sh && rm ./install-base-packages.sh

FROM base-image AS install-image

# Install system packages only needed for building dependencies.
COPY scripts/install-dependency-packages.sh .
RUN ./install-dependency-packages.sh

# Create a Python virtual environment.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV

# Make sure we use the virtualenv.
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Put the latest uv in the virtualenv.
RUN pip install --upgrade --no-cache-dir uv

# Install the app's Python runtime dependencies.
COPY requirements/main.txt ./requirements.txt
RUN uv pip install --quiet --no-cache-dir -r requirements.txt

# Install the Python package.
COPY . /workdir
WORKDIR /workdir
RUN uv pip install --no-cache-dir .

FROM base-image AS runtime-image

# Copy the virtualenv.
COPY --from=install-image /opt/venv /opt/venv

# Make sure we use the virtualenv.
ENV PATH="/opt/venv/bin:$PATH"

# Run something innocuous
CMD ["/bin/true"]
