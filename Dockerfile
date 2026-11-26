# The MCP server over stdio, built from this checkout:
#   docker build -t openbionews . && docker run -i --rm openbionews
# Set OPENBIONEWS_EDGAR_UA ("Your Name you@example.com") with -e for search_sec_filings.
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[mcp]"
ENTRYPOINT ["openbionews", "mcp"]
