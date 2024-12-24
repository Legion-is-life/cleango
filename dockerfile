FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create config directory and set permissions
RUN mkdir -p /config && \
    chown -R nobody:nogroup /config && \
    chmod 777 /config

# Create volume for persistent database storage
VOLUME /config

# Create a script to initialize the container
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Switch to non-root user
USER nobody

# Use the entrypoint script
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Expose port
EXPOSE 5000

# Run the application with proper initialization
CMD ["sh", "-c", "python app.py"]
LABEL org.opencontainers.image.source=https://github.com/Legion-is-life/cleango
LABEL org.opencontainers.image.description="CleanGo"
LABEL org.opencontainers.image.licenses=Apache2.0