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

## Optional model variants

Use the optional `{variant}` value when a creator publishes several distinct
versions of the same canonical model. The captured value is free-form; Meshive
does not require words such as `Variant` or `Edition`.

The recommended convention places a recognized identifier before the free-form
value. `{variant_identifier}` accepts `variant`, `version`, `edition`,
`revision`, `rev`, and `ver` without regard to capitalization. These patterns
cover models both with and without a series:

```text
{franchise} - {series} - {model} - {variant_identifier} {variant} - by {creator}
{franchise} - {model} - {variant_identifier} {variant} - by {creator}
{franchise} - {series} - {model} - by {creator}
{franchise} - {model} - by {creator}
```

They parse all of the following without changing the canonical model name:

```text
Marvel - X-Men - Psylocke - variant 06 - by E.S Monster
Marvel - X-Men - Psylocke - Edition 2024 - by E.S Monster
Street Fighter - Cammy - variant Beach - by E.S Monster
Street Fighter - Cammy - VERSION Chibi - by E.S Monster
```

The model filter contains one `Psylocke` option and selects every variant.
Variants remain visible on catalogue cards and detail pages and are included in
full-text search.

A plain `{variant}` segment is also supported. Be careful when a source mixes
series and non-series layouts: these two patterns have the same structure and
the first one would always win for a matching folder:

```text
{franchise} - {series} - {model} - by {creator}
{franchise} - {model} - {variant} - by {creator}
```

The pattern preview warns about this overlap. Add a source-specific literal
marker to make the layouts distinct. Meshive recommends
`{variant_identifier} {variant}` for consistent archives. A custom fixed marker
such as `style {variant}` or `[{variant}]` remains supported; fixed literals are
also matched case-insensitively. Spacing must still match the folder names. Put
variant alternatives before their corresponding non-variant fallbacks and keep
a broad `{model}` fallback last.

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
