# Catalogue metadata

The **Administration → Metadata** page manages optional data owned by Meshive.
It never changes mounted library folders or archive contents.

Administrators can manage stable Creator Profiles, including canonical names,
aliases, descriptions, links, and custom artwork. Creator merges require a
preview and can be undone; source-scoped managers may only operate on profiles
whose models they can access. Franchise and Collection metadata remains managed
by discovered catalogue value. Meshive accepts common raster image
formats supported by Pillow, limits each upload to 12 MB and 40 megapixels,
applies EXIF orientation, limits the longest output edge to 1600 pixels, and
stores an optimized WebP copy in SQLite. Removing custom artwork restores the
built-in Meshive fallback image.

Creator links and artwork are profile-bound and independent; a creator can use
either or both. Creator Cards on model details and catalogue filters use stable
profile identity while retaining legacy creator fields for 1.x compatibility.

Because artwork is stored in the main database, manual, scheduled, and
pre-restore backups include it automatically. Artwork for a temporarily absent
catalogue value remains manageable with a model count of zero.
