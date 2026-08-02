# Catalogue metadata

The **Administration → Metadata** page manages optional data owned by Meshive.
It never changes mounted library folders or archive contents.

Administrators can select a Creator, Franchise, or Collection discovered in
the catalogue and upload custom artwork. Meshive accepts common raster image
formats supported by Pillow, limits each upload to 12 MB and 40 megapixels,
applies EXIF orientation, limits the longest output edge to 1600 pixels, and
stores an optimized WebP copy in SQLite. Removing custom artwork restores the
built-in Meshive fallback image.

Creator link metadata remains available on the same page. Links and artwork
are independent; a creator can use either or both.

Because artwork is stored in the main database, manual, scheduled, and
pre-restore backups include it automatically. Artwork for a temporarily absent
catalogue value remains manageable with a model count of zero.
