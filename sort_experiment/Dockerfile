# Sort-granularity experiment image. Built on top of the csto2-runner base, which already provides
# the JDKs, Maven, the csto2 jars, and the testorder Surefire fork (with the method-order commit).
# Rebuild the base first (./run.sh --build ... in docker_template) so it clones the updated fork.
FROM csto2-runner

COPY MethodAllocListener.java /opt/csto/sortexp/MethodAllocListener.java
COPY gen_orders.py           /opt/csto/sortexp/gen_orders.py
COPY analyze.py              /opt/csto/sortexp/analyze.py
COPY entrypoint.sh           /usr/local/bin/sort-runner
RUN chmod +x /usr/local/bin/sort-runner

ENTRYPOINT ["sort-runner"]
