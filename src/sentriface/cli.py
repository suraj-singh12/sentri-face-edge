from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from sentriface.components.dev_components import HashFaceEmbedder, WholeImageFaceDetector
from sentriface.components.linear_index import LinearFaceIndex
from sentriface.components.onnx_components import OnnxArcFaceEmbedder, OnnxScrfdDetector
from sentriface.config import HardwareProfile, RuntimeConfig, config_for_hardware
from sentriface.engine import IMAGE_EXTENSIONS, FaceEngine
from sentriface.errors import SentriFaceError
from sentriface.hardware import assess_hardware
from sentriface.models import PersonMatch
from sentriface.storage.sqlite_store import SQLiteIdentityStore


def build_dev_engine(data_dir: Path, config: RuntimeConfig | None = None) -> FaceEngine:
    config = config or config_for_hardware(assess_hardware(), data_dir=data_dir)
    return FaceEngine(
        config=config,
        detector=WholeImageFaceDetector(),
        embedder=HashFaceEmbedder(config.embedding_dim),
        index=LinearFaceIndex(),
        store=SQLiteIdentityStore(config.db_path, config.embedding_dim),
    )


def build_onnx_engine(config: RuntimeConfig) -> FaceEngine:
    return FaceEngine(
        config=config,
        detector=OnnxScrfdDetector(
            model_path=config.detector_model,
            max_image_edge=config.max_image_edge,
            input_size=config.detector_input_size,
            intra_op_threads=config.onnx_intra_threads,
        ),
        embedder=OnnxArcFaceEmbedder(
            model_path=config.recognizer_model,
            intra_op_threads=config.onnx_intra_threads,
        ),
        index=LinearFaceIndex(),
        store=SQLiteIdentityStore(config.db_path, config.embedding_dim),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="SentriFace Edge")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--profile",
        choices=("auto", "low", "medium", "high"),
        default="auto",
        help="Runtime profile. Use auto on real machines.",
    )
    parser.add_argument(
        "--runtime",
        choices=("dev", "onnx"),
        default="dev",
        help="Use dev placeholders or real ONNX CPU components.",
    )
    parser.add_argument("--detector-model", type=Path, default=Path("models/det_500m.onnx"))
    parser.add_argument("--recognizer-model", type=Path, default=Path("models/w600k_r50.onnx"))
    parser.add_argument("--onnx-threads", type=int, help="Override ONNX Runtime intra-op threads")
    parser.add_argument("--max-image-edge", type=int, help="Override image downscale edge before detection")
    parser.add_argument("--high-confidence", type=float, help="Similarity needed for a strong match")
    parser.add_argument("--medium-confidence", type=float, help="Similarity needed for an ambiguous match")
    parser.add_argument("--min-quality-score", type=float, help="Minimum face quality allowed for adding")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    parser.add_argument("--metrics", action="store_true", help="Include timing and count metrics")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("init-db", help="Create or migrate the local database")
    backup_db = subcommands.add_parser("backup-db", help="Create a SQLite database backup")
    backup_db.add_argument("target", type=Path)
    subcommands.add_parser("profile", help="Show detected hardware and selected config")

    recognize = subcommands.add_parser("recognize", help="Run recognition")
    recognize.add_argument("image", type=Path)

    enroll = subcommands.add_parser("enroll", help="Create a person from the first face in an image")
    enroll.add_argument("name")
    enroll.add_argument("image", type=Path)
    enroll.add_argument("--force-bad-quality", action="store_true")

    queue = subcommands.add_parser("queue-add", help="Queue detected faces for review")
    queue.add_argument("image", type=Path)
    queue.add_argument("--force-bad-quality", action="store_true")

    subcommands.add_parser("pending", help="List queued face additions")

    confirm_new = subcommands.add_parser("confirm-new", help="Confirm a pending face as a new person")
    confirm_new.add_argument("pending_id")
    confirm_new.add_argument("name")

    confirm_existing = subcommands.add_parser(
        "confirm-existing",
        help="Confirm a pending face as an existing person embedding",
    )
    confirm_existing.add_argument("pending_id")
    confirm_existing.add_argument("person_id")

    reject = subcommands.add_parser("reject-pending", help="Reject a pending face addition")
    reject.add_argument("pending_id")

    init_scan = subcommands.add_parser("init-scan", help="Scan images and cluster faces for initial setup")
    init_scan.add_argument("source", type=Path)
    init_scan.add_argument("--force-bad-quality", action="store_true")

    init_groups = subcommands.add_parser("init-groups", help="List groups in an init session")
    init_groups.add_argument("session_id")

    init_confirm = subcommands.add_parser("init-confirm", help="Confirm an init group as a new person")
    init_confirm.add_argument("session_id")
    init_confirm.add_argument("group_id")
    init_confirm.add_argument("name")

    init_confirm_existing = subcommands.add_parser(
        "init-confirm-existing",
        help="Confirm an init group as embeddings for an existing person",
    )
    init_confirm_existing.add_argument("session_id")
    init_confirm_existing.add_argument("group_id")
    init_confirm_existing.add_argument("person_id")

    init_reject = subcommands.add_parser("init-reject", help="Reject an init group")
    init_reject.add_argument("session_id")
    init_reject.add_argument("group_id")

    init_reset = subcommands.add_parser("init-reset", help="Reset an init group to pending")
    init_reset.add_argument("session_id")
    init_reset.add_argument("group_id")

    subcommands.add_parser("persons", help="List active people")

    person = subcommands.add_parser("person", help="Show one person and embeddings")
    person.add_argument("person_id")

    rename = subcommands.add_parser("rename-person", help="Rename a person")
    rename.add_argument("person_id")
    rename.add_argument("name")

    delete_person = subcommands.add_parser("delete-person", help="Soft-delete a person")
    delete_person.add_argument("person_id")

    delete_embedding = subcommands.add_parser("delete-embedding", help="Delete one embedding")
    delete_embedding.add_argument("embedding_id")

    move_embedding = subcommands.add_parser("move-embedding", help="Move one embedding to another person")
    move_embedding.add_argument("embedding_id")
    move_embedding.add_argument("person_id")

    merge_persons = subcommands.add_parser("merge-persons", help="Merge source person into target person")
    merge_persons.add_argument("source_person_id")
    merge_persons.add_argument("target_person_id")

    benchmark = subcommands.add_parser("benchmark", help="Run repeated recognition benchmark")
    benchmark.add_argument("source", type=Path)
    benchmark.add_argument("--repeat", type=int, default=1)
    benchmark.add_argument(
        "--compare-threads",
        help="Comma-separated ONNX thread counts to compare, for example 1,2,4",
    )

    args = parser.parse_args()
    profile = _select_profile(args.profile)
    config = config_for_hardware(profile, data_dir=args.data_dir)

    try:
        config = _apply_runtime_overrides(config, args)
        if args.command == "profile":
            return _emit(
                args,
                {
                    "tier": profile.tier,
                    "cpu_count": profile.cpu_count,
                    "memory_gb": profile.memory_gb,
                    "reason": profile.reason,
                    "max_workers": config.max_workers,
                    "onnx_intra_threads": config.onnx_intra_threads,
                    "max_image_edge": config.max_image_edge,
                    "detector_input_size": config.detector_input_size,
                    "batch_size": config.batch_size,
                    "prefer_small_models": config.prefer_small_models,
                    "index_backend": config.index_backend,
                    "high_confidence": config.high_confidence,
                    "medium_confidence": config.medium_confidence,
                    "min_quality_score": config.min_quality_score,
                    "runtime": args.runtime,
                    "detector_model": str(config.detector_model),
                    "recognizer_model": str(config.recognizer_model),
                },
            )

        if args.command == "benchmark" and args.compare_threads:
            return _run_thread_comparison(args, config)

        engine = build_dev_engine(args.data_dir, config) if args.runtime == "dev" else build_onnx_engine(config)
        engine.initialize()
        if args.metrics:
            engine.reset_metrics()

        if args.command == "init-db":
            return _emit_engine(args, engine, {"initialized": str(args.data_dir)})

        if args.command == "backup-db":
            engine.backup_database(args.target)
            return _emit_engine(args, engine, {"backup": str(args.target)})

        if args.command == "recognize":
            results = engine.recognize(args.image)
            return _emit_engine(
                args,
                engine,
                {
                    "faces": [
                        {
                            "index": index,
                            "decision": result.decision.value,
                            "quality": _quality(result.quality),
                            "matches": _matches(engine, result.matches),
                        }
                        for index, result in enumerate(results, start=1)
                    ]
                },
            )

        if args.command == "enroll":
            additions = engine.prepare_additions(
                args.image,
                allow_bad_quality=args.force_bad_quality,
            )
            if not additions:
                return _emit_engine(args, engine, {"faces": []}, exit_code=1)
            person_id = engine.confirm_new_person(additions[0], args.name)
            return _emit_engine(
                args,
                engine,
                {
                    "person_id": person_id,
                    "embeddings": 1,
                    "quality": _quality(additions[0].quality),
                },
            )

        if args.command == "queue-add":
            prepared = engine.queue_additions(
                args.image,
                allow_bad_quality=args.force_bad_quality,
            )
            return _emit_engine(
                args,
                engine,
                {
                    "pending": [
                        {
                            "pending_id": pending.pending_id,
                            "decision": pending.decision.value,
                            "crop_path": pending.face.crop_path,
                            "quality": _quality(pending.quality),
                            "matches": _matches(engine, pending.matches),
                        }
                        for pending in prepared.accepted
                    ],
                    "rejected": [_rejected(rejected, index) for index, rejected in enumerate(prepared.rejected, start=1)],
                },
            )

        if args.command == "pending":
            additions = engine.list_pending_additions()
            return _emit_engine(
                args,
                engine,
                {
                    "pending": [
                        {
                            "pending_id": pending.pending_id,
                            "decision": pending.decision.value,
                            "source_image": pending.source_image,
                            "crop_path": pending.face.crop_path,
                            "quality": _quality(pending.quality),
                            "matches": _matches(engine, pending.matches),
                        }
                        for pending in additions
                    ]
                },
            )

        if args.command == "confirm-new":
            person_id = engine.confirm_pending_as_new_person(args.pending_id, args.name)
            return _emit_engine(args, engine, {"person_id": person_id, "confirmed": "new"})

        if args.command == "confirm-existing":
            embedding_id = engine.confirm_pending_as_existing_person(args.pending_id, args.person_id)
            return _emit_engine(args, engine, {"embedding_id": embedding_id, "confirmed": "existing"})

        if args.command == "reject-pending":
            engine.reject_pending_addition(args.pending_id)
            return _emit_engine(args, engine, {"rejected": 1})

        if args.command == "init-scan":
            session = engine.create_init_session(
                args.source,
                allow_bad_quality=args.force_bad_quality,
            )
            groups = engine.list_init_groups(session.session_id)
            return _emit_engine(
                args,
                engine,
                {
                    "session_id": session.session_id,
                    "groups": [_init_group(group) for group in groups],
                },
            )

        if args.command == "init-groups":
            groups = engine.list_init_groups(args.session_id)
            return _emit_engine(args, engine, {"groups": [_init_group(group) for group in groups]})

        if args.command == "init-confirm":
            person_id = engine.confirm_init_group(args.session_id, args.group_id, args.name)
            return _emit_engine(
                args,
                engine,
                {
                    "session_id": args.session_id,
                    "group_id": args.group_id,
                    "person_id": person_id,
                    "confirmed": "init_group",
                },
            )

        if args.command == "init-confirm-existing":
            embeddings = engine.confirm_init_group_existing(args.session_id, args.group_id, args.person_id)
            return _emit_engine(
                args,
                engine,
                {
                    "session_id": args.session_id,
                    "group_id": args.group_id,
                    "person_id": args.person_id,
                    "embeddings": embeddings,
                    "confirmed": "init_group_existing",
                },
            )

        if args.command == "init-reject":
            engine.reject_init_group(args.session_id, args.group_id)
            return _emit_engine(args, engine, {"session_id": args.session_id, "group_id": args.group_id, "rejected": 1})

        if args.command == "init-reset":
            engine.reset_init_group(args.session_id, args.group_id)
            return _emit_engine(args, engine, {"session_id": args.session_id, "group_id": args.group_id, "status": "pending"})

        if args.command == "persons":
            return _emit_engine(args, engine, {"persons": [_person_summary(summary) for summary in engine.list_persons()]})

        if args.command == "person":
            person = engine.get_person(args.person_id)
            if person is None:
                raise KeyError(f"Unknown person: {args.person_id}")
            embeddings = engine.list_person_embeddings(args.person_id)
            return _emit_engine(
                args,
                engine,
                {
                    "person": _person(person),
                    "embeddings": [_embedding(record) for record in embeddings],
                },
            )

        if args.command == "rename-person":
            engine.rename_person(args.person_id, args.name)
            return _emit_engine(args, engine, {"person_id": args.person_id, "renamed": args.name})

        if args.command == "delete-person":
            engine.delete_person(args.person_id)
            return _emit_engine(args, engine, {"person_id": args.person_id, "deleted": 1})

        if args.command == "delete-embedding":
            engine.delete_embedding(args.embedding_id)
            return _emit_engine(args, engine, {"embedding_id": args.embedding_id, "deleted": 1})

        if args.command == "move-embedding":
            engine.move_embedding(args.embedding_id, args.person_id)
            return _emit_engine(
                args,
                engine,
                {
                    "embedding_id": args.embedding_id,
                    "person_id": args.person_id,
                    "moved": 1,
                },
            )

        if args.command == "merge-persons":
            moved = engine.merge_persons(args.source_person_id, args.target_person_id)
            return _emit_engine(
                args,
                engine,
                {
                    "source_person_id": args.source_person_id,
                    "target_person_id": args.target_person_id,
                    "embeddings_moved": moved,
                    "merged": 1,
                },
            )

        if args.command == "benchmark":
            images = _image_paths(args.source)
            if not images:
                raise KeyError(f"No supported images found: {args.source}")
            if args.repeat < 1:
                raise KeyError("Repeat must be at least 1")
            started = perf_counter()
            faces_seen = 0
            for _ in range(args.repeat):
                for image_path in images:
                    faces_seen += len(engine.recognize(image_path))
            engine.metrics.timings_ms["total_benchmark_ms"] = (perf_counter() - started) * 1000.0
            engine.metrics.increment("benchmark_images", len(images))
            engine.metrics.increment("benchmark_repeat", args.repeat)
            engine.metrics.increment("benchmark_runs", len(images) * args.repeat)
            engine.metrics.increment("benchmark_faces", faces_seen)
            return _emit_engine(
                args,
                engine,
                {
                    "benchmark": {
                        "images": len(images),
                        "repeat": args.repeat,
                        "runs": len(images) * args.repeat,
                        "faces": faces_seen,
                    }
                },
            )

        return 1
    except SentriFaceError as exc:
        return _emit_error(args, str(exc))
    except KeyError as exc:
        return _emit_error(args, str(exc).strip("'"))


