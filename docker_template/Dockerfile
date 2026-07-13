FROM maven:3.9-eclipse-temurin-21

ARG TARGETARCH

# Install native compilation dependencies for Netty and general utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    ca-certificates \
    curl \
    procps \
    net-tools \
    iputils-ping \
    make \
    gcc \
    g++ \
    autoconf \
    automake \
    libtool \
    m4 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy deps directory to temp
COPY deps/ /tmp/deps/

# Setup JDKs (8, 11, 17) depending on target architecture
RUN set -eux; \
    ARCH=""; \
    if [ "$TARGETARCH" = "amd64" ]; then \
        ARCH="x64"; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        ARCH="aarch64"; \
    else \
        ARCH="$TARGETARCH"; \
    fi; \
    echo "Resolving JDKs for target architecture: $TARGETARCH (Adoptium arch: $ARCH)"; \
    mkdir -p /usr/lib/jvm; \
    \
    # Setup JDK 8 \
    mkdir -p /usr/lib/jvm/java-8-openjdk-amd64; \
    if [ "$TARGETARCH" = "amd64" ] && [ -f /tmp/deps/jdk-8u102.tgz ]; then \
        echo "Using local JDK 8 for amd64"; \
        tar -xzf /tmp/deps/jdk-8u102.tgz -C /usr/lib/jvm/java-8-openjdk-amd64 --strip-components=1; \
    else \
        echo "Downloading JDK 8 from Adoptium for $ARCH"; \
        curl -L "https://api.adoptium.net/v3/binary/latest/8/ga/linux/${ARCH}/jdk/hotspot/normal/eclipse" -o /tmp/jdk8.tar.gz; \
        tar -xzf /tmp/jdk8.tar.gz -C /usr/lib/jvm/java-8-openjdk-amd64 --strip-components=1; \
        rm /tmp/jdk8.tar.gz; \
    fi; \
    \
    # Setup JDK 11 \
    mkdir -p /usr/lib/jvm/java-11-openjdk-amd64; \
    if [ "$TARGETARCH" = "amd64" ] && [ -f /tmp/deps/openjdk-11.0.2_linux-x64_bin.tar.gz ]; then \
        echo "Using local JDK 11 for amd64"; \
        tar -xzf /tmp/deps/openjdk-11.0.2_linux-x64_bin.tar.gz -C /usr/lib/jvm/java-11-openjdk-amd64 --strip-components=1; \
    else \
        echo "Downloading JDK 11 from Adoptium for $ARCH"; \
        curl -L "https://api.adoptium.net/v3/binary/latest/11/ga/linux/${ARCH}/jdk/hotspot/normal/eclipse" -o /tmp/jdk11.tar.gz; \
        tar -xzf /tmp/jdk11.tar.gz -C /usr/lib/jvm/java-11-openjdk-amd64 --strip-components=1; \
        rm /tmp/jdk11.tar.gz; \
    fi; \
    \
    # Setup JDK 17 \
    mkdir -p /usr/lib/jvm/java-17-openjdk-amd64; \
    if [ "$TARGETARCH" = "amd64" ] && [ -f /tmp/deps/openjdk-17.0.2_linux-x64_bin.tar.gz ]; then \
        echo "Using local JDK 17 for amd64"; \
        tar -xzf /tmp/deps/openjdk-17.0.2_linux-x64_bin.tar.gz -C /usr/lib/jvm/java-17-openjdk-amd64 --strip-components=1; \
    else \
        echo "Downloading JDK 17 from Adoptium for $ARCH"; \
        curl -L "https://api.adoptium.net/v3/binary/latest/17/ga/linux/${ARCH}/jdk/hotspot/normal/eclipse" -o /tmp/jdk17.tar.gz; \
        tar -xzf /tmp/jdk17.tar.gz -C /usr/lib/jvm/java-17-openjdk-amd64 --strip-components=1; \
        rm /tmp/jdk17.tar.gz; \
    fi; \
    \
    # Clean up temp deps \
    rm -rf /tmp/deps

# Sync modern CA certificates to the manually installed JDKs to prevent SSL/TLS connection failures
RUN cp /opt/java/openjdk/lib/security/cacerts /usr/lib/jvm/java-8-openjdk-amd64/jre/lib/security/cacerts \
    && cp /opt/java/openjdk/lib/security/cacerts /usr/lib/jvm/java-11-openjdk-amd64/lib/security/cacerts \
    && cp /opt/java/openjdk/lib/security/cacerts /usr/lib/jvm/java-17-openjdk-amd64/lib/security/cacerts

# Install the testorder fork. Build the FULL reactor (not just common+plugin) so ALL
# Surefire providers land in ~/.m2 -- surefire-junit-platform (JUnit 5), surefire-junit4/47
# (JUnit 4), surefire-testng. The M8 plugin resolves the matching provider at runtime, and
# a JUnit-5 project (e.g. paimon) fails to even start Surefire without it. Mirrors the prior
# researcher's setup (tool/helpers.sh: `mvn install -DskipTests -Drat.skip -Denforcer.skip`).
RUN git clone --branch modifiedRunOrder-ext https://github.com/Archonic944/maven-surefire.git /opt/maven-surefire \
    && cd /opt/maven-surefire \
    && mvn install -DskipTests -Drat.skip -Denforcer.skip \
    && cd surefire-changing-maven-extension \
    && mvn clean package -DskipTests \
    && mkdir -p /opt/csto \
    && cp target/surefire-changing-maven-extension-1.0-SNAPSHOT.jar /opt/csto/surefire-changing-maven-extension.jar \
    && rm -rf /opt/maven-surefire

# Copy built CSTO jars and configs
COPY deps/csto2.jar /opt/csto/csto2.jar
COPY deps/csto2-agent.jar /opt/csto/csto2-agent.jar
COPY configs /opt/csto/configs

# Setup entrypoint
COPY entrypoint.sh /usr/local/bin/repo-runner
RUN chmod +x /usr/local/bin/repo-runner

ENTRYPOINT ["repo-runner"]
