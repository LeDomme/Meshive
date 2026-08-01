# Library source patterns

Each library source has two related groups of patterns:

- Directory patterns describe folders relative to the configured container
  path. For example, `{franchise}/{model_folder}`.
- Model-name patterns extract metadata from the final `{model_folder}` value.

Both fields may contain multiple alternatives, one per line. Meshive
tries them from top to bottom and uses the first pattern that matches without
conflicting with values already extracted from the directory.

Put more specific alternatives before more general alternatives.

## Franchise and optional series

For a source rooted at `/models/library-one`, the directory pattern can stay:

```text
{franchise}/{model_folder}
```

The following model-name patterns support both ordinary franchise names and
more specific series names:

```text
{franchise} - {model} - by {creator}
{series} - {model} - by {creator}
{series} - {model} - {creator}
```

Given `Galaxy/Galaxy Chronicles - Explorer - Example Studio`, Meshive resolves:

- `franchise`: `Galaxy`
- `series`: `Galaxy Chronicles`
- `model`: `Explorer`
- `creator`: `Example Studio`

The first alternative still handles a folder such as
`Galaxy/Galaxy - Rover - by Example Studio`.

## Franchise repeated before a series

Some creators include both the broad franchise and the series in the model
folder. Use the more specific alternative first:

```text
{franchise} - {series} - {model} - by {creator}
{series} - {model} - by {creator}
```

For `Galaxy/Galaxy - Outer Rim - Navigator - by Example Studio`, the result is
`Galaxy` as the franchise, `Outer Rim` as the series, and `Navigator` as the
model.

Always use **Preview values** with a path relative to the source's container
path before saving. Do not include `/models`, the source root, or an archive
filename in the preview path.

## Optional directory levels

If some models are grouped inside an additional series folder, configure both
directory layouts, with the deeper and more specific layout first:

```text
{creator_folder}/{franchise}/{series}/{model_folder}
{creator_folder}/{franchise}/{model_folder}
```

The scanner only considers a directory a model candidate when it directly
contains at least one supported archive or image. Pure organisation folders are
therefore not added to the catalogue, even when a broad `{model}` fallback is
the final model-name pattern.