def _apply_runtime_overrides(config: RuntimeConfig, args: argparse.Namespace) -> RuntimeConfig:
    values = {
        **config.__dict__,
        "detector_model": args.detector_model,
        "recognizer_model": args.recognizer_model,
        "onnx_intra_threads": args.onnx_threads or config.onnx_intra_threads,
        "max_image_edge": args.max_image_edge or config.max_image_edge,
        "high_confidence": args.high_confidence if args.high_confidence is not None else config.high_confidence,
        "medium_confidence": args.medium_confidence if args.medium_confidence is not None else config.medium_confidence,
        "min_quality_score": args.min_quality_score if args.min_quality_score is not None else config.min_quality_score,
    }
    _validate_positive_int("onnx threads", values["onnx_intra_threads"])
    _validate_positive_int("max image edge", values["max_image_edge"])
    _validate_unit_interval("high confidence", values["high_confidence"])
    _validate_unit_interval("medium confidence", values["medium_confidence"])
    _validate_unit_interval("min quality score", values["min_quality_score"])
    if values["medium_confidence"] > values["high_confidence"]:
        raise KeyError("Medium confidence must be less than or equal to high confidence")
    return RuntimeConfig(**values)


def _validate_positive_int(name: str, value: int) -> None:
    if value < 1:
        raise KeyError(f"{name.title()} must be at least 1")


