# Dockerfile — Aria Code 本地实例
# 用于 docker compose up aria-local

FROM python:3.11-slim

WORKDIR /aria

# System deps for PDF/Excel parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt websockets

COPY . .
# Installs the console scripts (aria-code, aria-code-mcp) and puts aria_code on
# the path, which every service module now imports from.
RUN pip install --no-cache-dir --no-deps -e .

# Config volume mount point
RUN mkdir -p /root/.aria

ENV PYTHONUNBUFFERED=1
# The package moved to a src layout. Both roots go on the path for the same
# reason pyproject's pytest config lists them: the package imports itself by
# bare names (`from runtime import ...`) as well as `aria_code.*`.
ENV PYTHONPATH=/aria/src:/aria/src/aria_code

CMD ["python3", "src/aria_code/aria_cli.py"]
