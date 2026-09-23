"""Unit tests — task lifecycle."""

from __future__ import annotations

import pytest

from life_ledger.domain.models import (
    ArchivedTaskError,
    InvalidTaskError,
    NotArchivedError,
    TaskAlreadyExistsError,
    TaskNotFoundError,
)
from life_ledger.domain.services import TaskService


class TestTaskCreation:
    """Tests for task creation and validation."""

    def test_create_task_success(
        self,
        task_svc: TaskService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "At least 30 minutes",
        )

        assert task.id > 0
        assert task.name == "Exercise"
        assert task.cutoff_message == "At least 30 minutes"
        assert task.is_active
        assert task.archived_at is None
        assert task.created_at.tzinfo is not None

    def test_create_trims_whitespace(
        self,
        task_svc: TaskService,
    ) -> None:
        task = task_svc.create_task(
            "  Reading  ",
            "  At least 10 pages  ",
        )

        assert task.name == "Reading"
        assert task.cutoff_message == "At least 10 pages"

    def test_create_empty_name_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(
            InvalidTaskError,
            match="name cannot be empty",
        ):
            task_svc.create_task(
                "",
                "Some cutoff",
            )

    def test_create_whitespace_only_name_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(
            InvalidTaskError,
            match="name cannot be empty",
        ):
            task_svc.create_task(
                "   ",
                "Some cutoff",
            )

    def test_create_empty_cutoff_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(
            InvalidTaskError,
            match="Cutoff message cannot be empty",
        ):
            task_svc.create_task(
                "Exercise",
                "",
            )

    def test_create_whitespace_only_cutoff_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(
            InvalidTaskError,
            match="Cutoff message cannot be empty",
        ):
            task_svc.create_task(
                "Exercise",
                "   ",
            )

    def test_create_duplicate_name_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        with pytest.raises(TaskAlreadyExistsError):
            task_svc.create_task(
                "Exercise",
                "Different cutoff",
            )

    def test_create_case_insensitive_duplicate_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        with pytest.raises(TaskAlreadyExistsError):
            task_svc.create_task(
                "exercise",
                "30 min",
            )

    def test_create_name_too_long_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(
            InvalidTaskError,
            match="at most 200 characters",
        ):
            task_svc.create_task(
                "x" * 201,
                "cutoff",
            )

    def test_create_cutoff_too_long_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(
            InvalidTaskError,
            match="at most 500 characters",
        ):
            task_svc.create_task(
                "Exercise",
                "x" * 501,
            )

    def test_create_after_archiving_same_name_is_allowed(
        self,
        task_svc: TaskService,
    ) -> None:
        original = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task("Exercise")

        replacement = task_svc.create_task(
            "Exercise",
            "45 min",
        )

        assert replacement.id != original.id
        assert replacement.name == "Exercise"
        assert replacement.cutoff_message == "45 min"
        assert replacement.is_active

    def test_archived_task_does_not_block_new_task_with_same_name(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.archive_task("Exercise")

        replacement = task_svc.create_task(
            "exercise",
            "45 min",
        )

        assert replacement.is_active


class TestTaskLookup:
    """Tests for task lookup semantics."""

    def test_get_task_returns_existing_task(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        found = task_svc.get_task("Exercise")

        assert found.id == created.id
        assert found.name == "Exercise"

    def test_get_task_is_case_insensitive(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        found = task_svc.get_task("exercise")

        assert found.id == created.id

    def test_get_task_trims_name(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        found = task_svc.get_task("  Exercise  ")

        assert found.id == created.id

    def test_get_nonexistent_task_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            task_svc.get_task("DoesNotExist")

    def test_get_empty_name_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(InvalidTaskError):
            task_svc.get_task("   ")


class TestTaskEditing:
    """Tests for editing active tasks."""

    def test_edit_name(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exorcise",
            "30 min",
        )

        updated = task_svc.edit_task(
            "Exorcise",
            "Exercise",
            None,
        )

        assert updated.name == "Exercise"
        assert updated.cutoff_message == "30 min"
        assert updated.is_active

    def test_edit_cutoff(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "20 min",
        )

        updated = task_svc.edit_task(
            "Exercise",
            None,
            "30 min",
        )

        assert updated.name == "Exercise"
        assert updated.cutoff_message == "30 min"

    def test_edit_trims_values(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "20 min",
        )

        updated = task_svc.edit_task(
            "Exercise",
            "  Exercise Daily  ",
            "  30 minutes  ",
        )

        assert updated.name == "Exercise Daily"
        assert updated.cutoff_message == "30 minutes"

    def test_edit_empty_name_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        with pytest.raises(
            InvalidTaskError,
            match="name cannot be empty",
        ):
            task_svc.edit_task(
                "Exercise",
                "   ",
                None,
            )

    def test_edit_empty_cutoff_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )

        with pytest.raises(
            InvalidTaskError,
            match="Cutoff message cannot be empty",
        ):
            task_svc.edit_task(
                "Exercise",
                None,
                "   ",
            )

    def test_edit_name_collision_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.create_task(
            "Learning",
            "45 min",
        )

        with pytest.raises(TaskAlreadyExistsError):
            task_svc.edit_task(
                "Exercise",
                "Learning",
                None,
            )

    def test_edit_case_insensitive_name_collision_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.create_task(
            "Learning",
            "45 min",
        )

        with pytest.raises(TaskAlreadyExistsError):
            task_svc.edit_task(
                "Exercise",
                "learning",
                None,
            )

    def test_edit_nonexistent_task_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            task_svc.edit_task(
                "DoesNotExist",
                "new",
                None,
            )

    def test_edit_archived_task_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.archive_task("Exercise")

        with pytest.raises(ArchivedTaskError):
            task_svc.edit_task(
                "Exercise",
                "New Name",
                None,
            )

    def test_edit_same_values_is_allowed(
        self,
        task_svc: TaskService,
    ) -> None:
        task = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        updated = task_svc.edit_task(
            "Exercise",
            "Exercise",
            "30 min",
        )

        assert updated.id == task.id
        assert updated.name == task.name
        assert updated.cutoff_message == task.cutoff_message


class TestTaskArchival:
    """Tests for task archival."""

    def test_archive_task(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        archived = task_svc.archive_task("Exercise")

        assert archived.id == created.id
        assert not archived.is_active
        assert archived.archived_at is not None
        assert archived.archived_at >= archived.created_at

    def test_archived_task_not_in_active_list(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.archive_task("Exercise")

        active = task_svc.list_active_tasks()

        assert not any(task.name == "Exercise" for task in active)

    def test_archived_task_remains_in_all_tasks(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.archive_task("Exercise")

        all_tasks = task_svc.list_all_tasks()

        assert any(task.id == created.id and not task.is_active for task in all_tasks)

    def test_archive_nonexistent_task_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            task_svc.archive_task("DoesNotExist")

    def test_archive_already_archived_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        task_svc.create_task(
            "Exercise",
            "30 min",
        )
        task_svc.archive_task("Exercise")

        with pytest.raises(ArchivedTaskError):
            task_svc.archive_task("Exercise")

    def test_archiving_does_not_delete_task_definition(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        archived = task_svc.archive_task("Exercise")
        all_tasks = task_svc.list_all_tasks()

        found = next(task for task in all_tasks if task.id == created.id)

        assert found.name == "Exercise"
        assert found.cutoff_message == "30 min"
        assert found.archived_at == archived.archived_at


class TestTaskRestoration:
    """Tests for restoring archived tasks."""

    def test_restore_archived_task_by_id(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task("Exercise")

        restored = task_svc.restore_task_by_id(
            created.id,
        )

        assert restored.id == created.id
        assert restored.name == "Exercise"
        assert restored.is_active
        assert restored.archived_at is None

    def test_restore_active_task_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        with pytest.raises(NotArchivedError):
            task_svc.restore_task_by_id(
                created.id,
            )

    def test_restore_nonexistent_task_raises(
        self,
        task_svc: TaskService,
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            task_svc.restore_task_by_id(999)

    def test_restore_appears_in_active_list(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task("Exercise")
        task_svc.restore_task_by_id(created.id)

        active = task_svc.list_active_tasks()

        assert any(task.id == created.id and task.name == "Exercise" for task in active)

    def test_restore_preserves_task_identity(
        self,
        task_svc: TaskService,
    ) -> None:
        created = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task("Exercise")
        restored = task_svc.restore_task_by_id(created.id)

        assert restored.id == created.id

    def test_restore_conflicts_with_replacement_active_task(
        self,
        task_svc: TaskService,
    ) -> None:
        original = task_svc.create_task(
            "Exercise",
            "30 min",
        )

        task_svc.archive_task("Exercise")

        replacement = task_svc.create_task(
            "Exercise",
            "45 min",
        )

        assert replacement.id != original.id

        with pytest.raises(TaskAlreadyExistsError):
            task_svc.restore_task_by_id(original.id)

    def test_restore_wrong_task_id_does_not_restore_another_task(
        self,
        task_svc: TaskService,
    ) -> None:
        first = task_svc.create_task(
            "Exercise",
            "30 min",
        )
        second = task_svc.create_task(
            "Learning",
            "45 min",
        )

        task_svc.archive_task("Exercise")

        with pytest.raises(NotArchivedError):
            task_svc.restore_task_by_id(second.id)

        restored = task_svc.restore_task_by_id(first.id)

        assert restored.id == first.id
        assert restored.name == "Exercise"
