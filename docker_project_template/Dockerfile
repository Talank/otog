FROM ubuntu:20.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install necessary packages
RUN apt-get update && \
    apt-get install -y git python3 python3-pip make autoconf automake libtool curl g++ wget unzip openjdk-8-jdk openjdk-11-jdk openjdk-17-jdk bc sed && \
    apt-get clean

# # Install OpenJDK 11 and Maven
# RUN apt-get update && \
#     apt-get install -y openjdk-11-jdk maven && \
#     apt-get clean

# RUN echo 'export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64/' >> ~/.bashrc
# ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
# ENV PATH=$JAVA_HOME/bin:$PATH

# Set the working directory
WORKDIR /app

# Copy all scripts into the container
COPY . .

# make dirs /app/scripts/runs_n25, /app/scripts/test_list, /app/scripts/dataset, /app/scripts/random_test_orders_n25
RUN mkdir -p /app/scripts/runs_n25 /app/scripts/test_list /app/scripts/dataset /app/scripts/random_test_orders_n25

RUN chmod -R +rwx /app/scripts
RUN chmod -R +rwx /app

# Install any Python dependencies if needed
# RUN pip3 install -r requirements.txt

# Set the working directory to the scripts directory
WORKDIR /app/scripts

# Run the script with the provided ID
CMD ["bash", "-c", "./run.sh $ID"]
