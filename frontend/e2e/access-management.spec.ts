import { expect, test } from "@playwright/test";

const admin = {
  id: 1,
  username: "Admin",
  email: null,
  email_verified: false,
  role: "admin",
  is_active: true,
  must_change_password: false,
  role_definition: {
    id: 5,
    name: "Administrator",
    is_system: true,
    is_superuser: true,
  },
  permissions: ["catalogue.view", "users.manage", "roles.manage"],
  source_access: { all_sources: true, source_ids: [] },
};
const limited = {
  ...admin,
  id: 2,
  username: "Member",
  role: "user",
  role_definition: {
    id: 2,
    name: "Member",
    is_system: true,
    is_superuser: false,
  },
  permissions: ["catalogue.view"],
  source_access: { all_sources: true, source_ids: [] },
};
const noCatalogue = {
  ...limited,
  id: 3,
  username: "No catalogue",
  permissions: [],
  source_access: { all_sources: true, source_ids: [] },
};
const roles = [
  {
    id: 5,
    name: "Administrator",
    description: "Full access",
    is_system: true,
    is_superuser: true,
    permission_keys: ["users.manage", "roles.manage"],
    user_count: 1,
  },
  {
    id: 2,
    name: "Member",
    description: "Library member",
    is_system: true,
    is_superuser: false,
    permission_keys: ["catalogue.view"],
    user_count: 1,
  },
];
const users = [{ ...admin, source_ids: [] }];
const secondUser = {
  ...limited,
  id: 3,
  username: "Second user",
  email: "second@example.test",
  source_ids: [],
};

async function mockApi(page: import("@playwright/test").Page, user = admin) {
  await page.route("**/api/setup/status", (route) =>
    route.fulfill({ json: { required: false, enabled: false } }),
  );
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/admin/roles/permissions", (route) =>
    route.fulfill({ json: ["catalogue.view", "roles.manage", "users.manage"] }),
  );
  await page.route("**/api/admin/permissions", (route) =>
    route.fulfill({ json: ["catalogue.view", "roles.manage", "users.manage"] }),
  );
  await page.route("**/api/admin/roles", (route) =>
    route.fulfill({ json: roles }),
  );
  await page.route("**/api/admin/users/roles", (route) =>
    route.fulfill({ json: roles }),
  );
  await page.route("**/api/admin/users", (route) =>
    route.fulfill({ json: users }),
  );
  await page.route("**/api/admin/users/library-sources", (route) =>
    route.fulfill({
      json: [
        { id: 1, name: "Source A" },
        { id: 2, name: "Source B" },
      ],
    }),
  );
  await page.route("**/api/models/filters**", (route) =>
    route.fulfill({
      json: {
        models: [],
        creators: [],
        franchises: [],
        series: [],
        collections: [],
        sources: [],
        statuses: [],
        tags: [],
      },
    }),
  );
  await page.route("**/api/models?**", (route) =>
    route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 24 } }),
  );
}

