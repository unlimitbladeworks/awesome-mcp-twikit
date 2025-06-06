# Generated by https://smithery.ai. See: https://smithery.ai/docs/config#dockerfile
# Use a Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy the project files
COPY . /app

# Install the project's dependencies
RUN pip install --no-cache-dir hatchling
RUN pip install --no-cache-dir .

# Set environment variables for Twitter authentication
# These should be provided at runtime for security purposes
ENV TWITTER_USERNAME="@example"
ENV TWITTER_EMAIL="me@example.com"
ENV TWITTER_PASSWORD="secret"
ENV TWITTER_2FA="2fa"
ENV ENABLE_PROXY="true"
ENV PROXY="proxy"

# Set the entrypoint command to run the MCP server
ENTRYPOINT ["mcp-twikit-tools"]
