FROM gradle:9.5.0-jdk17
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv unzip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/mintpack
COPY service/requirements.txt ./requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
COPY --chown=gradle:gradle service ./service
COPY --chown=gradle:gradle android-template ./android-template
RUN mkdir -p /data && chown -R gradle:gradle /data /opt/mintpack
ENV PATH="/opt/venv/bin:${PATH}" \
    GRADLE_BIN=gradle \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    ANDROID_HOME=/opt/android-sdk \
    MINTPACK_DATA_DIR=/data \
    HOME=/home/gradle
USER gradle
EXPOSE 8000
CMD ["uvicorn", "service.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