def _validate_unit_interval(name: str, value: float) -> None:
    if value < 0.0 or value > 1.0:
        raise KeyError(f"{name.title()} must be between 0 and 1")


def _select_profile(profile_name: str):
    if profile_name == "auto":
        return assess_hardware()
    forced = {
        "low": HardwareProfile(
            cpu_count=4,
            memory_gb=4.0,
            tier="low",
            reason="forced low profile",
        ),
        "medium": HardwareProfile(
            cpu_count=8,
            memory_gb=8.0,
            tier="medium",
            reason="forced medium profile",
        ),
        "high": HardwareProfile(
            cpu_count=12,
            memory_gb=16.0,
            tier="high",
            reason="forced high profile",
        ),
    }
    return forced[profile_name]


def _emit(args, payload: dict[str, Any], exit_code: int = 0) -> int:
    if args.json:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        _print_human(payload)
    return exit_code


def _emit_engine(args, engine: FaceEngine, payload: dict[str, Any], exit_code: int = 0) -> int:
    if args.metrics:
        payload = {**payload, "metrics": engine.metrics_snapshot()}
    return _emit(args, payload, exit_code)


def _emit_error(args, message: str) -> int:
    if args.json:
        print(json.dumps({"error": message}, separators=(",", ":")))
    else:
        print(f"error={message}")
    return 1


