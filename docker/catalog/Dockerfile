ARG ICEBERG_VERSION=1.10.1
FROM apache/iceberg-rest-fixture:${ICEBERG_VERSION}

ARG PG_JDBC_VERSION=42.7.7
ADD --chmod=644 \
    https://repo1.maven.org/maven2/org/postgresql/postgresql/${PG_JDBC_VERSION}/postgresql-${PG_JDBC_VERSION}.jar \
    /usr/lib/iceberg-rest/postgresql.jar

CMD ["java", "-cp", \
     "/usr/lib/iceberg-rest/iceberg-rest-adapter.jar:/usr/lib/iceberg-rest/postgresql.jar", \
     "org.apache.iceberg.rest.RESTCatalogServer"]