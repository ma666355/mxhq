FROM python:3.12-slim

LABEL org.opencontainers.image.title="StockRadar"
LABEL org.opencontainers.image.description="A-Share Quantitative Stock Screening System"
LABEL org.opencontainers.image.source="https://github.com/ma666355/stockradar"

WORKDIR /app

# 安装系统依赖（baostock 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 数据目录挂载点
VOLUME ["/app/data"]

# 首次使用需回填数据，日常运行去掉 --backfill
ENTRYPOINT ["python", "main.py"]
CMD ["--backfill"]
