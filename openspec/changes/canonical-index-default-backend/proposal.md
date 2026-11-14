# Canonical index default backend

Make standard index use the proven canonical registry/archive/validation/publication
flow. Preserve the legacy writer only behind explicit --backend legacy and label
its executes as compatibility SQL discovery. Reuse existing pipeline code, avoid
basename repository collisions, and keep failures from changing publication visibility.
