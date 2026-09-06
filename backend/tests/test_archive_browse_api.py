from types import SimpleNamespace

from fastapi import status
from test_catalog_api import catalog_client

from meshive.auth.dependencies import get_current_user
from meshive.models.authorization import UserLibrarySource
from meshive.models.catalog import Archive, ArchiveBrowseNode, ArchiveEntry, LibraryModel
from meshive.models.library_source import LibrarySource
from meshive.models.user import User
from meshive.services.archive_browse import rebuild_archive_browse_nodes


def _source(session, name: str) -> LibrarySource:
    source = LibrarySource(name=name, root_path=f"/models/{name}", directory_pattern="{model}")
    session.add(source)
    session.flush()
    return source


def _archive(session, source: LibrarySource, name: str = "Model") -> tuple[LibraryModel, Archive]:
    model = LibraryModel(
        library_source_id=source.id,
        relative_path=name,
        name=name,
        status="available",
    )
    session.add(model)
    session.flush()
    archive = Archive(
        model_id=model.id,
        filename=f"{name}.zip",
        relative_path=f"{name}/{name}.zip",
        format="zip",
        size_bytes=1,
        modified_ns=1,
        status="ready",
        entry_count=0,
        uncompressed_size_bytes=0,
    )
    session.add(archive)
    session.flush()
    return model, archive


def _add_entries(session, archive: Archive, paths: list[tuple[str, bool]]) -> None:
    session.add_all(
        [
            ArchiveEntry(
                archive_id=archive.id,
                path=path,
                name=path.replace("\\", "/").rstrip("/").split("/")[-1],
                is_directory=is_directory,
                size_bytes=1,
            )
            for path, is_directory in paths
        ]
    )
    session.flush()
    rebuild_archive_browse_nodes(session, archive.id)


def test_archive_browse_lists_direct_children_and_synthetic_folders() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            model, archive = _archive(session, _source(session, "source"))
            _add_entries(
                session,
                archive,
                [
                    ("zeta.txt", False),
                    ("Folder/deep/file.stl", False),
                    ("folder/other.stl", False),
                    ("unicode\\Ärger\\same.stl", False),
                    ("explicit", True),
                ],
            )
            session.commit()

        root = client.get(f"/api/models/{model.id}/archives/{archive.id}/entries")
        assert root.status_code == status.HTTP_200_OK
        assert [(item["path"], item["is_directory"]) for item in root.json()["items"]] == [
            ("explicit", True),
            ("Folder", True),
            ("folder", True),
            ("unicode", True),
            ("zeta.txt", False),
        ]
        nested = client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"parent_path": "unicode\\Ärger"},
        )
        assert nested.json() == {
            "items": [
                {
                    "path": "unicode/Ärger/same.stl",
                    "name": "same.stl",
                    "is_directory": False,
                    "size_bytes": 1,
                    "compressed_size_bytes": None,
                    "modified_at": None,
                }
            ],
            "next_cursor": None,
            "parent_path": "unicode/Ärger",
        }


def test_archive_browse_cursor_and_search_are_stable() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            model, archive = _archive(session, _source(session, "source"))
            _add_entries(
                session,
                archive,
                [
                    ("alpha.txt", False),
                    ("beta.txt", False),
                    ("one/same.stl", False),
                    ("two/same.stl", False),
                    ("zeta.txt", False),
                ],
            )
            session.commit()

        first = client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"page_size": 2},
        ).json()
        second = client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"page_size": 2, "cursor": first["next_cursor"]},
        ).json()
        third = client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"page_size": 2, "cursor": second["next_cursor"]},
        ).json()
        paths = [item["path"] for page in (first, second, third) for item in page["items"]]
        assert paths == ["one", "two", "alpha.txt", "beta.txt", "zeta.txt"]
        assert len(paths) == len(set(paths))

        search = client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"search": "same", "page_size": 1},
        ).json()
        next_search = client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"search": "same", "cursor": search["next_cursor"]},
        ).json()
        assert [item["path"] for item in search["items"] + next_search["items"]] == [
            "one/same.stl",
            "two/same.stl",
        ]
        assert search["parent_path"] is None
        assert client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"cursor": "not-a-cursor"},
        ).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"search": "x" * 201},
        ).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert client.get(
            f"/api/models/{model.id}/archives/{archive.id}/entries",
            params={"search": "", "page_size": 501},
        ).status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_archive_browse_response_stays_bounded_for_large_archives() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            model, archive = _archive(session, _source(session, "source"))
            session.add_all(
                [
                    ArchiveBrowseNode(
                        archive_id=archive.id,
                        path=f"file-{index:06}.stl",
                        parent_path="",
                        name=f"file-{index:06}.stl",
                        name_sort_key=f"file-{index:06}.stl",
                        path_sort_key=f"file-{index:06}.stl",
                        depth=1,
                        is_directory=False,
                    )
                    for index in range(100_000)
                ]
            )
            session.commit()

        response = client.get(f"/api/models/{model.id}/archives/{archive.id}/entries")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["items"]) == 200
        assert len(response.content) < 100_000


def test_archive_browse_reports_missing_index_instead_of_an_empty_tree() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            model, archive = _archive(session, _source(session, "missing-index"))
            archive.entry_count = 1
            session.add(
                ArchiveEntry(
                    archive_id=archive.id,
                    path="only.stl",
                    name="only.stl",
                    is_directory=False,
                    size_bytes=1,
                )
            )
            session.commit()

        response = client.get(f"/api/models/{model.id}/archives/{archive.id}/entries")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "browse index" in response.json()["detail"]


def test_archive_browse_enforces_visibility_archive_ownership_and_permission() -> None:
    with catalog_client() as (client, sessions):
        with sessions() as session:
            source_a = _source(session, "a")
            source_b = _source(session, "b")
            model_a, archive_a = _archive(session, source_a, "A")
            model_b, archive_b = _archive(session, source_b, "B")
            _add_entries(session, archive_a, [("visible.stl", False)])
            _add_entries(session, archive_b, [("hidden.stl", False)])
            user = User(
                username="Restricted",
                normalized_username="restricted",
                password_hash="unused",
                role="user",
                all_sources=False,
                is_active=True,
            )
            session.add(user)
            session.flush()
            session.add(UserLibrarySource(user_id=user.id, library_source_id=source_a.id))
            session.commit()

        app_user = SimpleNamespace(
            id=user.id,
            role_definition=SimpleNamespace(is_superuser=False),
            role_id=None,
            all_sources=False,
        )
        from meshive.main import app

        app.dependency_overrides[get_current_user] = lambda: app_user
        visible_without_permission = client.get(
            f"/api/models/{model_a.id}/archives/{archive_a.id}/entries"
        )
        hidden = client.get(f"/api/models/{model_b.id}/archives/{archive_b.id}/entries")
        wrong_archive = client.get(f"/api/models/{model_a.id}/archives/{archive_b.id}/entries")
        assert visible_without_permission.status_code == status.HTTP_403_FORBIDDEN
        assert hidden.status_code == status.HTTP_404_NOT_FOUND
        assert wrong_archive.status_code == status.HTTP_404_NOT_FOUND
