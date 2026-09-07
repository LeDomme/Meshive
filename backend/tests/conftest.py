"""Suite-wide runtime isolation for tests that start the application lifespan."""

import os


# The production Settings defaults deliberately point at the image's stable
# mount contract.  Application-lifespan tests do not use those mounts, so give
# background schedulers a writable disposable SQLite location instead.
os.environ.setdefault("MESHIVE_DATABASE_URL", "sqlite:////tmp/meshive-pytest.db")
