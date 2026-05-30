from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentriface.components.dev_components import HashFaceEmbedder, WholeImageFaceDetector
from sentriface.components.linear_index import LinearFaceIndex
from sentriface.components.onnx_components import OnnxArcFaceEmbedder, OnnxScrfdDetector
from sentriface.config import HardwareProfile, RuntimeConfig, config_for_hardware
from sentriface.engine import FaceEngine
from sentriface.errors import SentriFaceError
from sentriface.hardware import assess_hardware
from sentriface.models import Match
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
            intra_op_threads=config.max_workers,
        ),
        embedder=OnnxArcFaceEmbedder(
            model_path=config.recognizer_model,
            intra_op_threads=config.max_workers,
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
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("init-db", help="Create or migrate the local database")
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

    init_reject = subcommands.add_parser("init-reject", help="Reject an init group")
    init_reject.add_argument("session_id")
    init_reject.add_argument("group_id")

    args = parser.parse_args()
    profile = _select_profile(args.profile)
    config = config_for_hardware(profile, data_dir=args.data_dir)
    config = RuntimeConfig(
        **{
            **config.__dict__,
            "detector_model": args.detector_model,
            "recognizer_model": args.recognizer_model,
        }
    )

    try:
        if args.command == "profile":
            return _emit(
                args,
                {
                    "tier": profile.tier,
                    "cpu_count": profile.cpu_count,
                    "memory_gb": profile.memory_gb,
                    "reason": profile.reason,
                    "max_workers": config.max_workers,
                    "max_image_edge": config.max_image_edge,
                    "detector_input_size": config.detector_input_size,
                    "batch_size": config.batch_size,
                    "prefer_small_models": config.prefer_small_models,
                    "index_backend": config.index_backend,
                    "runtime": args.runtime,
                    "detector_model": str(config.detector_model),
                    "recognizer_model": str(config.recognizer_model),
                },
            )

        engine = build_dev_engine(args.data_dir, config) if args.runtime == "dev" else build_onnx_engine(config)
        engine.initialize()

        if args.command == "init-db":
            return _emit(args, {"initialized": str(args.data_dir)})

        if args.command == "recognize":
            results = engine.recognize(args.image)
            return _emit(
                args,
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
                return _emit(args, {"faces": []}, exit_code=1)
            person_id = engine.confirm_new_person(additions[0], args.name)
            return _emit(
                args,
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
            return _emit(
                args,
                {
                    "pending": [
                        {
                            "pending_id": pending.pending_id,
                            "decision": pending.decision.value,
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
            return _emit(
                args,
                {
                    "pending": [
                        {
                            "pending_id": pending.pending_id,
                            "decision": pending.decision.value,
                            "source_image": pending.source_image,
                            "quality": _quality(pending.quality),
                            "matches": _matches(engine, pending.matches),
                        }
                        for pending in additions
                    ]
                },
            )

        if args.command == "confirm-new":
            person_id = engine.confirm_pending_as_new_person(args.pending_id, args.name)
            return _emit(args, {"person_id": person_id, "confirmed": "new"})

        if args.command == "confirm-existing":
            embedding_id = engine.confirm_pending_as_existing_person(args.pending_id, args.person_id)
            return _emit(args, {"embedding_id": embedding_id, "confirmed": "existing"})

        if args.command == "reject-pending":
            engine.reject_pending_addition(args.pending_id)
            return _emit(args, {"rejected": 1})

        if args.command == "init-scan":
            session = engine.create_init_session(
                args.source,
                allow_bad_quality=args.force_bad_quality,
            )
            groups = engine.list_init_groups(session.session_id)
            return _emit(
                args,
                {
                    "session_id": session.session_id,
                    "groups": [_init_group(group) for group in groups],
                },
            )

        if args.command == "init-groups":
            groups = engine.list_init_groups(args.session_id)
            return _emit(args, {"groups": [_init_group(group) for group in groups]})

        if args.command == "init-confirm":
            person_id = engine.confirm_init_group(args.session_id, args.group_id, args.name)
            return _emit(
                args,
                {
                    "session_id": args.session_id,
                    "group_id": args.group_id,
                    "person_id": person_id,
                    "confirmed": "init_group",
                },
            )

        if args.command == "init-reject":
            engine.reject_init_group(args.session_id, args.group_id)
            return _emit(args, {"session_id": args.session_id, "group_id": args.group_id, "rejected": 1})

        return 1
    except SentriFaceError as exc:
        return _emit_error(args, str(exc))
    except KeyError as exc:
        return _emit_error(args, str(exc).strip("'"))


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


def _emit_error(args, message: str) -> int:
    if args.json:
        print(json.dumps({"error": message}, separators=(",", ":")))
    else:
        print(f"error={message}")
    return 1


def _print_human(payload: dict[str, Any]) -> None:
    if "faces" in payload:
        faces = payload["faces"]
        if not faces:
            print("faces=0")
            return
        for face in faces:
            print(
                f"face={face['index']} decision={face['decision']} "
                f"quality={face['quality']['status']} quality_score={face['quality']['score']:.3f} "
                f"matches={len(face['matches'])}"
            )
            _print_reasons(face["quality"]["reasons"])
            _print_match_rows(face["matches"])
        return
    if "pending" in payload:
        pending = payload["pending"]
        rejected = payload.get("rejected", [])
        if not pending and not rejected:
            print("pending=0")
            return
        for item in pending:
            print(
                f"pending_id={item['pending_id']} decision={item['decision']} "
                f"quality={item['quality']['status']} quality_score={item['quality']['score']:.3f} "
                f"source={item.get('source_image', '')} matches={len(item['matches'])}"
            )
            _print_reasons(item["quality"]["reasons"])
            _print_match_rows(item["matches"])
        for item in rejected:
            print(
                f"rejected face={item['index']} quality={item['quality']['status']} "
                f"quality_score={item['quality']['score']:.3f}"
            )
            _print_reasons(item["quality"]["reasons"])
        return
    if "groups" in payload:
        if "session_id" in payload:
            print(f"session_id={payload['session_id']}")
        groups = payload["groups"]
        if not groups:
            print("groups=0")
            return
        for group in groups:
            print(
                f"group_id={group['group_id']} status={group['status']} "
                f"faces={len(group['faces'])} avg_quality={group['avg_quality']:.3f}"
            )
            for face in group["faces"]:
                print(
                    f"  face_id={face['init_face_id']} source={face['source_image']} "
                    f"quality={face['quality']['status']} quality_score={face['quality']['score']:.3f}"
                )
        return
    for key, value in payload.items():
        print(f"{key}={value}")


def _matches(engine: FaceEngine, matches: list[Match]) -> list[dict[str, Any]]:
    rows = []
    for rank, match in enumerate(matches, start=1):
        person = engine.get_person(match.person_id)
        rows.append(
            {
                "rank": rank,
                "person_id": match.person_id,
                "name": person.name if person else "unknown",
                "score": match.score,
                "embedding_id": match.embedding_id,
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
                "quality": _quality(face.quality),
            }
            for face in group.faces
        ],
    }


def _print_reasons(reasons: list[str]) -> None:
    if reasons:
        print(f"  reasons={','.join(reasons)}")


def _print_match_rows(matches: list[dict[str, Any]]) -> None:
    for match in matches:
        print(
            f"  match={match['rank']} person_id={match['person_id']} "
            f"name={match['name']} score={match['score']:.4f} embedding_id={match['embedding_id']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
