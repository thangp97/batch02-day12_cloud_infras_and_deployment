# Stage 1: builder — cài dependencies vào /root/.local
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: runtime — chỉ copy packages đã cài + source code
FROM python:3.11-slim AS runtime
WORKDIR /app

# Copy installed packages từ builder (giảm image size)
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy source code (không copy __pycache__, .env, v.v.)
COPY common/          common/
COPY registry/        registry/
COPY customer_agent/  customer_agent/
COPY law_agent/       law_agent/
COPY tax_agent/       tax_agent/
COPY compliance_agent/ compliance_agent/
COPY start_all.sh     .

# Fix Windows CRLF → Unix LF và set executable
RUN sed -i 's/\r//' start_all.sh && chmod +x start_all.sh

# Chọn agent module khi build (override qua docker-compose environment)
ARG AGENT_MODULE=customer_agent
ENV AGENT_MODULE=${AGENT_MODULE}

EXPOSE 10000 10100 10101 10102 10103

CMD ["sh", "-c", "python -m ${AGENT_MODULE}"]
