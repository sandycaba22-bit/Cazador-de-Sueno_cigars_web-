# Paquete interno del buscador B2B (local / producción).
from b2b.cortafuegos_tests import bajo_test, instalar

if bajo_test():
    instalar()