def _run_thread_comparison(args, base_config: RuntimeConfig) -> int:
    if args.runtime != "onnx":
        return _emit_error(args, "--compare-threads requires --runtime onnx")
    thread_counts = [
        int(value.strip())
        for value in args.compare_threads.split(",")
        if value.strip()
    ]
    if not thread_counts or any(value < 1 for value in thread_counts):
        return _emit_error(args, "Thread counts must be positive integers")

    images = _image_paths(args.source)
    if not images:
        return _emit_error(args, f"No supported images found: {args.source}")
    if args.repeat < 1:
        return _emit_error(args, "Repeat must be at least 1")

    results = []
    for threads in thread_counts:
        config = RuntimeConfig(**{**base_config.__dict__, "onnx_intra_threads": threads})
        engine = build_onnx_engine(config)
        engine.initialize()
        engine.reset_metrics()
        started = perf_counter()
        faces_seen = 0
        for _ in range(args.repeat):
            for image_path in images:
                faces_seen += len(engine.recognize(image_path))
        engine.metrics.timings_ms["total_benchmark_ms"] = (perf_counter() - started) * 1000.0
        engine.metrics.increment("benchmark_images", len(images))
        engine.metrics.increment("benchmark_repeat", args.repeat)
        engine.metrics.increment("benchmark_runs", len(images) * args.repeat)
        engine.metrics.increment("benchmark_faces", faces_seen)
        results.append(
            {
                "onnx_intra_threads": threads,
                "benchmark": {
                    "images": len(images),
                    "repeat": args.repeat,
                    "runs": len(images) * args.repeat,
                    "faces": faces_seen,
                },
                "metrics": engine.metrics_snapshot(),
            }
        )
    return _emit(args, {"thread_comparison": results})


