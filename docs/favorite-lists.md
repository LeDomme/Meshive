# Favorite lists

Meshive users can create multiple private lists for organizing catalogue
entries. Lists are visible only to their owner; administrators do not receive
access to another user's lists through the favorite-list API or interface.

## Saving an entry

Use **Save** on a catalogue card or **Save to favorites** on a model detail
page. The dialog can save any metadata available for that model:

- the exact model and optional variant;
- Creator;
- Franchise;
- Series;
- Collection;
- Tags.

Choose an existing list or create a new list without leaving the model. The
same entry cannot be added to the same list twice.

Creators, Franchises, Series, Collections, and Tags can also be added directly
from the favorite-list page. This does not require finding and opening a model
that contains the desired catalogue value first.

## Managing lists

Open the account menu and select **Favorite lists**. From there, a user can:

- create, rename, and delete lists;
- open saved models;
- open a catalogue view filtered to saved metadata or a tag;
- remove individual entries.

Saved models use a green heart in the catalogue and detail view. If a model is
saved in exactly one list, hovering changes the action to **Remove from list**
and clicking removes it immediately. Models saved in multiple lists open the
management dialog so that the intended list remains explicit.

Creator, Franchise, and Collection cards use Meshive-themed fallback artwork.
Administrators can replace it per catalogue value under **Administration →
Metadata**. Uploaded images are validated, resized to at most 1600 pixels per
edge, encoded as WebP, and stored in SQLite.

Deleting a list does not change any model, archive, image, tag, or source file.

## Missing and renamed entries

Model and tag entries store a label snapshot in addition to their database
reference. If the referenced record is deleted, the favorite remains readable
but is marked as no longer available and has no catalogue link.

Creator, Franchise, Series, and Collection entries use a normalized value as
their stable key. If the corresponding value no longer occurs in the catalogue,
the saved entry is shown as unavailable. A later scan that restores the same
normalized value makes its catalogue link available again.

Missing models that remain indexed by Meshive are still valid favorites and
continue to link to their detail page.

## Backups and upgrades

Favorite lists are ordinary Meshive database records. Manual, scheduled, and
pre-restore backups include them and custom metadata artwork automatically. No
additional directory or container volume is required.
