FROM python:3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8084
COPY . .
CMD [ "gunicorn", "--bind", "0.0.0.0:8088", "main:app" ]
