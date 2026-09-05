export interface PermissionPresentation {
  key: string;
  label: string;
  description: string;
  group: string;
  administrative?: boolean;
}

const definitions: PermissionPresentation[] = [
  [
    "catalogue.view",
    "View catalogue",
    "Browse visible library models.",
    "Catalogue",
  ],
  [
    "catalogue.view_maintenance",
    "View maintenance status",
    "See catalogue maintenance states.",
    "Catalogue",
  ],
  [
    "archives.view_entries",
    "View archive contents",
    "Inspect files inside archives.",
    "Archives & downloads",
  ],
  [
    "archives.download",
    "Download archives",
    "Download visible model archives.",
    "Archives & downloads",
  ],
  [
    "favorites.manage",
    "Manage favourites",
    "Create and manage personal favourites.",
    "Favourites",
  ],
  [
    "models.primary_image",
    "Set primary image",
    "Choose a model's primary image.",
    "Models",
  ],
  [
    "models.tags",
    "Edit model tags",
    "Add or remove direct model tags.",
    "Models",
  ],
  ["models.rescan", "Rescan models", "Start targeted model rescans.", "Models"],
  [
    "models.rebuild_images",
    "Rebuild model images",
    "Rebuild model image caches.",
    "Models",
  ],
  [
    "models.reset_images",
    "Reset model images",
    "Reset model image selections.",
    "Models",
  ],
  [
    "models.delete_missing",
    "Delete missing models",
    "Remove missing model records.",
    "Models",
  ],
  ["scans.view", "View scans", "See scan history and queue status.", "Scans"],
  ["scans.start", "Start scans", "Start scans for allowed sources.", "Scans"],
  [
    "scans.control",
    "Control scans",
    "Pause, resume, or cancel scans.",
    "Scans",
  ],
  [
    "metadata.manage",
    "Manage metadata",
    "Edit visible model metadata.",
    "Metadata & tags",
  ],
  ["tags.manage", "Manage tags", "Manage global tags.", "Metadata & tags"],
  [
    "tag_rules.manage",
    "Manage automatic tag rules",
    "Manage tag rules.",
    "Metadata & tags",
  ],
  [
    "sources.manage",
    "Manage library sources",
    "Configure library sources.",
    "System administration",
    true,
  ],
  [
    "diagnostics.view",
    "View diagnostics",
    "View operational diagnostics.",
    "System administration",
    true,
  ],
  [
    "backups.manage",
    "Manage backups",
    "Create and manage backups.",
    "System administration",
    true,
  ],
  [
    "users.manage",
    "Manage users",
    "Create and manage user accounts.",
    "System administration",
    true,
  ],
  [
    "roles.manage",
    "Manage roles",
    "Create and manage custom roles.",
    "System administration",
    true,
  ],
  [
    "audit.view",
    "View audit log",
    "View audit records.",
    "System administration",
    true,
  ],
].map(
  ([
    key,
    label,
    description,
    group,
    administrative,
  ]): PermissionPresentation => ({
    key: key as string,
    label: label as string,
    description: description as string,
    group: group as string,
    administrative: Boolean(administrative),
  }),
);

export const permissionPresentation = new Map(
  definitions.map((item) => [item.key, item]),
);

export function presentPermission(key: string): PermissionPresentation {
  return (
    permissionPresentation.get(key) ?? {
      key,
      label: key,
      description: "Unknown permission.",
      group: "Other",
    }
  );
}
