# Single image used for both the MCP server and the web chatbot.
# docker-compose overrides CMD per service.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer-cache friendly)
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "mcp[cli]>=1.6.0" \
    "anthropic>=0.45.0" \
    "flask>=3.1.0" \
    "pytz>=2024.1" \
    "python-dotenv>=1.0.0"

# Copy source
COPY server.py webapp.py ./
COPY templates/ templates/

# Default: run the MCP server in HTTP mode
# (docker-compose overrides this for the chatbot service)
EXPOSE 8000
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000

CMD ["python", "server.py", "--transport", "http"]
