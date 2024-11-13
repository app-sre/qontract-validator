# qontract-validator

This project contains the tools necessary to bundle data into the format used by [qontract-server](https://github.com/app-sre/qontract-server) and to JSON validate it's schema.

## Installation

```sh
uv sync
source .venv/bin/activate

qontract-bundler --help
qontract-validator --help
```

### Overview: `qontract-bundler`

A bundle is a JSON document containing the payload that will be served by [qontract-server](https://github.com/app-sre/qontract-server). It is has four top level keys:

- `data`: documents that will be JSON validated
- `resources`: documents that will *not* be JSON validated.
- `schemas`: JSON validation schemas ([json-schema.org](http://json-schema.org))
- `graphl`: The GraphQL schema in intermediary format (this will not be needed eventually).

Example:

```json
{
  "data": {
    "/path/to/validated/doc1.yml": {
      "path": "/path/to/validated/doc1.yml",
      "$schema": "/schema1.yml",
      "key1": "...",
      "key2": "...",
      ...
    },
    ...
  },
  "resources": {
    "/path/to/NOT/validated/doc1": {
      "path": "/path/to/NOT/validated/doc1",
      "content": "...",
      "sha256sum": "..."
    },
    ...
  },
  "schemas": {
    "/schema1.yml": {
      "$schema": "...",
      "...": "...",
    }
  },
  "graphql": {
    {
      "name": "...",
      "fields": [
        {
          "isRequired": true,
          "type": "string",
          "name": "...""
        },
      ],
    },
  }
}
```

### Overview: `qontract-validator`

This command validates the `data` key in the bundle (`DATA_DIR`) against the json schemas in the `schemas` key (`SCHEMA_DIR`).

It will exit 0 upon success and 1 otherwise.

## Licence

See [LICENSE](LICENSE) for details.

## Authors

These tools have been written by the [Red Hat App-SRE Team](mailto:sd-app-sre@redhat.com).
