FROM python:3.13-slim

WORKDIR /app

COPY PrtMcpCommon /app/PrtMcpCommon
COPY PrtDatabaseMcp /app/PrtDatabaseMcp

RUN pip install --no-cache-dir -e /app/PrtMcpCommon -e /app/PrtDatabaseMcp

ENV PRT_MCP_TRANSPORT=http
ENV PRT_MCP_HOST=0.0.0.0
ENV PRT_MCP_PORT=8080
ENV PRT_MCP_HTTP_PATH=/mcp
ENV PRT_MCP_STATELESS_HTTP=true

EXPOSE 8080

CMD ["python", "-m", "prt_database_mcp", "--transport", "http"]
