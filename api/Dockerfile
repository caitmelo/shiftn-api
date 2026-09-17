FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements.txt
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r api/requirements.txt
COPY api api
COPY dist dist
RUN useradd --create-home appuser && mkdir -p /app/models && chown -R appuser:appuser /app
USER appuser
ENV WATERMARK_ENABLED=1
EXPOSE 8080
CMD ["uvicorn","api.app:create_app","--factory","--host","0.0.0.0","--port","8080","--workers","1"]
