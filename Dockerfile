# NthLayer CLI Docker Image
# Reliability at build time, not incident time
#
# Usage:
#   docker run ghcr.io/rsionnach/nthlayer plan service.yaml
#   docker run -v $(pwd):/workspace ghcr.io/rsionnach/nthlayer validate-slo service.yaml
#
# Note: Image is ~800MB due to ML/AI dependencies (scipy, langgraph).
# A slim "cli-only" image may be provided in future versions.

FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install nthlayer
RUN pip install --no-cache-dir nthlayer

# Production image
FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/rsionnach/nthlayer"
LABEL org.opencontainers.image.description="NthLayer - Reliability validation for CI/CD pipelines"
LABEL org.opencontainers.image.licenses="MIT"

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user for security
RUN useradd -m -s /bin/bash nthlayer

# Switch to non-root user
USER nthlayer

# Set working directory (mount point for service files)
WORKDIR /workspace

# Default entrypoint is nthlayer CLI
ENTRYPOINT ["nthlayer"]

# Default command shows help
CMD ["--help"]
