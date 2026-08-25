# Mechanism 5: SnakeYAML shared first-use initialization.
# Many small tests initialize shared YAML parser/emitter paths; the large repeated consumers
# are faster when they run after 300+ other classes (5.72% whole-suite, 18/20 pairs).
# Whole-suite arms move the seven consumers with documented repeatable savings (mechanisms.md
# section 5.1 table) to the front (cold) vs the back (warm), keeping their internal order.
# The pair is a PROXY (the mechanism is many-to-one): one cheap emitter-path test before the
# top consumer PyEmitterTest; a weak pair effect next to a strong whole-suite effect is the
# expected signature of this mechanism.
MECHANISM="sy-init"
NATURAL="sy.natural"
TRACK="org.pyyaml.PyEmitterTest org.yaml.snakeyaml.issues.issue102.BigDataLoadTest"
PAIR_FAST="org.yaml.snakeyaml.emitter.EmitterTest org.pyyaml.PyEmitterTest"
PAIR_SLOW="org.pyyaml.PyEmitterTest org.yaml.snakeyaml.emitter.EmitterTest"
SY_HEAVY="org.pyyaml.PyEmitterTest,org.yaml.snakeyaml.issues.issue102.BigDataLoadTest,org.yaml.snakeyaml.issues.issue377.ReferencesTest,org.yaml.snakeyaml.issues.issue148.PrintableUnicodeTest,org.yaml.snakeyaml.issues.issue1100.JacksonTest,org.yaml.snakeyaml.emitter.template.VelocityTest,org.pyyaml.PyStructureTest"
WHOLE_FAST_MOVES="back:${SY_HEAVY}"
WHOLE_SLOW_MOVES="front:${SY_HEAVY}"
