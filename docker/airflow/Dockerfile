FROM eclipse-temurin:17-jre AS jre

FROM apache/airflow:3.4.0-python3.12
#java 17 for spark driver
COPY --from=jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libatomic1 \
 && rm -rf /var/lib/apt/lists/*
#install requirements and python libs
USER airflow
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==3.4.0" -r /requirements.txt \
 && python -m playwright install chromium \
 && python -c "import sys; print(sys.executable)" > /tmp/pw_python \
 && python -c "import os, playwright; print(os.path.dirname(os.path.dirname(playwright.__file__)))" > /tmp/pw_site

#install jar iceberg into pyspark driver
ARG ICEBERG_VERSION=1.10.1
ARG MAVEN=https://repo1.maven.org/maven2/org/apache/iceberg
RUN JARS=$(python -c "import os, pyspark; print(os.path.join(os.path.dirname(pyspark.__file__), 'jars'))") \
 && curl -fsSL -o "$JARS/iceberg-spark-runtime-4.0_2.13-${ICEBERG_VERSION}.jar" \
      "${MAVEN}/iceberg-spark-runtime-4.0_2.13/${ICEBERG_VERSION}/iceberg-spark-runtime-4.0_2.13-${ICEBERG_VERSION}.jar" \
 && curl -fsSL -o "$JARS/iceberg-aws-bundle-${ICEBERG_VERSION}.jar" \
      "${MAVEN}/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar"

#switch to root to install chromium dependencies
USER root
RUN PYTHONPATH="$(cat /tmp/pw_site)" "$(cat /tmp/pw_python)" -m playwright install-deps chromium \
 && rm -rf /var/lib/apt/lists/* /tmp/pw_python /tmp/pw_site \
 && mkdir -p /opt/spark/conf /opt/spark/events && chmod 777 /opt/spark/events

USER airflow
ENV SPARK_CONF_DIR=/opt/spark/conf