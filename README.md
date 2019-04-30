![](https://img.shields.io/github/license/app-sre/qontract-reconcile.svg?style=flat)

# qontract-validator

This project contains the tools necessary to bundle data into the format used by [qontract-server](https://github.com/app-sre/qontract-server) and to JSON validate it's schema.

## Create a bundle: `qontract-bundler`

### Overview

A bundle is a JSON document containing the payload that will be served by [qontract-server](https://github.com/app-sre/qontract-server). It is has four top level keys:

- `data`: documents that will be JSON validated
- `resources`: documents that will *not* be JSON validated.
- `schemas`: JSON validation schemas ([json-schema.org](http://json-schema.org))
- `graphl`: The GraphQL schema in intermediary format (this will not be needed eventually).

Example:

```yaml
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

### Usage

```
Usage: qontract-bundler [OPTIONS] SCHEMA_DIR GRAPHQL_SCHEMA_FILE DATA_DIR
                        RESOURCE_DIR


Options:
  --resolve  Resolve references
  --help     Show this message and exit.
```

### Docker Usage

Container: https://quay.io/repository/app-sre/qontract-validator

Example:

```
docker run -v <mounts> \
    quay.io/app-sre/qontract-validator:latest \
    qontract-bundler /schemas /graphql-schema/schema.yml /data /resources
```

## Validating the bundle: `qontract-validator`

### Overview

This command validates the `data` key in the bundle (`DATA_DIR`) against the json schemas in the `schemas` key (`SCHEMA_DIR`).

It will exit 0 upon success and 1 otherwise.


### Usage

```
Usage: qontract-validator [OPTIONS] BUNDLE

Options:
  --only-errors  Print only errors
  --help         Show this message and exit.
```

### Docker usage

Container: https://quay.io/repository/app-sre/qontract-validator

Example:

```
docker run -v $PWD:/data:z \
    quay.io/app-sre/qontract-validator:latest \
    qontract-validator --only-errors /data/data.json
```


## Licence

[Apache License Version 2.0](LICENSE).

## Authors

These tools have been written by the [Red Hat App-SRE Team](sd-app-sre@redhat.com).
