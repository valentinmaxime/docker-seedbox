FROM python:3.12-slim
WORKDIR /app
COPY app_docker.py /app/app_docker.py
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
ENV PSUTIL_PROCFS_PATH=/hostproc
CMD ["python","/app/app_docker.py"]