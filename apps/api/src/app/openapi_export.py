"""Write the OpenAPI schema to disk.

The schema is a committed artifact, not something generated at runtime, because
it is the contract the frontend's TypeScript client is generated from. CI
regenerates it and fails if the committed copy has drifted, which makes it
impossible to change a response model without the frontend types following.

Output is deterministic — sorted keys, fixed indentation, trailing newline — so
an unchanged API produces a byte-identical file and the drift check has no false
positives.
"""

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def build_schema() -> dict[str, object]:
    # Explicitly non-production: production hides the schema endpoint, and we
    # want the export to behave identically wherever it runs.
    app = create_app(Settings(environment="local"))
    return app.openapi()


def main() -> None:
    schema = build_schema()
    OUTPUT_PATH.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
