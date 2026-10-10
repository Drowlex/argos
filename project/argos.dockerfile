FROM python:3.10-slim

RUN mkdir -p /opt/dagster/dagster_home /opt/dagster/app

# Instalar herramientas del sistema, kubectl y Google Cloud SDK (GKE auth plugin)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    tzdata \
    && curl -fsSL "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/$(dpkg --print-architecture)/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y google-cloud-cli google-cloud-cli-gke-gcloud-auth-plugin \
    && rm -rf /var/lib/apt-get/lists/*

# Copy the application's requirements.txt and run pip to install all
# dependencies into the virtualenv.
ADD requirements.txt requirements.txt
RUN pip install -r requirements.txt


# RUN pip install dagit dagster-postgres dagster-aws

# Copy your code and workspace to /opt/dagster/app
# COPY ./src/main.py ./src/config/workspace.yaml /opt/dagster/app/
COPY ./src/ /opt/dagster/app/

ENV DAGSTER_HOME=/opt/dagster/dagster_home/

# Copy dagster instance YAML to $DAGSTER_HOME
COPY ./src/config/dagster.yaml /opt/dagster/dagster_home/

WORKDIR /opt/dagster/app

# Zona horaria
RUN ln -fs /usr/share/zoneinfo/America/Mexico_City /etc/localtime
RUN apt-get install -y tzdata
RUN dpkg-reconfigure --frontend noninteractive tzdata


EXPOSE 3000

#* PROD
# ENTRYPOINT ["dagit", "-f", "main.py", "-h", "0.0.0.0", "-p", "3000"]
#* TEST
ENTRYPOINT ["dagster", "dev", "-f", "main.py", "-h", "0.0.0.0", "-p", "3000"]