FROM python:3.12-slim

WORKDIR /app

# مطلوبة لبناء بعض اعتماديات Twisted/cryptography عند عدم توفر wheel جاهز
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# هذا Worker وليس خدمة ويب — لا يستمع على أي منفذ، يعمل عبر Twisted reactor
# باستمرار حتى يُوقَف يدويًا أو يُعاد نشره
CMD ["python", "main.py"]
