FROM python:3.14-slim

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY src ./src
COPY *.py ./

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Railway provides PORT at runtime; Streamlit must bind to all interfaces.
EXPOSE 8501
CMD ["sh", "-c", "streamlit run app_streamlit.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true"]