def _print_human(payload: dict[str, Any]) -> None:
    if "thread_comparison" in payload:
        for item in payload["thread_comparison"]:
            print(f"onnx_intra_threads={item['onnx_intra_threads']}")
            benchmark = item["benchmark"]
            print(
                f"benchmark.images={benchmark['images']} "
                f"benchmark.repeat={benchmark['repeat']} "
                f"benchmark.runs={benchmark['runs']} "
                f"benchmark.faces={benchmark['faces']}"
            )
            _print_metrics(item["metrics"])
        return
    if "faces" in payload:
        faces = payload["faces"]
        if not faces:
            print("faces=0")
            if "metrics" in payload:
                _print_metrics(payload["metrics"])
            return
        for face in faces:
            print(
                f"face={face['index']} decision={face['decision']} "
                f"quality={face['quality']['status']} quality_score={face['quality']['score']:.3f} "
                f"matches={len(face['matches'])}"
            )
            _print_reasons(face["quality"]["reasons"])
            _print_match_rows(face["matches"])
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "pending" in payload:
        pending = payload["pending"]
        rejected = payload.get("rejected", [])
        if not pending and not rejected:
            print("pending=0")
            if "metrics" in payload:
                _print_metrics(payload["metrics"])
            return
        for item in pending:
            print(
                f"pending_id={item['pending_id']} decision={item['decision']} "
                f"quality={item['quality']['status']} quality_score={item['quality']['score']:.3f} "
                f"source={item.get('source_image', '')} crop={item.get('crop_path')} "
                f"matches={len(item['matches'])}"
            )
            _print_reasons(item["quality"]["reasons"])
            _print_match_rows(item["matches"])
        for item in rejected:
            print(
                f"rejected face={item['index']} quality={item['quality']['status']} "
                f"quality_score={item['quality']['score']:.3f}"
            )
            _print_reasons(item["quality"]["reasons"])
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "groups" in payload:
        if "session_id" in payload:
            print(f"session_id={payload['session_id']}")
        groups = payload["groups"]
        if not groups:
            print("groups=0")
            if "metrics" in payload:
                _print_metrics(payload["metrics"])
            return
        for group in groups:
            print(
                f"group_id={group['group_id']} status={group['status']} "
                f"faces={len(group['faces'])} avg_quality={group['avg_quality']:.3f}"
            )
            for face in group["faces"]:
                print(
                    f"  face_id={face['init_face_id']} source={face['source_image']} "
                    f"crop={face['crop_path']} "
                    f"quality={face['quality']['status']} quality_score={face['quality']['score']:.3f}"
                )
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "persons" in payload:
        persons = payload["persons"]
        if not persons:
            print("persons=0")
            if "metrics" in payload:
                _print_metrics(payload["metrics"])
            return
        for item in persons:
            print(
                f"person_id={item['person_id']} name={item['name']} "
                f"embeddings={item['embedding_count']}"
            )
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "person" in payload:
        person = payload["person"]
        embeddings = payload["embeddings"]
        print(f"person_id={person['person_id']} name={person['name']} embeddings={len(embeddings)}")
        for embedding in embeddings:
            print(
                f"  embedding_id={embedding['embedding_id']} "
                f"quality_score={embedding['quality_score']:.3f} "
                f"source={embedding['source_image']}"
            )
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "benchmark" in payload:
        benchmark = payload["benchmark"]
        print(
            f"benchmark.images={benchmark['images']} "
            f"benchmark.repeat={benchmark['repeat']} "
            f"benchmark.runs={benchmark['runs']} "
            f"benchmark.faces={benchmark['faces']}"
        )
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "quality" in payload:
        quality = payload["quality"]
        for key, value in payload.items():
            if key == "quality":
                print(f"quality={quality['status']} quality_score={quality['score']:.3f}")
                _print_reasons(quality["reasons"])
            elif key == "metrics":
                continue
            else:
                print(f"{key}={value}")
        if "metrics" in payload:
            _print_metrics(payload["metrics"])
        return
    if "metrics" in payload:
        _print_metrics(payload["metrics"])
        return
    for key, value in payload.items():
        if key == "metrics":
            _print_metrics(value)
        else:
            print(f"{key}={value}")


