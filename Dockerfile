FROM python:3.12-slim

# Install Terraform
RUN apt-get update && apt-get install -y --no-install-recommends wget unzip && \
    wget -q https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip && \
    unzip terraform_1.7.0_linux_amd64.zip -d /usr/local/bin/ && \
    rm terraform_1.7.0_linux_amd64.zip

# Install Azure CLI
RUN apt-get install -y --no-install-recommends curl gnupg lsb-release && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agencyops/ agencyops/
COPY terraform/workloads/ terraform/workloads/

ENV AGENCYOPS_DATA_DIR=/data
ENV AGENCYOPS_TERRAFORM_DIR=/app/terraform/workloads

EXPOSE 8000

CMD ["python", "-m", "agencyops"]
