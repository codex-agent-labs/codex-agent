from __future__ import annotations

from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import ci.products.contract as contract_product
from ci.products.inventory import git_file_inventory
from ci.products.plan import plan_phase, NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST
from ci.products.registry import PhaseInstanceId
from ci.products.selection import phase_git_inventory
from ci.products.contract import (
    _publish_prepared_directory,
    _reject_symlinked_output_parent,
    prepare_contract_inputs,
)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)


class ContractOutputContainmentTest(unittest.TestCase):
    def _repository(self, root: Path) -> Path:
        repository = root / "repository"
        repository.mkdir()
        _git(repository, "init", "--quiet")
        _git(repository, "config", "user.name", "Contract Test")
        _git(repository, "config", "user.email", "contract@example.invalid")
        _write(
            repository / "ci/lanes/contract-product.production.pathspec",
            b"ci/lanes/contract-product.production.pathspec\ncontract/**\n",
        )
        _write(
            repository / "ci/lanes/contract-product.test.pathspec",
            b"ci/lanes/contract-product.test.pathspec\ntests/**\n",
        )
        _write(repository / ".github/workflows/contract.yml", b"name: Contract fixture\n")
        _write(repository / "contract/Contract.kt", b"contract\n")
        _write(repository / "tests/ContractTest.kt", b"test\n")
        _git(repository, "add", ".")
        _git(repository, "commit", "--quiet", "-m", "fixture")
        return repository

    def _prepare(self, repository: Path, output: Path) -> dict[str, object]:
        return prepare_contract_inputs(
            repository,
            output,
            "HEAD",
        )

    def test_source_mode_only_commit_preserves_content_inventory_and_original_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = self._repository(root)
            source = repository / "contract/Contract.kt"
            first = self._prepare(repository, root / "first")
            before = {path.name: path.read_bytes() for path in (root / "first/inventories").iterdir()}
            inputs = git_file_inventory(repository, first["commit"], ["contract/Contract.kt"])
            _git(repository, "config", "core.fileMode", "true")
            source.chmod(0o755)
            _git(repository, "add", "contract/Contract.kt")
            _git(repository, "commit", "--quiet", "-m", "mode only")
            second = self._prepare(repository, root / "second")
            self.assertNotEqual(first["commit"], second["commit"])
            self.assertNotEqual(first["tree"], second["tree"])
            self.assertEqual(inputs, git_file_inventory(repository, second["commit"], ["contract/Contract.kt"]))
            instance = PhaseInstanceId("contract", "contract", "binary", "common")
            keys = [plan_phase(
                instance, inventory=phase_git_inventory(repository, identity["commit"], instance),
                versions={name: "0.2.0" for name in
                          ("contract", "runtime-release", "runtime-compatibility", "sdk")},
                upstream_receipts=[], toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
            )["buildKey"] for identity in (first, second)]
            self.assertEqual(*keys)
            self.assertTrue(_git(repository, "ls-tree", "HEAD", "contract/Contract.kt").startswith("100755 "))
            for directory in ("first", "second"):
                self.assertEqual(before, {path.name: path.read_bytes()
                                         for path in (root / directory / "inventories").iterdir()})
            source.unlink()
            source.symlink_to("../tests/ContractTest.kt")
            _git(repository, "add", "contract/Contract.kt")
            _git(repository, "commit", "--quiet", "-m", "symbolic source")
            with self.assertRaises(ValueError):
                self._prepare(repository, root / "symbolic")
            self.assertFalse((root / "symbolic").exists())

    def test_rejects_symlinked_output_ancestor_without_writing_through_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = self._repository(root)
            external = root / "external"
            external.mkdir()
            _write(external / "must-survive", b"external\n")
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "output directory is unsafe"):
                self._prepare(repository, linked_parent / "prepared")

            self.assertEqual(b"external\n", (external / "must-survive").read_bytes())
            self.assertFalse((external / "prepared").exists())

    def test_prepares_transactional_output_under_a_normal_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = self._repository(root)
            output = root / "arbitrary-output" / "prepared"
            _write(output / "stale", b"stale\n")

            identity = self._prepare(repository, output)

            self.assertEqual(_git(repository, "rev-parse", "HEAD"), identity["commit"])
            self.assertEqual(
                {
                    "inventories/contract-binary-inputs.git-tree",
                    "inventories/contract-validation-inputs.git-tree",
                },
                {
                    path.relative_to(output).as_posix()
                    for path in output.rglob("*")
                    if path.is_file()
                },
            )
            self.assertFalse((output / "stale").exists())

    def test_rejects_repository_and_contract_input_overlap_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = self._repository(root)
            original = (repository / "contract/Contract.kt").read_bytes()
            commit = _git(repository, "rev-parse", "HEAD")

            for output in (
                repository,
                repository / ".git",
                repository / "contract",
                repository / "contract/new-output",
            ):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(ValueError, "overlaps repository inputs"):
                        self._prepare(repository, output)
                    self.assertEqual(original, (repository / "contract/Contract.kt").read_bytes())
                    self.assertEqual(commit, _git(repository, "rev-parse", "HEAD"))

    def test_failed_publication_and_rollback_preserve_the_original_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            output = root / "output"
            _write(source / "value", b"new\n")
            _write(output / "value", b"original\n")
            original_replace = contract_product.os.replace
            calls = 0

            def fail_publish_and_restore(source_path: Path, output_path: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    original_replace(source_path, output_path)
                else:
                    raise OSError(f"simulated replace failure {calls}")

            with mock.patch.object(
                contract_product.os,
                "replace",
                side_effect=fail_publish_and_restore,
            ):
                with self.assertRaisesRegex(RuntimeError, "original preserved at"):
                    _publish_prepared_directory(source, output)

            backups = list(root.glob(".output-backup-*"))
            self.assertEqual(1, len(backups))
            self.assertEqual(b"original\n", (backups[0] / "value").read_bytes())
            self.assertEqual(b"new\n", (source / "value").read_bytes())
            self.assertFalse(output.exists())

    def test_rejects_linked_worktree_git_and_common_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = self._repository(root)
            linked = root / "linked"
            _git(repository, "worktree", "add", "--quiet", "--detach", str(linked), "HEAD")
            commit = _git(linked, "rev-parse", "HEAD")
            git_directory = Path(_git(linked, "rev-parse", "--absolute-git-dir"))
            common_directory = Path(_git(linked, "rev-parse", "--git-common-dir"))
            if not common_directory.is_absolute():
                common_directory = linked / common_directory

            for output in (git_directory / "prepared", common_directory / "prepared"):
                with self.subTest(output=output):
                    with self.assertRaisesRegex(ValueError, "overlaps repository inputs"):
                        self._prepare(linked, output)
                    self.assertFalse(output.exists())
                    self.assertEqual(commit, _git(linked, "rev-parse", "HEAD"))

    def test_rejects_windows_reparse_point_ancestors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            parent = root / "reparse-parent"
            original_lstat = Path.lstat
            reparse = SimpleNamespace(
                st_mode=stat.S_IFDIR,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024),
            )

            with mock.patch.object(Path, "lstat", autospec=True) as lstat:
                lstat.side_effect = lambda path: reparse if path == parent else original_lstat(path)
                with self.assertRaisesRegex(ValueError, "output directory is unsafe"):
                    _reject_symlinked_output_parent(parent / "prepared", root)


if __name__ == "__main__":
    unittest.main()