test("administrator sees Users and Roles and system roles are read-only", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/admin/roles");
  await page.locator(".account-menu summary").click();
  await expect(page.getByRole("link", { name: "Users" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Roles" })).toBeVisible();
  await page.getByRole("button", { name: "Administrator" }).click();
  await expect(page.getByText("System roles are read-only.")).toBeVisible();
  await expect(page.getByText("Manage users")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete role" })).toHaveCount(
    0,
  );
});

test("custom roles and selected-source users submit the management API", async ({
  page,
}) => {
  await mockApi(page);
  let roleCreated = false;
  await page.route("**/api/admin/roles", async (route) => {
    if (route.request().method() === "POST") {
      roleCreated = true;
      await route.fulfill({
        json: { ...roles[1], id: 9, name: "Custom" },
        status: 201,
      });
      return;
    }
    await route.fulfill({
      json: roleCreated
        ? [
            ...roles,
            {
              ...roles[1],
              id: 9,
              name: "Custom",
              is_system: false,
              user_count: 0,
            },
          ]
        : roles,
    });
  });
  await page.route("**/api/admin/users", async (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toMatchObject({
        all_sources: false,
        source_ids: [1],
      });
      await route.fulfill({
        json: {
          ...users[0],
          id: 3,
          username: "Selected",
          all_sources: false,
          source_ids: [1],
        },
        status: 201,
      });
      return;
    }
    await route.fulfill({ json: users });
  });
  await page.goto("/admin/roles");
  await page.getByRole("button", { name: "New custom role" }).click();
  await expect(page.getByText("View catalogue")).toBeVisible();
  await page.getByLabel("Name").fill("Custom");
  await page.getByRole("button", { name: "Save role" }).click();
  await expect(page.getByText("Role saved successfully.")).toBeVisible();
  await page.goto("/admin/users");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Create user" }).first().click();
  await page.getByLabel("Username").first().fill("Selected");
  await page
    .getByRole("textbox", { name: "Password", exact: true })
    .fill("a sufficiently long password");
  await page.getByLabel("All current and future sources").first().uncheck();
  await page.getByLabel("Source A").first().check();
  await page.locator("form").getByRole("button", { name: "Create user" }).click();
  await expect(page.getByText("User created successfully.")).toBeVisible();
});

test("users without management permissions cannot open management URLs", async ({
  page,
}) => {
  await mockApi(page, limited);
  await page.goto("/admin/users");
  await expect(page).toHaveURL(/\/\?(?:.*)?$|\/$/);
  await page.goto("/admin/roles");
  await expect(page).toHaveURL(/\/\?(?:.*)?$|\/$/);
});

test("users without catalogue access receive a stable access-denied view", async ({
  page,
}) => {
  await mockApi(page, noCatalogue);
  await page.goto("/models/12");

  await expect(page).toHaveURL(/\/access-denied$/);
  await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
  await page.locator(".account-menu-trigger").click();
  await expect(page.getByRole("link", { name: "Account settings" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});

test("users with catalogue access can open the catalogue", async ({ page }) => {
  await mockApi(page, { ...limited, permissions: ["catalogue.view"] });
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Meshive" })).toBeVisible();
});

test("users without favorite access do not see favorite UI or trigger memberships", async ({
  page,
}) => {
  await mockApi(page, limited);
  let membershipRequests = 0;
  await page.route("**/api/favorite-lists/model-memberships**", (route) => {
    membershipRequests += 1;
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/models?**", (route) =>
    route.fulfill({
      json: {
        items: [{ id: 1, name: "Visible model", variant: null, creator: null, franchise: null, series: null, collection: null, status: "available", source_id: 1, source_name: "Source A", archive_format: null, archive_size_bytes: null, archive_count: 0, thumbnail_url: null, tags: [] }],
        total: 1,
        page: 1,
        page_size: 24,
      },
    }),
  );
  await page.goto("/");

  await expect(page.getByRole("button", { name: /Save to favorites|Save$/ })).toHaveCount(0);
  await page.locator(".account-menu-trigger").click();
  await expect(page.getByRole("link", { name: "Favorite lists" })).toHaveCount(0);
  expect(membershipRequests).toBe(0);

  await page.goto("/favorites");
  await expect(page).toHaveURL(/\/\?(?:.*)?$/);
  expect(membershipRequests).toBe(0);
});

test("switching users without edits does not ask to discard changes", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/api/admin/users", (route) =>
    route.fulfill({ json: [...users, secondUser] }),
  );
  let dialogCount = 0;
  page.on("dialog", async (dialog) => {
    dialogCount += 1;
    await dialog.accept();
  });

  await page.goto("/admin/users");
  await page.locator(".user-master-list .role-card").nth(1).click();

  await expect(page.getByLabel("Username")).toHaveValue("Second user");
  expect(dialogCount).toBe(0);
});

test("switching a changed user asks before discarding changes", async ({ page }) => {
  await mockApi(page);
  await page.route("**/api/admin/users", (route) =>
    route.fulfill({ json: [...users, secondUser] }),
  );
  await page.goto("/admin/users");
  await page.getByLabel("Username").fill("Changed admin");

  let dialogMessage = "";
  page.once("dialog", async (dialog) => {
    dialogMessage = dialog.message();
    await dialog.accept();
  });
  await page.locator(".user-master-list .role-card").nth(1).click();
  expect(dialogMessage).toBe("Discard unsaved user changes?");

  await expect(page.getByLabel("Username")).toHaveValue("Second user");
});

test("cancelling a changed-user switch retains the current selection", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/api/admin/users", (route) =>
    route.fulfill({ json: [...users, secondUser] }),
  );
  await page.goto("/admin/users");
  await page.getByLabel("Username").fill("Changed admin");

  page.once("dialog", (dialog) => dialog.dismiss());
  await page.locator(".user-master-list .role-card").nth(1).click();

  await expect(page.getByLabel("Username")).toHaveValue("Changed admin");
  await expect(page.locator(".user-master-list .role-card").first()).toHaveClass(
    /selected/,
  );
});

test("a user manager can select sources without source configuration access", async ({
  page,
}) => {
  const userManager = {
    ...admin,
    username: "User manager",
    role: "user",
    permissions: ["users.manage"],
    role_definition: {
      id: 9,
      name: "User manager",
      is_system: false,
      is_superuser: false,
    },
  };
  await mockApi(page, userManager);
  await page.goto("/admin/users");
  await expect(
    page.getByRole("heading", { name: "Users", level: 1 }),
  ).toBeVisible();
  await page.getByLabel("All current and future sources").first().uncheck();
  await expect(page.getByLabel("Source A").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Library sources" })).toHaveCount(
    0,
  );
  await page.goto("/admin/sources");
  await expect(page).toHaveURL(/\/access-denied$/);
});

test("custom roles can be edited and deleted", async ({ page }) => {
  const custom = {
    ...roles[1],
    id: 9,
    name: "Custom",
    is_system: false,
    user_count: 0,
  };
  await mockApi(page);
  await page.route("**/api/admin/roles/9", async (route) => {
    expect(["PUT", "DELETE"]).toContain(route.request().method());
    await route.fulfill({
      status: route.request().method() === "DELETE" ? 204 : 200,
      json: custom,
    });
  });
  await page.route("**/api/admin/roles", (route) =>
    route.fulfill({ json: [...roles, custom] }),
  );
  await page.goto("/admin/roles");
  await page.locator(".role-card").filter({ hasText: "Custom" }).click();
  await page.getByLabel("Name").fill("Custom edited");
  await page.getByRole("button", { name: "Save role" }).click();
  await page.locator(".role-card").filter({ hasText: "Custom" }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete role" }).click();
});
