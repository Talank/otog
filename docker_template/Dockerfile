FROM maven:3.9-eclipse-temurin-21

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

# Create JVM directory
RUN mkdir -p /usr/lib/jvm

# Copy and unpack JDK 8
COPY deps/jdk-8u102.tgz /tmp/
RUN tar -xzf /tmp/jdk-8u102.tgz -C /usr/lib/jvm/ \
    && ln -s /usr/lib/jvm/jdk1.8.0_102 /usr/lib/jvm/java-8-openjdk-amd64 \
    && rm /tmp/jdk-8u102.tgz

# Copy and unpack JDK 11
COPY deps/openjdk-11.0.2_linux-x64_bin.tar.gz /tmp/
RUN tar -xzf /tmp/openjdk-11.0.2_linux-x64_bin.tar.gz -C /usr/lib/jvm/ \
    && ln -s /usr/lib/jvm/jdk-11.0.2 /usr/lib/jvm/java-11-openjdk-amd64 \
    && rm /tmp/openjdk-11.0.2_linux-x64_bin.tar.gz

# Copy and unpack JDK 17
COPY deps/openjdk-17.0.2_linux-x64_bin.tar.gz /tmp/
RUN tar -xzf /tmp/openjdk-17.0.2_linux-x64_bin.tar.gz -C /usr/lib/jvm/ \
    && ln -s /usr/lib/jvm/jdk-17.0.2 /usr/lib/jvm/java-17-openjdk-amd64 \
    && rm /tmp/openjdk-17.0.2_linux-x64_bin.tar.gz

# Clone, compile, and install the custom maven surefire testorder fork (only the extension submodule)
RUN git clone https://github.com/TestingResearchIllinois/maven-surefire.git /opt/maven-surefire \
    && cd /opt/maven-surefire/surefire-changing-maven-extension \
    && sed -i 's/<source>1.7<\/source>/<source>1.8<\/source>/g' pom.xml \
    && sed -i 's/<target>1.7<\/target>/<target>1.8<\/target>/g' pom.xml \
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
