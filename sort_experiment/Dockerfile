# Sort-granularity experiment image. Built on top of the csto2-runner base, which already provides
# the JDKs, Maven, the csto2 jars, and the testorder Surefire fork (with the method-order commit).
# Rebuild the base first (./run.sh --build ... in docker_template) so it clones the updated fork.
FROM csto2-runner

# The base (maven:eclipse-temurin) has no Python; the experiment scripts need it.
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*

COPY MethodAllocListener.java /opt/csto/sortexp/MethodAllocListener.java
COPY gen_orders.py           /opt/csto/sortexp/gen_orders.py
COPY analyze.py              /opt/csto/sortexp/analyze.py
COPY entrypoint.sh           /usr/local/bin/sort-runner
RUN chmod +x /usr/local/bin/sort-runner

ENTRYPOINT ["sort-runner"]
