from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from sentriface import cli
from sentriface.cli import build_dev_engine


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization_patch = patch("sentriface.cli._authorize_cli")
        self.authorization_patch.start()

    def tearDown(self) -> None:
        self.authorization_patch.stop()

    def test_profile_command_prints_runtime_settings(self) -> None:
        output = io.StringIO()

        with patch("sys.argv", ["sentriface", "--profile", "low", "profile"]):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("tier=low", text)
        self.assertIn("max_workers=1", text)
        self.assertIn("runtime=dev", text)

    def test_json_profile_command(self) -> None:
        output = io.StringIO()

        with patch("sys.argv", ["sentriface", "--json", "--profile", "low", "profile"]):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["tier"], "low")
        self.assertEqual(payload["max_workers"], 1)
        self.assertEqual(payload["onnx_intra_threads"], 1)

    def test_profile_accepts_runtime_threshold_overrides(self) -> None:
        output = io.StringIO()

        with patch(
            "sys.argv",
            [
                "sentriface",
                "--json",
                "--profile",
                "low",
                "--high-confidence",
                "0.7",
                "--medium-confidence",
                "0.5",
                "--min-quality-score",
                "0.6",
                "--max-image-edge",
                "720",
                "profile",
            ],
        ):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["high_confidence"], 0.7)
        self.assertEqual(payload["medium_confidence"], 0.5)
        self.assertEqual(payload["min_quality_score"], 0.6)
        self.assertEqual(payload["max_image_edge"], 720)

    def test_invalid_confidence_override_is_user_facing_error(self) -> None:
        output = io.StringIO()

        with patch(
            "sys.argv",
            [
                "sentriface",
                "--high-confidence",
                "0.4",
                "--medium-confidence",
                "0.8",
                "profile",
            ],
        ):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 1)
        self.assertIn("Medium confidence must be less than or equal to high confidence", output.getvalue())

    def test_missing_onnx_model_is_user_facing_error(self) -> None:
        output = io.StringIO()

        with patch(
            "sys.argv",
            [
                "sentriface",
                "--runtime",
                "onnx",
                "--detector-model",
                "missing-detector.onnx",
                "init-db",
            ],
        ), patch("sentriface.cli.require_os_network_policy"):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 1)
        self.assertIn("error=Model file not found", output.getvalue())

    def test_metrics_are_emitted_with_json(self) -> None:
        output = io.StringIO()

        with patch("sys.argv", ["sentriface", "--json", "--metrics", "--profile", "low", "init-db"]):
            with redirect_stdout(output):
                code = cli.main()

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertIn("metrics", payload)
        self.assertIn("timings_ms", payload["metrics"])
        self.assertIn("counts", payload["metrics"])

    def test_benchmark_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "face.jpg"
            canvas = np.full((120, 120, 3), 128, dtype=np.uint8)
            cv2.imwrite(str(image), canvas)
            output = io.StringIO()

            with patch(
                "sys.argv",
                [
                    "sentriface",
                    "--json",
                    "--metrics",
                    "--profile",
                    "low",
                    "--data-dir",
                    str(Path(temp) / "data"),
                    "benchmark",
                    str(image),
                    "--repeat",
                    "2",
                ],
            ):
                with redirect_stdout(output):
                    code = cli.main()

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["benchmark"]["images"], 1)
        self.assertEqual(payload["benchmark"]["repeat"], 2)
        self.assertEqual(payload["benchmark"]["runs"], 2)
        self.assertIn("total_benchmark_ms", payload["metrics"]["timings_ms"])
        self.assertEqual(payload["metrics"]["counts"]["benchmark_runs"], 2)

    def test_recognize_batch_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            images = temp_path / "images"
            images.mkdir()
            canvas = np.full((120, 120, 3), 128, dtype=np.uint8)
            cv2.imwrite(str(images / "a.jpg"), canvas)
            cv2.imwrite(str(images / "b.jpg"), canvas)
            output = io.StringIO()

            with patch(
                "sys.argv",
                [
                    "sentriface",
                    "--json",
                    "--profile",
                    "low",
                    "--data-dir",
                    str(temp_path / "data"),
                    "recognize-batch",
                    str(images),
                ],
            ):
                with redirect_stdout(output):
                    code = cli.main()

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(len(payload["batch"]), 2)
        self.assertEqual(payload["batch"][0]["faces"][0]["decision"], "unknown")

    def test_compare_threads_requires_onnx_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "face.jpg"
            canvas = np.full((120, 120, 3), 128, dtype=np.uint8)
            cv2.imwrite(str(image), canvas)
            output = io.StringIO()

            with patch(
                "sys.argv",
                [
                    "sentriface",
                    "--runtime",
                    "dev",
                    "benchmark",
                    str(image),
                    "--compare-threads",
                    "1,2",
                ],
            ):
                with redirect_stdout(output):
                    code = cli.main()

        self.assertEqual(code, 1)
        self.assertIn("--compare-threads requires --runtime onnx", output.getvalue())

    def test_face_delete_cli_creates_backup_and_supports_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "data"
            image = root / "face.jpg"
            canvas = np.full((120, 120, 3), 128, dtype=np.uint8)
            cv2.imwrite(str(image), canvas)
            engine = build_dev_engine(data_dir)
            engine.initialize()
            person_id = engine.confirm_new_person(engine.prepare_additions(image)[0], "CLI Person")
            embedding_id = engine.list_person_embeddings(person_id)[0].embedding_id

            delete_output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "sentriface",
                    "--json",
                    "--profile",
                    "low",
                    "--data-dir",
                    str(data_dir),
                    "delete-embedding",
                    embedding_id,
                ],
            ):
                with redirect_stdout(delete_output):
                    self.assertEqual(cli.main(), 0)
            deleted = json.loads(delete_output.getvalue())
            self.assertTrue(deleted["backup_id"].startswith("backup_"))
            self.assertTrue((data_dir / "backups" / deleted["backup_id"]).is_dir())

            list_output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "sentriface",
                    "--json",
                    "--profile",
                    "low",
                    "--data-dir",
                    str(data_dir),
                    "deleted-faces",
                ],
            ):
                with redirect_stdout(list_output):
                    self.assertEqual(cli.main(), 0)
            self.assertEqual(
                json.loads(list_output.getvalue())["deleted_faces"][0]["embedding_id"],
                embedding_id,
            )

            restore_output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "sentriface",
                    "--json",
                    "--profile",
                    "low",
                    "--data-dir",
                    str(data_dir),
                    "restore-embedding",
                    embedding_id,
                ],
            ):
                with redirect_stdout(restore_output):
                    self.assertEqual(cli.main(), 0)
            self.assertTrue(json.loads(restore_output.getvalue())["restored"])


if __name__ == "__main__":
    unittest.main()
