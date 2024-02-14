FROM python:3.12.2

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-server-dev-all \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --trusted-host=pypi.org --trusted-host=files.pythonhosted.org --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

# If running behind a proxy like Nginx or Traefik add --proxy-headers
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--proxy-headers"]