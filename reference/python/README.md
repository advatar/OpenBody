# OpenBody Python reference host/client

This package is the conformance-first reference implementation for OpenBody 0.1.

Run locally:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=reference/python uvicorn openbody_ref.host:app --reload
```

Then, from another process:

```python
from openbody_ref import OpenBodyClient

with OpenBodyClient("http://127.0.0.1:8000") as client:
    state = client.state()
    print(state["kind"], state["subject"])
```

The reference host exposes discovery/capabilities, current state, subsystem state, model/trajectory lookup, executable simulation, outcome recording, and calibration recording. Every protocol object is validated against `schemas/openbody.schema.json`; unsupported simulation requests fail closed with a protocol `Abstention` rather than a fabricated effect.

The bundled simulation provider is intentionally deterministic and narrow. It exists to test OpenBody interoperability, not to act as a clinical model. Production hosts should replace it with qualified model adapters while preserving the same protocol semantics.