def _matches(engine: FaceEngine, matches: list[PersonMatch]) -> list[dict[str, Any]]:
    rows = []
    for rank, match in enumerate(matches, start=1):
        person = engine.get_person(match.person_id)
        rows.append(
            {
                "rank": rank,
                "person_id": match.person_id,
                "name": person.name if person else "unknown",
                "score": match.score,
                "embedding_ids": list(match.embedding_ids),
                "embeddings_matched": match.embeddings_matched,
            }
        )
    return rows


def _quality(report) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "status": report.status.value,
        "score": report.score,
        "reasons": list(report.reasons),
    }


def _rejected(rejected, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "source_image": rejected.source_image,
        "quality": _quality(rejected.quality),
    }


def _init_group(group) -> dict[str, Any]:
    qualities = [face.quality.score for face in group.faces]
    avg_quality = sum(qualities) / len(qualities) if qualities else 0.0
    return {
        "group_id": group.group_id,
        "session_id": group.session_id,
        "status": group.status,
        "avg_quality": avg_quality,
        "faces": [
            {
                "init_face_id": face.init_face_id,
                "source_image": face.source_image,
                "crop_path": face.face.crop_path,
                "quality": _quality(face.quality),
            }
            for face in group.faces
        ],
    }


def _print_reasons(reasons: list[str]) -> None:
    if reasons:
        print(f"  reasons={','.join(reasons)}")


def _print_metrics(metrics: dict[str, Any]) -> None:
    for key, value in metrics.get("timings_ms", {}).items():
        print(f"metrics.{key}={value:.3f}")
    for key, value in metrics.get("counts", {}).items():
        print(f"metrics.{key}={value}")


def _image_paths(source: Path) -> list[Path]:
    if source.is_file():
        return [source] if source.suffix.lower() in IMAGE_EXTENSIONS else []
    if not source.exists():
        raise KeyError(f"Source path does not exist: {source}")
    return sorted(
        path
        for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _print_match_rows(matches: list[dict[str, Any]]) -> None:
    for match in matches:
        print(
            f"  match={match['rank']} person_id={match['person_id']} "
            f"name={match['name']} score={match['score']:.4f} "
            f"embeddings_matched={match['embeddings_matched']} "
            f"embedding_ids={','.join(match['embedding_ids'])}"
        )


def _person_summary(summary) -> dict[str, Any]:
    return {
        "person_id": summary.person.person_id,
        "name": summary.person.name,
        "metadata": summary.person.metadata,
        "created_at": summary.person.created_at,
        "embedding_count": summary.embedding_count,
    }


def _person(person) -> dict[str, Any]:
    return {
        "person_id": person.person_id,
        "name": person.name,
        "metadata": person.metadata,
        "created_at": person.created_at,
    }


def _embedding(record) -> dict[str, Any]:
    return {
        "embedding_id": record.embedding_id,
        "person_id": record.person_id,
        "quality_score": record.quality_score,
        "source_image": record.source_image,
        "crop_path": record.crop_path,
        "created_at": record.created_at,
    }


if __name__ == "__main__":
    raise SystemExit(main())
