# nthlayer migrate

Convert legacy NthLayer service.yaml files to the OpenSRM format.

## Synopsis

```bash
nthlayer migrate <service-file> [options]
```

## Description

The `migrate` command converts legacy flat-YAML service specifications to the OpenSRM `srm/v1` format. The migration:

- Adds `apiVersion: srm/v1` and `kind: ServiceReliabilityManifest`
- Restructures fields into `metadata` and `spec` sections
- Converts `resources[kind=SLO]` entries into `spec.slos` map
- Normalizes service type aliases (e.g. `background-job` → `worker`)
- Preserves all existing configuration

If the input file is already in OpenSRM format, the command reports this and exits cleanly.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Migration successful (or file already OpenSRM) |
| 1 | Error (file not found, parse failure, output exists without `--force`) |

## Options

| Option | Description |
|--------|-------------|
| `--output DIR`, `-o DIR` | Output directory (default: same directory as input) |
| `--dry-run` | Print migrated YAML to stdout without writing a file |
| `--force` | Overwrite existing output file if it already exists |

## Examples

### Basic Migration

```bash
nthlayer migrate services/payment-api.yaml
```

Output:
```
Migration Complete: payment-api

  ✓ Converted from legacy NthLayer format to OpenSRM

  Changes:
    • Added apiVersion: srm/v1
    • Added kind: ServiceReliabilityManifest
    • Restructured metadata and spec sections

  Output: services/payment-api.reliability.yaml

  Next steps:
    1. Review the migrated file: services/payment-api.reliability.yaml
    2. Validate: nthlayer validate services/payment-api.reliability.yaml
    3. Test: nthlayer plan services/payment-api.reliability.yaml

  ⚠ The legacy file (payment-api.yaml) can be removed after validation
```

### Dry-Run Preview

```bash
nthlayer migrate services/payment-api.yaml --dry-run
```

Prints the full migrated YAML to stdout without writing any files.

### Custom Output Directory

```bash
nthlayer migrate services/payment-api.yaml --output opensrm/
```

Writes the migrated file to `opensrm/payment-api.reliability.yaml`.

### Batch Migration

```bash
for f in services/*.yaml; do
  nthlayer migrate "$f" --output opensrm/ --force
done
```

## What Changes

The output file uses the naming convention `<service-name>.reliability.yaml` and contains the full OpenSRM structure:

| Legacy Field | OpenSRM Location |
|-------------|------------------|
| `name` | `metadata.name` |
| `team` | `metadata.team` |
| `tier` | `metadata.tier` |
| `type` | `spec.type` |
| `dependencies` | `spec.dependencies` |
| `resources[kind=SLO]` | `spec.slos` |
| `resources[kind=Alert]` | `spec.alerting.rules` |
| `resources[kind=Dependencies]` | `spec.dependencies` |
| `environments` | `spec.deployment.environments` |

## See Also

- [OpenSRM Format](../concepts/opensrm.md) — Format guide and schema overview
- [Service YAML Schema](../reference/service-yaml.md) — Full field reference
