FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/
COPY templates ./templates 

ENV CHROMA_DIR=/chroma
VOLUME ["/chroma"]

EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-k", "gthread", "-t", "120", "-b", "0.0.0.0:8000", "app:app"]
