"""Atalho de compatibilidade: `import pyneb` agora devolve o pacote `nebula`."""
import sys

import nebula

sys.modules[__name__] = nebula
