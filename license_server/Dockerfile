FROM python:3.12-slim
WORKDIR /app
COPY license_server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY license_server /app/license_server
RUN mkdir -p /data && chown -R 10001:10001 /data /app
USER 10001:10001
ENV LICENSE_DB=/data/licenses.sqlite3
EXPOSE 8088
CMD ["gunicorn", "license_server.app:production_app()", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8088"]
