FROM apache/spark:4.0.5-scala2.13-java17-python3-ubuntu

USER root
#next command run as root
# install python3.12 for executer to fit with image Airflow 3.4.0-python3.12
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3.12 \
 && rm -rf /var/lib/apt/lists/*

#install Jar Iceberg for Spark 4.0 (Scala 2.13) + S3FileIO
ARG ICEBERG_VERSION=1.10.1
ARG MAVEN=https://repo1.maven.org/maven2/org/apache/iceberg
ADD --chmod=644 ${MAVEN}/iceberg-spark-runtime-4.0_2.13/${ICEBERG_VERSION}/iceberg-spark-runtime-4.0_2.13-${ICEBERG_VERSION}.jar /opt/spark/jars/
ADD --chmod=644 ${MAVEN}/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar /opt/spark/jars/

# eventlog folder, mount volume with Airflow
RUN mkdir -p /opt/spark/events && chmod 777 /opt/spark/events

USER spark
#switch back to spark
