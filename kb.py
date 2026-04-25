import argparse
from datetime import datetime
import json
import os
import subprocess
import re
import yaml
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ROOT_DIR = Path(__file__).resolve().parent


FEISHU_SYNC_ENABLED = False


def _check_feishu_sync():
    global FEISHU_SYNC_ENABLED
    if FEISHU_SYNC_ENABLED:
        return True
    config_path = ROOT_DIR / "data" / "feishu-config.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if config.get("space_id"):
                FEISHU_SYNC_ENABLED = True
                return True
        except Exception:
            pass
    return False


def _try_feishu_sync(entry_id: str, kind: str = "knowledge"):
    if not _check_feishu_sync():
        return
    try:
        feishu_py = str(ROOT_DIR / "feishu.py")
        subprocess.run(
            [sys.executable, feishu_py, "sync", "--id", entry_id, "--kind", kind],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def _check_feishu_duplicate(topic: str, kind: str = "knowledge") -> tuple:
    """Check if a document with the same topic already exists in Feishu.
    Returns (exists: bool, node_token: str, doc_id: str, action: str)
    """
    if not _check_feishu_sync():
        return (False, "", "", "")
    try:
        feishu_py = str(ROOT_DIR / "feishu.py")
        result = subprocess.run(
            [sys.executable, feishu_py, "sync", "--dry-run", "--kind", kind],
            capture_output=True,
            timeout=30,
            encoding="utf-8",
        )
        output = result.stdout.strip()
        if not output:
            return (False, "", "", "")
        # Parse dry-run output to find matching topic
        for line in output.split("\n"):
            if topic in line:
                if "[UPDATE]" in line:
                    return (True, "", "", "update")
                elif "[CREATE]" in line:
                    return (False, "", "", "create")
    except Exception:
        pass
    return (False, "", "", "")


HELP_TEXT = """knowledge-system kb.py

Skill-local data IO tool.
AI is responsible for searching, analysis, lesson-plan writing, teaching, and dialogue.
This script only reads, writes, appends, lists, and organizes data under the skill root.

Commands:
  init
  list --path <relative_path>
  read --path <relative_path>
  write --path <relative_path> [--content <text> | --stdin]
  append --path <relative_path> [--content <text> | --stdin]
  read-json --path <relative_path>
  write-json --path <relative_path> [--content <json_text> | --stdin]
  mkdir --path <relative_path>
  exists --path <relative_path>
  delete --path <relative_path>
  save-plan --topic <topic> [--id <plan_id>] [--goal <goal>] [--status <status>] [--basis <text>] [--baseline <text>] [--resume-from <text>] [--content <text> | --stdin]
  get-plan --id <plan_id>
  list-plans [--status <status>] [--topic <text>] [--sort updated_at|created_at|topic] [--desc]
  update-plan-status --id <plan_id> --status <status>
  update-units --id <plan_id> --content <json_text> | --stdin
  set-resume --id <plan_id> --resume-from <text>
  record-progress --plan-id <plan_id> --unit <unit_name> --status <status> [--summary <text>] [--next <text>] [--mastered <text>] [--weak <text>]
  upsert-progress --plan-id <plan_id> --unit <unit_name> --status <status> [--summary <text>] [--next <text>] [--mastered <text>] [--weak <text>]
  save-lesson --topic <topic> [--id <lesson_id>] [--plan-id <plan_id>] [--unit <unit_name>] [--goal <text>] [--content <text> | --stdin]
  get-lesson --id <lesson_id>
  list-lessons [--plan-id <plan_id>] [--status <status>] [--topic <text>] [--sort updated_at|created_at|topic] [--desc]
  update-lesson --id <lesson_id> [--topic <topic>] [--goal <text>] [--status <status>] [--mastered <csv>] [--weak <csv>] [--next <text>] [--content <text> | --stdin]
  complete-lesson --id <lesson_id> [--status <status>]
  save-digest --topic <topic> [--id <digest_id>] [--goal <text>] [--source-plan <plan_id>] [--status <status>] [--content <text> | --stdin]
  get-digest --id <digest_id>
  list-digests [--status <status>] [--topic <text>] [--sort updated_at|created_at|topic] [--desc]
  update-digest --id <digest_id> [--topic <topic>] [--goal <text>] [--status <status>] [--confirmed <csv>] [--pending <csv>] [--content <text> | --stdin]
  complete-digest --id <digest_id> --topic <topic> [--summary <text>] [--tags <csv>] [--content <text> | --stdin]
  save-knowledge --topic <topic> [--id <knowledge_id>] [--summary <text>] [--tags <csv>] [--parent <text>] [--prerequisites <csv>] [--related <csv>] [--content <text> | --stdin]
  get-knowledge --id <knowledge_id>
  list-knowledge [--tag <tag>] [--topic <text>] [--sort updated_at|created_at|topic] [--desc]
  update-knowledge --id <knowledge_id> [--topic <topic>] [--summary <text>] [--tags <csv>] [--parent <text>] [--prerequisites <csv>] [--related <csv>] [--content <text> | --stdin]
  add-memo --type <idea|todo|flash> --title <title> [--id <memo_id>] [--status <status>] [--priority <low|medium|high>] [--deadline <yyyy-mm-dd>] [--content <text> | --stdin]
  get-memo --id <memo_id>
  list-memos [--type <type>] [--status <status>] [--priority <priority>] [--sort updated_at|created_at|title|deadline] [--desc]
  update-memo --id <memo_id> [--title <title>] [--status <status>] [--priority <priority>] [--deadline <yyyy-mm-dd>] [--content <text> | --stdin]
  search --kind <plans|lessons|digests|knowledge|memos|all> --query <text>
  backlinks --query <topic>
  due-reviews [--days <n>]
  record-review --id <knowledge_id>
  reset-review --id <knowledge_id>
  tree-roots
  tree-children --parent <topic>
  tree-summary
  tree-check [--threshold <n>]
  agenda [--days <n>]
"""


DATA_DIR = ROOT_DIR / "data"
PLANS_DIR = DATA_DIR / "plans"
LESSONS_DIR = DATA_DIR / "lessons"
DIGESTS_DIR = DATA_DIR / "digests"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
MEMOS_DIR = DATA_DIR / "memos"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


REVIEW_INTERVALS = [1, 2, 4, 7, 15, 30]


def next_review_date(learned_at: str, review_count: int) -> str:
    from datetime import timedelta

    base = datetime.fromisoformat(learned_at)
    idx = min(review_count, len(REVIEW_INTERVALS) - 1)
    delta = timedelta(days=REVIEW_INTERVALS[idx])
    return (base + delta).isoformat(timespec="seconds")


def ensure_data_dirs() -> None:
    for path in [
        DATA_DIR,
        PLANS_DIR,
        LESSONS_DIR,
        DIGESTS_DIR,
        KNOWLEDGE_DIR,
        MEMOS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def generate_id(prefix: str) -> str:
    import time

    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"


def split_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def write_record(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = payload.get("content", "")
    metadata = {
        k: v
        for k, v in payload.items()
        if k != "content" and v is not None and v != "" and v != []
    }
    for k, v in payload.items():
        if k == "content":
            continue
        metadata[k] = v
    frontmatter = yaml.dump(
        metadata, allow_unicode=True, default_flow_style=False, sort_keys=False
    )
    content = f"---\n{frontmatter}---\n{body}"
    path.write_text(content, encoding="utf-8")


def read_record(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    metadata = {}
    body = ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            metadata = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
    else:
        body = text
    metadata["content"] = body
    return metadata


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def text_matches(values: list[str], query: str) -> bool:
    haystack = " ".join(value for value in values if value).lower()
    return query.lower() in haystack


def summarize_record(kind: str, data: dict) -> dict:
    if kind == "plans":
        return {
            "kind": kind,
            "id": data.get("id"),
            "topic": data.get("topic"),
            "status": data.get("status"),
            "updated_at": data.get("updated_at"),
        }
    if kind == "digests":
        return {
            "kind": kind,
            "id": data.get("id"),
            "topic": data.get("topic"),
            "status": data.get("status"),
            "source_plan": data.get("source_plan"),
            "source_lesson": data.get("source_lesson"),
            "updated_at": data.get("updated_at"),
        }
    if kind == "lessons":
        return {
            "kind": kind,
            "id": data.get("id"),
            "topic": data.get("topic"),
            "plan_id": data.get("plan_id"),
            "unit": data.get("unit"),
            "status": data.get("status"),
            "updated_at": data.get("updated_at"),
        }
    if kind == "knowledge":
        return {
            "kind": kind,
            "id": data.get("id"),
            "topic": data.get("topic"),
            "tags": data.get("tags", []),
            "parent": data.get("parent", ""),
            "related": data.get("related", []),
            "updated_at": data.get("updated_at"),
        }
    return {
        "kind": kind,
        "id": data.get("id"),
        "title": data.get("title"),
        "type": data.get("type"),
        "status": data.get("status"),
        "updated_at": data.get("updated_at"),
    }


def sort_records(records: list[dict], field: str, desc: bool) -> list[dict]:
    return sorted(
        records,
        key=lambda item: (
            (item.get(field) or "").lower()
            if isinstance(item.get(field), str)
            else item.get(field) or ""
        ),
        reverse=desc,
    )


def resolve_path(relative_path: str) -> Path:
    candidate = (ROOT_DIR / relative_path).resolve()
    if ROOT_DIR not in candidate.parents and candidate != ROOT_DIR:
        raise ValueError("path must stay inside skill root")
    return candidate


def get_content(args: argparse.Namespace) -> str:
    if getattr(args, "stdin", False):
        return sys.stdin.buffer.read().decode("utf-8")
    return args.content or ""


def cmd_init(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    print_json(
        {
            "root": str(ROOT_DIR),
            "storage": "markdown",
            "data": "data/",
            "plans": "data/plans/",
            "lessons": "data/lessons/",
            "digests": "data/digests/",
            "knowledge": "data/knowledge/",
            "memos": "data/memos/",
        }
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    if not target.exists():
        print(f"NOT_FOUND\t{args.path}")
        return 1
    if not target.is_dir():
        print(f"NOT_DIR\t{args.path}")
        return 1

    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        suffix = "/" if entry.is_dir() else ""
        print(f"{entry.relative_to(ROOT_DIR).as_posix()}{suffix}")
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    if not target.exists() or not target.is_file():
        print(f"NOT_FOUND\t{args.path}")
        return 1
    sys.stdout.write(target.read_text(encoding="utf-8"))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(get_content(args), encoding="utf-8")
    print(target.relative_to(ROOT_DIR).as_posix())
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(get_content(args))
    print(target.relative_to(ROOT_DIR).as_posix())
    return 0


def cmd_read_json(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    if not target.exists() or not target.is_file():
        print(f"NOT_FOUND\t{args.path}")
        return 1
    data = json.loads(target.read_text(encoding="utf-8"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_write_json(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = get_content(args)
    data = json.loads(raw)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target.relative_to(ROOT_DIR).as_posix())
    return 0


def cmd_mkdir(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    target.mkdir(parents=True, exist_ok=True)
    print(target.relative_to(ROOT_DIR).as_posix())
    return 0


def cmd_exists(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    print("true" if target.exists() else "false")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    target = resolve_path(args.path)
    if not target.exists():
        print(f"NOT_FOUND\t{args.path}")
        return 1
    if target.is_dir():
        for child in sorted(target.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        target.rmdir()
    else:
        target.unlink()
    print(args.path)
    return 0


def cmd_save_plan(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    plan_id = args.id or generate_id("plan")
    path = PLANS_DIR / f"{plan_id}.md"
    existing = read_record(path) if path.exists() else {}
    content = get_content(args)
    payload = {
        "id": plan_id,
        "topic": args.topic,
        "goal": args.goal or existing.get("goal", ""),
        "status": args.status or existing.get("status", "active"),
        "basis": args.basis if args.basis is not None else existing.get("basis", ""),
        "baseline": args.baseline
        if args.baseline is not None
        else existing.get("baseline", ""),
        "units": existing.get("units", []),
        "resume_from": args.resume_from
        if args.resume_from is not None
        else existing.get("resume_from", ""),
        "adjustments": existing.get("adjustments", []),
        "updated_at": now_iso(),
        "created_at": existing.get("created_at", now_iso()),
        "content": content if content else existing.get("content", ""),
        "progress": existing.get("progress", []),
    }
    write_record(path, payload)
    _try_feishu_sync(plan_id, kind="plans")
    print_json(payload)
    return 0


def cmd_get_plan(args: argparse.Namespace) -> int:
    path = PLANS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    print_json(read_record(path))
    return 0


def cmd_list_plans(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    records = []
    for path in sorted(PLANS_DIR.glob("*.md")):
        data = read_record(path)
        if args.status and data.get("status") != args.status:
            continue
        if args.topic and args.topic.lower() not in (data.get("topic") or "").lower():
            continue
        records.append(
            {
                "id": data.get("id"),
                "topic": data.get("topic"),
                "status": data.get("status"),
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
            }
        )
    records = sort_records(records, args.sort, args.desc)
    print_json(records)
    return 0


def cmd_update_plan_status(args: argparse.Namespace) -> int:
    path = PLANS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    data["status"] = args.status
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="plans")
    print_json(data)
    return 0


def cmd_update_units(args: argparse.Namespace) -> int:
    path = PLANS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    content = get_content(args)
    units = json.loads(content)
    if not isinstance(units, list):
        print("ERROR\tunits must be a JSON array")
        return 1
    data["units"] = units
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="plans")
    print_json(data)
    return 0


def cmd_set_resume(args: argparse.Namespace) -> int:
    path = PLANS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    data["resume_from"] = args.resume_from
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="plans")
    print_json(data)
    return 0


def _sync_unit_status(data: dict, unit_name: str, status: str) -> None:
    for unit in data.get("units", []):
        if unit.get("name") == unit_name:
            unit["status"] = status
            return


def cmd_record_progress(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    path = PLANS_DIR / f"{args.plan_id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.plan_id}")
        return 1

    data = read_record(path)
    progress_entry = {
        "recorded_at": now_iso(),
        "unit": args.unit,
        "status": args.status,
        "summary": args.summary or "",
        "next": args.next or "",
        "mastered": split_csv(args.mastered),
        "weak": split_csv(args.weak),
    }
    data.setdefault("progress", []).append(progress_entry)
    _sync_unit_status(data, args.unit, args.status)
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.plan_id, kind="plans")
    print_json(data)
    return 0


def cmd_upsert_progress(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    path = PLANS_DIR / f"{args.plan_id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.plan_id}")
        return 1

    data = read_record(path)
    progress_list = data.setdefault("progress", [])
    content = {
        "recorded_at": now_iso(),
        "unit": args.unit,
        "status": args.status,
        "summary": args.summary or "",
        "next": args.next or "",
        "mastered": split_csv(args.mastered),
        "weak": split_csv(args.weak),
    }

    replaced = False
    for index, item in enumerate(progress_list):
        if item.get("unit") == args.unit:
            progress_list[index] = content
            replaced = True
            break

    if not replaced:
        progress_list.append(content)

    _sync_unit_status(data, args.unit, args.status)
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.plan_id, kind="plans")
    print_json(content)
    return 0


def cmd_save_lesson(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    lesson_id = args.id or generate_id("lesson")
    path = LESSONS_DIR / f"{lesson_id}.md"
    existing = read_record(path) if path.exists() else {}
    content = get_content(args)
    payload = {
        "id": lesson_id,
        "plan_id": args.plan_id or existing.get("plan_id", ""),
        "unit": args.unit or existing.get("unit", ""),
        "topic": args.topic,
        "goal": args.goal or existing.get("goal", ""),
        "status": existing.get("status", "in_progress"),
        "mastered": existing.get("mastered", []),
        "weak": existing.get("weak", []),
        "next": existing.get("next", ""),
        "content": content if content else existing.get("content", ""),
        "updated_at": now_iso(),
        "created_at": existing.get("created_at", now_iso()),
    }
    write_record(path, payload)
    _try_feishu_sync(lesson_id, kind="lessons")
    print_json(payload)
    return 0


def cmd_get_lesson(args: argparse.Namespace) -> int:
    path = LESSONS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    print_json(read_record(path))
    return 0


def cmd_list_lessons(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    records = []
    for path in sorted(LESSONS_DIR.glob("*.md")):
        data = read_record(path)
        if args.plan_id and data.get("plan_id") != args.plan_id:
            continue
        if args.status and data.get("status") != args.status:
            continue
        if args.topic and args.topic.lower() not in (data.get("topic") or "").lower():
            continue
        records.append(
            {
                "id": data.get("id"),
                "topic": data.get("topic"),
                "plan_id": data.get("plan_id"),
                "unit": data.get("unit"),
                "status": data.get("status"),
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
            }
        )
    records = sort_records(records, args.sort, args.desc)
    print_json(records)
    return 0


def cmd_update_lesson(args: argparse.Namespace) -> int:
    path = LESSONS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    content = get_content(args)
    if args.topic:
        data["topic"] = args.topic
    if args.goal is not None:
        data["goal"] = args.goal
    if args.status:
        data["status"] = args.status
    if args.mastered is not None:
        data["mastered"] = split_csv(args.mastered)
    if args.weak is not None:
        data["weak"] = split_csv(args.weak)
    if args.next is not None:
        data["next"] = args.next
    if content:
        data["content"] = content
    data["updated_at"] = now_iso()
    write_record(path, data)
    print_json(data)
    return 0


def cmd_complete_lesson(args: argparse.Namespace) -> int:
    path = LESSONS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    lesson_status = args.status or "mastered"
    data["status"] = "completed"
    data["updated_at"] = now_iso()
    write_record(path, data)

    if data.get("plan_id") and data.get("unit"):
        plan_path = PLANS_DIR / f"{data['plan_id']}.md"
        if plan_path.exists():
            plan_data = read_record(plan_path)
            _sync_unit_status(plan_data, data["unit"], lesson_status)

            units = plan_data.get("units", [])
            if isinstance(units, str):
                try:
                    units = json.loads(units)
                except (json.JSONDecodeError, TypeError):
                    units = []
            plan_data["units"] = units

            remaining = [u for u in units if u.get("status") not in ("mastered", "completed")]
            if remaining:
                plan_data["resume_from"] = remaining[0].get("name", "")
            else:
                plan_data["status"] = "completed"
                plan_data["resume_from"] = ""

            plan_data["updated_at"] = now_iso()
            write_record(plan_path, plan_data)
            _try_feishu_sync(data["plan_id"], kind="plans")

    _try_feishu_sync(args.id, kind="lessons")
    print_json(data)
    return 0


def cmd_save_digest(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    digest_id = args.id or generate_id("digest")
    path = DIGESTS_DIR / f"{digest_id}.md"
    existing = read_record(path) if path.exists() else {}
    content = get_content(args)
    payload = {
        "id": digest_id,
        "topic": args.topic,
        "goal": args.goal or existing.get("goal", ""),
        "source_plan": args.source_plan or existing.get("source_plan", ""),
        "status": args.status or existing.get("status", "draft"),
        "confirmed": existing.get("confirmed", []),
        "pending": existing.get("pending", []),
        "updated_at": now_iso(),
        "created_at": existing.get("created_at", now_iso()),
        "content": content if content else existing.get("content", ""),
    }
    write_record(path, payload)
    _try_feishu_sync(digest_id, kind="digests")
    print_json(payload)
    return 0


def cmd_get_digest(args: argparse.Namespace) -> int:
    path = DIGESTS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    print_json(read_record(path))
    return 0


def cmd_list_digests(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    records = []
    for path in sorted(DIGESTS_DIR.glob("*.md")):
        data = read_record(path)
        if args.status and data.get("status") != args.status:
            continue
        if args.topic and args.topic.lower() not in (data.get("topic") or "").lower():
            continue
        records.append(
            {
                "id": data.get("id"),
                "topic": data.get("topic"),
                "status": data.get("status"),
                "source_plan": data.get("source_plan"),
                "source_lesson": data.get("source_lesson"),
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
            }
        )
    records = sort_records(records, args.sort, args.desc)
    print_json(records)
    return 0


def cmd_update_digest(args: argparse.Namespace) -> int:
    path = DIGESTS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    content = get_content(args)
    if args.topic:
        data["topic"] = args.topic
    if args.goal is not None:
        data["goal"] = args.goal
    if args.status:
        data["status"] = args.status
    if args.confirmed is not None:
        data["confirmed"] = split_csv(args.confirmed)
    if args.pending is not None:
        data["pending"] = split_csv(args.pending)
    if content:
        data["content"] = content
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="digests")
    print_json(data)
    return 0


def cmd_complete_digest(args: argparse.Namespace) -> int:
    path = DIGESTS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    data["status"] = "completed"
    data["updated_at"] = now_iso()
    write_record(path, data)
    knowledge_id = generate_id("knowledge")
    content = get_content(args)
    knowledge_payload = {
        "id": knowledge_id,
        "topic": args.topic,
        "summary": args.summary or "",
        "tags": split_csv(args.tags) if args.tags is not None else [],
        "parent": args.parent or "",
        "prerequisites": split_csv(args.prerequisites)
        if args.prerequisites is not None
        else [],
        "related": split_csv(args.related) if args.related is not None else [],
        "learned_at": now_iso(),
        "review_count": 0,
        "updated_at": now_iso(),
        "created_at": now_iso(),
        "content": content if content else "",
        "source_digest": args.id,
    }
    ensure_data_dirs()
    knowledge_path = KNOWLEDGE_DIR / f"{knowledge_id}.md"
    write_record(knowledge_path, knowledge_payload)
    _try_feishu_sync(knowledge_id)

    source_plan = data.get("source_plan") or data.get("source-plan")
    if source_plan:
        plan_path = PLANS_DIR / f"{source_plan}.md"
        if plan_path.exists():
            plan_data = read_record(plan_path)
            if plan_data.get("status") != "completed":
                plan_data["status"] = "completed"
                plan_data["resume_from"] = ""
                plan_data["updated_at"] = now_iso()
                write_record(plan_path, plan_data)
                _try_feishu_sync(source_plan, kind="plans")

    _try_feishu_sync(args.id, kind="digests")
    print_json({"digest": data, "knowledge": knowledge_payload})
    return 0


def cmd_save_knowledge(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    knowledge_id = args.id or generate_id("knowledge")
    path = KNOWLEDGE_DIR / f"{knowledge_id}.md"
    existing = read_record(path) if path.exists() else {}
    content = get_content(args)
    payload = {
        "id": knowledge_id,
        "topic": args.topic,
        "summary": args.summary or existing.get("summary", ""),
        "tags": split_csv(args.tags)
        if args.tags is not None
        else existing.get("tags", []),
        "parent": args.parent or existing.get("parent", ""),
        "prerequisites": split_csv(args.prerequisites)
        if args.prerequisites is not None
        else existing.get("prerequisites", []),
        "related": split_csv(args.related)
        if args.related is not None
        else existing.get("related", []),
        "learned_at": existing.get("learned_at", now_iso()),
        "review_count": existing.get("review_count", 0),
        "updated_at": now_iso(),
        "created_at": existing.get("created_at", now_iso()),
        "content": content if content else existing.get("content", ""),
    }
    write_record(path, payload)
    _try_feishu_sync(knowledge_id)
    print_json(payload)
    return 0


def cmd_get_knowledge(args: argparse.Namespace) -> int:
    path = KNOWLEDGE_DIR / f"{args.id}.md"
    if path.exists():
        print_json(read_record(path))
        return 0

    pulled = _try_pull_from_feishu(args.id)
    if pulled:
        print_json(read_record(path))
        return 0

    print(f"NOT_FOUND\t{args.id}")
    return 1


def _try_pull_from_feishu(knowledge_id: str) -> bool:
    if not _check_feishu_sync():
        return False
    try:
        config_path = ROOT_DIR / "data" / "feishu-config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        mapping = config.get("node_mapping", {})
        for topic, info in mapping.items():
            local_id = info.get("local_id", "")
            if local_id == knowledge_id or info.get("node_token") == knowledge_id:
                node_token = info.get("node_token", "")
                if node_token:
                    subprocess.run(
                        [sys.executable, str(ROOT_DIR / "feishu.py"), "pull", "--node-token", node_token],
                        capture_output=True,
                        timeout=30,
                    )
                    return True
    except Exception:
        pass
    return False


def cmd_list_knowledge(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    records = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        data = read_record(path)
        if args.tag and args.tag not in data.get("tags", []):
            continue
        if args.topic and args.topic.lower() not in (data.get("topic") or "").lower():
            continue
        records.append(
            {
                "id": data.get("id"),
                "topic": data.get("topic"),
                "tags": data.get("tags", []),
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
            }
        )
    records = sort_records(records, args.sort, args.desc)
    print_json(records)
    return 0


def cmd_update_knowledge(args: argparse.Namespace) -> int:
    path = KNOWLEDGE_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    content = get_content(args)
    if args.topic:
        data["topic"] = args.topic
    if args.summary is not None:
        data["summary"] = args.summary
    if args.tags is not None:
        data["tags"] = split_csv(args.tags)
    if args.parent:
        data["parent"] = args.parent
    if args.prerequisites is not None:
        data["prerequisites"] = split_csv(args.prerequisites)
    if args.related is not None:
        data["related"] = split_csv(args.related)
    if content:
        data["content"] = content
    data["updated_at"] = now_iso()
    write_record(path, data)
    print_json(data)
    return 0


def cmd_add_memo(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    memo_id = args.id or generate_id("memo")
    path = MEMOS_DIR / f"{memo_id}.md"
    existing = read_record(path) if path.exists() else {}
    content = get_content(args)
    payload = {
        "id": memo_id,
        "type": args.type,
        "title": args.title,
        "status": args.status or existing.get("status", "open"),
        "priority": args.priority or existing.get("priority", "medium"),
        "deadline": args.deadline or existing.get("deadline", ""),
        "updated_at": now_iso(),
        "created_at": existing.get("created_at", now_iso()),
        "content": content if content else existing.get("content", ""),
    }
    write_record(path, payload)
    _try_feishu_sync(memo_id, kind="memos")
    print_json(payload)
    return 0


def cmd_get_memo(args: argparse.Namespace) -> int:
    path = MEMOS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    print_json(read_record(path))
    return 0


def cmd_list_memos(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    records = []
    for path in sorted(MEMOS_DIR.glob("*.md")):
        data = read_record(path)
        if args.type and data.get("type") != args.type:
            continue
        if args.status and data.get("status") != args.status:
            continue
        if args.priority and data.get("priority") != args.priority:
            continue
        records.append(
            {
                "id": data.get("id"),
                "type": data.get("type"),
                "title": data.get("title"),
                "status": data.get("status"),
                "priority": data.get("priority"),
                "deadline": data.get("deadline"),
                "updated_at": data.get("updated_at"),
                "created_at": data.get("created_at"),
            }
        )
    records = sort_records(records, args.sort, args.desc)
    print_json(records)
    return 0


def cmd_update_memo(args: argparse.Namespace) -> int:
    path = MEMOS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    content = get_content(args)
    if args.title:
        data["title"] = args.title
    if args.status:
        data["status"] = args.status
    if args.priority:
        data["priority"] = args.priority
    if args.deadline is not None:
        data["deadline"] = args.deadline
    if content:
        data["content"] = content
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="memos")
    print_json(data)
    return 0


def _extract_wiki_links(text: str) -> list[str]:
    return re.findall(r"\[\[(.+?)\]\]", text)


def cmd_backlinks(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    query = args.query.lower()
    results = []
    targets = [
        ("knowledge", KNOWLEDGE_DIR),
        ("lessons", LESSONS_DIR),
        ("plans", PLANS_DIR),
        ("digests", DIGESTS_DIR),
        ("memos", MEMOS_DIR),
    ]
    for kind, directory in targets:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            data = read_record(path)
            body = data.get("content", "")
            links = _extract_wiki_links(body)
            matching = [link for link in links if query in link.lower()]
            if matching:
                results.append(
                    {
                        "source_kind": kind,
                        "source_id": data.get("id", ""),
                        "source_topic": data.get("topic", data.get("title", "")),
                        "matched_links": matching,
                    }
                )
    print_json(results)
    return 0


def cmd_due_reviews(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    from datetime import timedelta

    now = datetime.now()
    cutoff = now + timedelta(days=args.days or 0)
    results = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        data = read_record(path)
        learned_at = data.get("learned_at") or data.get("created_at", "")
        if not learned_at:
            continue
        review_count = data.get("review_count", 0)
        if review_count >= len(REVIEW_INTERVALS):
            continue
        try:
            next_date = datetime.fromisoformat(
                next_review_date(learned_at, review_count)
            )
        except (ValueError, TypeError):
            continue
        if next_date <= cutoff:
            idx = min(review_count, len(REVIEW_INTERVALS) - 1)
            results.append(
                {
                    "id": data.get("id"),
                    "topic": data.get("topic"),
                    "summary": data.get("summary", ""),
                    "tags": data.get("tags", []),
                    "review_count": review_count,
                    "interval_days": REVIEW_INTERVALS[idx],
                    "next_review": next_date.isoformat(timespec="seconds"),
                    "overdue_days": max(0, (now - next_date).days),
                }
            )
    results.sort(key=lambda x: x["overdue_days"], reverse=True)
    print_json(results)
    return 0


def cmd_record_review(args: argparse.Namespace) -> int:
    path = KNOWLEDGE_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    if not data.get("learned_at") and data.get("created_at"):
        data["learned_at"] = data["created_at"]
    data["review_count"] = data.get("review_count", 0) + 1
    data["last_reviewed_at"] = now_iso()
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="knowledge")
    print_json(data)
    return 0


def cmd_reset_review(args: argparse.Namespace) -> int:
    path = KNOWLEDGE_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"NOT_FOUND\t{args.id}")
        return 1
    data = read_record(path)
    data["review_count"] = 0
    data["learned_at"] = now_iso()
    data["last_reviewed_at"] = ""
    data["updated_at"] = now_iso()
    write_record(path, data)
    _try_feishu_sync(args.id, kind="knowledge")
    print_json(data)
    return 0


def _load_knowledge_tree() -> dict:
    tree = {}
    if not KNOWLEDGE_DIR.exists():
        return tree
    for path in KNOWLEDGE_DIR.glob("*.md"):
        data = read_record(path)
        tree[data.get("id", "")] = {
            "id": data.get("id", ""),
            "topic": data.get("topic", ""),
            "summary": data.get("summary", ""),
            "parent": data.get("parent", ""),
            "tags": data.get("tags", []),
        }
    return tree


def cmd_tree_roots(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    results = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        data = read_record(path)
        if not data.get("parent"):
            results.append(
                {
                    "id": data.get("id"),
                    "topic": data.get("topic"),
                    "summary": data.get("summary", ""),
                    "tags": data.get("tags", []),
                    "child_count": 0,
                }
            )
    child_map = {}
    for path in KNOWLEDGE_DIR.glob("*.md"):
        data = read_record(path)
        p = data.get("parent", "")
        if p:
            child_map[p] = child_map.get(p, 0) + 1
    for root in results:
        root["child_count"] = child_map.get(root["topic"], 0)
    print_json(results)
    return 0


def cmd_tree_children(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    parent_topic = args.parent
    results = []
    child_count_map = _build_child_count_map()
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        data = read_record(path)
        if data.get("parent", "") == parent_topic:
            topic = data.get("topic", "")
            cc = child_count_map.get(topic, 0)
            entry = {
                "id": data.get("id"),
                "topic": topic,
                "summary": data.get("summary", ""),
                "tags": data.get("tags", []),
                "child_count": cc,
            }
            results.append(entry)
    warnings = []
    total = len(results)
    if total > 8:
        warnings.append(
            f"SPLIT_SUGGESTED: parent '{parent_topic}' has {total} children (>8). "
            "Consider splitting into sub-categories."
        )
    for r in results:
        if r["child_count"] > 8:
            warnings.append(
                f"SPLIT_SUGGESTED: child '{r['topic']}' has {r['child_count']} children (>8). "
                "Consider splitting into sub-categories."
            )
    output = {"children": results}
    if warnings:
        output["_warnings"] = warnings
    print_json(output)
    return 0


def _build_child_count_map() -> dict:
    counts = {}
    for path in KNOWLEDGE_DIR.glob("*.md"):
        data = read_record(path)
        p = data.get("parent", "")
        if p:
            counts[p] = counts.get(p, 0) + 1
    return counts


def cmd_tree_check(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    threshold = args.threshold or 8
    child_count_map = _build_child_count_map()
    all_topics = set()
    for path in KNOWLEDGE_DIR.glob("*.md"):
        data = read_record(path)
        all_topics.add(data.get("topic", ""))

    issues = []
    for topic, count in child_count_map.items():
        if count > threshold:
            issues.append(
                {
                    "type": "too_many_children",
                    "topic": topic,
                    "child_count": count,
                    "suggestion": f"'{topic}' has {count} children (>{threshold}). Consider splitting into sub-categories.",
                }
            )

    orphans = []
    for path in KNOWLEDGE_DIR.glob("*.md"):
        data = read_record(path)
        topic = data.get("topic", "")
        parent = data.get("parent", "")
        if not parent and child_count_map.get(topic, 0) == 0:
            content = data.get("content", "")
            if not content.strip():
                orphans.append(topic)
    if orphans:
        issues.append(
            {
                "type": "empty_roots",
                "topics": orphans,
                "suggestion": "These root nodes have no children and no content. Consider merging into an existing root or removing.",
            }
        )

    stats = {
        "total_nodes": sum(1 for _ in KNOWLEDGE_DIR.glob("*.md")),
        "root_count": sum(
            1 for _ in KNOWLEDGE_DIR.glob("*.md") if not read_record(_).get("parent")
        ),
        "max_children": max(child_count_map.values()) if child_count_map else 0,
        "threshold": threshold,
        "issue_count": len(issues),
    }
    print_json({"stats": stats, "issues": issues})
    return 0


def cmd_agenda(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    now = datetime.now()
    days_ahead = args.days
    try:
        cutoff = now + __import__("datetime").timedelta(days=days_ahead)
    except Exception:
        cutoff = now

    reviews = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        data = read_record(path)
        learned_at = data.get("learned_at", "")
        review_count = data.get("review_count", 0)
        if review_count >= len(REVIEW_INTERVALS):
            continue
        try:
            next_date = datetime.fromisoformat(next_review_date(learned_at, review_count))
        except (ValueError, TypeError):
            continue
        if next_date <= cutoff:
            reviews.append({
                "id": data.get("id"),
                "topic": data.get("topic"),
                "overdue_days": max(0, (now - next_date).days),
                "review_count": review_count,
            })
    reviews.sort(key=lambda x: x["overdue_days"], reverse=True)

    memos = []
    for path in sorted(MEMOS_DIR.glob("*.md")):
        data = read_record(path)
        if data.get("status") != "open":
            continue
        memo_info = {
            "id": data.get("id"),
            "type": data.get("type"),
            "title": data.get("title"),
            "priority": data.get("priority", "medium"),
        }
        deadline = data.get("deadline", "")
        if deadline:
            try:
                dl = datetime.fromisoformat(deadline)
                memo_info["deadline"] = deadline
                memo_info["overdue_days"] = max(0, (now.date() - dl.date()).days)
            except (ValueError, TypeError):
                pass
        memos.append(memo_info)
    memos.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "medium"), 1))

    plans = []
    for path in sorted(PLANS_DIR.glob("*.md")):
        data = read_record(path)
        if data.get("status") != "active":
            continue
        units = data.get("units", [])
        if isinstance(units, str):
            try:
                units = json.loads(units)
            except (json.JSONDecodeError, TypeError):
                units = []
        pending_units = [u for u in units if u.get("status") != "mastered"] if isinstance(units, list) else []
        plans.append({
            "id": data.get("id"),
            "topic": data.get("topic"),
            "resume_from": data.get("resume_from", ""),
            "pending_units": len(pending_units),
            "total_units": len(units) if isinstance(units, list) else 0,
        })

    agenda = {
        "date": now.isoformat(timespec="seconds"),
        "reviews_due": reviews,
        "reviews_count": len(reviews),
        "memos_open": memos,
        "memos_count": len(memos),
        "plans_active": plans,
        "plans_count": len(plans),
    }
    print_json(agenda)
    return 0


def cmd_tree_summary(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    entries = {}
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        data = read_record(path)
        topic = data.get("topic", "")
        parent = data.get("parent", "")
        entries[topic] = parent

    roots = [t for t, p in entries.items() if not p]
    tree = {}
    for root in roots:
        tree[root] = _build_subtree(root, entries)
    print_json(tree)
    return 0


def _build_subtree(parent_topic: str, entries: dict) -> list:
    children = [t for t, p in entries.items() if p == parent_topic]
    result = []
    for child in children:
        sub = _build_subtree(child, entries)
        result.append({"topic": child, "children": sub} if sub else {"topic": child})
    return result


def cmd_search(args: argparse.Namespace) -> int:
    ensure_data_dirs()
    results = []
    targets = []
    if args.kind in {"plans", "all"}:
        targets.append(
            (
                "plans",
                PLANS_DIR,
                lambda data: [
                    data.get("id", ""),
                    data.get("topic", ""),
                    data.get("goal", ""),
                    data.get("status", ""),
                    data.get("content", ""),
                ],
            )
        )
    if args.kind in {"digests", "all"}:
        targets.append(
            (
                "digests",
                DIGESTS_DIR,
                lambda data: [
                    data.get("id", ""),
                    data.get("topic", ""),
                    data.get("goal", ""),
                    data.get("status", ""),
                    data.get("content", ""),
                ],
            )
        )
    if args.kind in {"lessons", "all"}:
        targets.append(
            (
                "lessons",
                LESSONS_DIR,
                lambda data: [
                    data.get("id", ""),
                    data.get("topic", ""),
                    data.get("goal", ""),
                    data.get("status", ""),
                    data.get("content", ""),
                ],
            )
        )
    if args.kind in {"knowledge", "all"}:
        targets.append(
            (
                "knowledge",
                KNOWLEDGE_DIR,
                lambda data: [
                    data.get("id", ""),
                    data.get("topic", ""),
                    data.get("summary", ""),
                    " ".join(data.get("tags", [])),
                    data.get("parent", ""),
                    " ".join(data.get("related", [])),
                    data.get("content", ""),
                ],
            )
        )
    if args.kind in {"memos", "all"}:
        targets.append(
            (
                "memos",
                MEMOS_DIR,
                lambda data: [
                    data.get("id", ""),
                    data.get("title", ""),
                    data.get("type", ""),
                    data.get("status", ""),
                    data.get("content", ""),
                ],
            )
        )

    for kind, directory, extractor in targets:
        for path in sorted(directory.glob("*.md")):
            data = read_record(path)
            if text_matches(extractor(data), args.query):
                results.append(summarize_record(kind, data))

    print_json(results)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="knowledge-system skill-local IO tool")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init")
    init_parser.set_defaults(func=cmd_init)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--path", required=True)
    list_parser.set_defaults(func=cmd_list)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--path", required=True)
    read_parser.set_defaults(func=cmd_read)

    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--path", required=True)
    write_parser.add_argument("--content")
    write_parser.add_argument("--stdin", action="store_true")
    write_parser.set_defaults(func=cmd_write)

    append_parser = subparsers.add_parser("append")
    append_parser.add_argument("--path", required=True)
    append_parser.add_argument("--content")
    append_parser.add_argument("--stdin", action="store_true")
    append_parser.set_defaults(func=cmd_append)

    read_json_parser = subparsers.add_parser("read-json")
    read_json_parser.add_argument("--path", required=True)
    read_json_parser.set_defaults(func=cmd_read_json)

    write_json_parser = subparsers.add_parser("write-json")
    write_json_parser.add_argument("--path", required=True)
    write_json_parser.add_argument("--content")
    write_json_parser.add_argument("--stdin", action="store_true")
    write_json_parser.set_defaults(func=cmd_write_json)

    mkdir_parser = subparsers.add_parser("mkdir")
    mkdir_parser.add_argument("--path", required=True)
    mkdir_parser.set_defaults(func=cmd_mkdir)

    exists_parser = subparsers.add_parser("exists")
    exists_parser.add_argument("--path", required=True)
    exists_parser.set_defaults(func=cmd_exists)

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("--path", required=True)
    delete_parser.set_defaults(func=cmd_delete)

    save_plan_parser = subparsers.add_parser("save-plan")
    save_plan_parser.add_argument("--id")
    save_plan_parser.add_argument("--topic", required=True)
    save_plan_parser.add_argument("--goal")
    save_plan_parser.add_argument("--status")
    save_plan_parser.add_argument("--basis")
    save_plan_parser.add_argument("--baseline")
    save_plan_parser.add_argument("--resume-from")
    save_plan_parser.add_argument("--content")
    save_plan_parser.add_argument("--stdin", action="store_true")
    save_plan_parser.set_defaults(func=cmd_save_plan)

    get_plan_parser = subparsers.add_parser("get-plan")
    get_plan_parser.add_argument("--id", required=True)
    get_plan_parser.set_defaults(func=cmd_get_plan)

    list_plans_parser = subparsers.add_parser("list-plans")
    list_plans_parser.add_argument("--status")
    list_plans_parser.add_argument("--topic")
    list_plans_parser.add_argument(
        "--sort", default="updated_at", choices=["updated_at", "created_at", "topic"]
    )
    list_plans_parser.add_argument("--desc", action="store_true")
    list_plans_parser.set_defaults(func=cmd_list_plans)

    update_plan_status_parser = subparsers.add_parser("update-plan-status")
    update_plan_status_parser.add_argument("--id", required=True)
    update_plan_status_parser.add_argument("--status", required=True)
    update_plan_status_parser.set_defaults(func=cmd_update_plan_status)

    update_units_parser = subparsers.add_parser("update-units")
    update_units_parser.add_argument("--id", required=True)
    update_units_parser.add_argument("--content")
    update_units_parser.add_argument("--stdin", action="store_true")
    update_units_parser.set_defaults(func=cmd_update_units)

    set_resume_parser = subparsers.add_parser("set-resume")
    set_resume_parser.add_argument("--id", required=True)
    set_resume_parser.add_argument("--resume-from", required=True)
    set_resume_parser.set_defaults(func=cmd_set_resume)

    record_progress_parser = subparsers.add_parser("record-progress")
    record_progress_parser.add_argument("--plan-id", required=True)
    record_progress_parser.add_argument("--unit", required=True)
    record_progress_parser.add_argument("--status", required=True)
    record_progress_parser.add_argument("--summary")
    record_progress_parser.add_argument("--next")
    record_progress_parser.add_argument("--mastered")
    record_progress_parser.add_argument("--weak")
    record_progress_parser.set_defaults(func=cmd_record_progress)

    upsert_progress_parser = subparsers.add_parser("upsert-progress")
    upsert_progress_parser.add_argument("--plan-id", required=True)
    upsert_progress_parser.add_argument("--unit", required=True)
    upsert_progress_parser.add_argument("--status", required=True)
    upsert_progress_parser.add_argument("--summary")
    upsert_progress_parser.add_argument("--next")
    upsert_progress_parser.add_argument("--mastered")
    upsert_progress_parser.add_argument("--weak")
    upsert_progress_parser.set_defaults(func=cmd_upsert_progress)

    save_lesson_parser = subparsers.add_parser("save-lesson")
    save_lesson_parser.add_argument("--id")
    save_lesson_parser.add_argument("--topic", required=True)
    save_lesson_parser.add_argument("--plan-id")
    save_lesson_parser.add_argument("--unit")
    save_lesson_parser.add_argument("--goal")
    save_lesson_parser.add_argument("--content")
    save_lesson_parser.add_argument("--stdin", action="store_true")
    save_lesson_parser.set_defaults(func=cmd_save_lesson)

    get_lesson_parser = subparsers.add_parser("get-lesson")
    get_lesson_parser.add_argument("--id", required=True)
    get_lesson_parser.set_defaults(func=cmd_get_lesson)

    list_lessons_parser = subparsers.add_parser("list-lessons")
    list_lessons_parser.add_argument("--plan-id")
    list_lessons_parser.add_argument("--status")
    list_lessons_parser.add_argument("--topic")
    list_lessons_parser.add_argument(
        "--sort", default="updated_at", choices=["updated_at", "created_at", "topic"]
    )
    list_lessons_parser.add_argument("--desc", action="store_true")
    list_lessons_parser.set_defaults(func=cmd_list_lessons)

    update_lesson_parser = subparsers.add_parser("update-lesson")
    update_lesson_parser.add_argument("--id", required=True)
    update_lesson_parser.add_argument("--topic")
    update_lesson_parser.add_argument("--goal")
    update_lesson_parser.add_argument("--status")
    update_lesson_parser.add_argument("--mastered")
    update_lesson_parser.add_argument("--weak")
    update_lesson_parser.add_argument("--next")
    update_lesson_parser.add_argument("--content")
    update_lesson_parser.add_argument("--stdin", action="store_true")
    update_lesson_parser.set_defaults(func=cmd_update_lesson)

    complete_lesson_parser = subparsers.add_parser("complete-lesson")
    complete_lesson_parser.add_argument("--id", required=True)
    complete_lesson_parser.add_argument("--status")
    complete_lesson_parser.set_defaults(func=cmd_complete_lesson)

    save_digest_parser = subparsers.add_parser("save-digest")
    save_digest_parser.add_argument("--id")
    save_digest_parser.add_argument("--topic", required=True)
    save_digest_parser.add_argument("--goal")
    save_digest_parser.add_argument("--source-plan")
    save_digest_parser.add_argument("--status")
    save_digest_parser.add_argument("--content")
    save_digest_parser.add_argument("--stdin", action="store_true")
    save_digest_parser.set_defaults(func=cmd_save_digest)

    get_digest_parser = subparsers.add_parser("get-digest")
    get_digest_parser.add_argument("--id", required=True)
    get_digest_parser.set_defaults(func=cmd_get_digest)

    list_digests_parser = subparsers.add_parser("list-digests")
    list_digests_parser.add_argument("--status")
    list_digests_parser.add_argument("--topic")
    list_digests_parser.add_argument(
        "--sort", default="updated_at", choices=["updated_at", "created_at", "topic"]
    )
    list_digests_parser.add_argument("--desc", action="store_true")
    list_digests_parser.set_defaults(func=cmd_list_digests)

    update_digest_parser = subparsers.add_parser("update-digest")
    update_digest_parser.add_argument("--id", required=True)
    update_digest_parser.add_argument("--topic")
    update_digest_parser.add_argument("--goal")
    update_digest_parser.add_argument("--status")
    update_digest_parser.add_argument("--confirmed")
    update_digest_parser.add_argument("--pending")
    update_digest_parser.add_argument("--content")
    update_digest_parser.add_argument("--stdin", action="store_true")
    update_digest_parser.set_defaults(func=cmd_update_digest)

    complete_digest_parser = subparsers.add_parser("complete-digest")
    complete_digest_parser.add_argument("--id", required=True)
    complete_digest_parser.add_argument("--topic", required=True)
    complete_digest_parser.add_argument("--summary")
    complete_digest_parser.add_argument("--tags")
    complete_digest_parser.add_argument("--parent")
    complete_digest_parser.add_argument("--prerequisites")
    complete_digest_parser.add_argument("--related")
    complete_digest_parser.add_argument("--content")
    complete_digest_parser.add_argument("--stdin", action="store_true")
    complete_digest_parser.set_defaults(func=cmd_complete_digest)

    save_knowledge_parser = subparsers.add_parser("save-knowledge")
    save_knowledge_parser.add_argument("--id")
    save_knowledge_parser.add_argument("--topic", required=True)
    save_knowledge_parser.add_argument("--summary")
    save_knowledge_parser.add_argument("--tags")
    save_knowledge_parser.add_argument("--parent")
    save_knowledge_parser.add_argument("--prerequisites")
    save_knowledge_parser.add_argument("--related")
    save_knowledge_parser.add_argument("--content")
    save_knowledge_parser.add_argument("--stdin", action="store_true")
    save_knowledge_parser.set_defaults(func=cmd_save_knowledge)

    get_knowledge_parser = subparsers.add_parser("get-knowledge")
    get_knowledge_parser.add_argument("--id", required=True)
    get_knowledge_parser.set_defaults(func=cmd_get_knowledge)

    list_knowledge_parser = subparsers.add_parser("list-knowledge")
    list_knowledge_parser.add_argument("--tag")
    list_knowledge_parser.add_argument("--topic")
    list_knowledge_parser.add_argument(
        "--sort", default="updated_at", choices=["updated_at", "created_at", "topic"]
    )
    list_knowledge_parser.add_argument("--desc", action="store_true")
    list_knowledge_parser.set_defaults(func=cmd_list_knowledge)

    update_knowledge_parser = subparsers.add_parser("update-knowledge")
    update_knowledge_parser.add_argument("--id", required=True)
    update_knowledge_parser.add_argument("--topic")
    update_knowledge_parser.add_argument("--summary")
    update_knowledge_parser.add_argument("--tags")
    update_knowledge_parser.add_argument("--parent")
    update_knowledge_parser.add_argument("--prerequisites")
    update_knowledge_parser.add_argument("--related")
    update_knowledge_parser.add_argument("--content")
    update_knowledge_parser.add_argument("--stdin", action="store_true")
    update_knowledge_parser.set_defaults(func=cmd_update_knowledge)

    add_memo_parser = subparsers.add_parser("add-memo")
    add_memo_parser.add_argument("--id")
    add_memo_parser.add_argument("--type", required=True)
    add_memo_parser.add_argument("--title", required=True)
    add_memo_parser.add_argument("--status")
    add_memo_parser.add_argument("--priority")
    add_memo_parser.add_argument("--deadline")
    add_memo_parser.add_argument("--content")
    add_memo_parser.add_argument("--stdin", action="store_true")
    add_memo_parser.set_defaults(func=cmd_add_memo)

    get_memo_parser = subparsers.add_parser("get-memo")
    get_memo_parser.add_argument("--id", required=True)
    get_memo_parser.set_defaults(func=cmd_get_memo)

    list_memos_parser = subparsers.add_parser("list-memos")
    list_memos_parser.add_argument("--type")
    list_memos_parser.add_argument("--status")
    list_memos_parser.add_argument("--priority")
    list_memos_parser.add_argument(
        "--sort",
        default="updated_at",
        choices=["updated_at", "created_at", "title", "deadline"],
    )
    list_memos_parser.add_argument("--desc", action="store_true")
    list_memos_parser.set_defaults(func=cmd_list_memos)

    update_memo_parser = subparsers.add_parser("update-memo")
    update_memo_parser.add_argument("--id", required=True)
    update_memo_parser.add_argument("--title")
    update_memo_parser.add_argument("--status")
    update_memo_parser.add_argument("--priority")
    update_memo_parser.add_argument("--deadline")
    update_memo_parser.add_argument("--content")
    update_memo_parser.add_argument("--stdin", action="store_true")
    update_memo_parser.set_defaults(func=cmd_update_memo)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument(
        "--kind",
        required=True,
        choices=["plans", "lessons", "digests", "knowledge", "memos", "all"],
    )
    search_parser.add_argument("--query", required=True)
    search_parser.set_defaults(func=cmd_search)

    backlinks_parser = subparsers.add_parser("backlinks")
    backlinks_parser.add_argument("--query", required=True)
    backlinks_parser.set_defaults(func=cmd_backlinks)

    due_reviews_parser = subparsers.add_parser("due-reviews")
    due_reviews_parser.add_argument("--days", type=int, default=0)
    due_reviews_parser.set_defaults(func=cmd_due_reviews)

    record_review_parser = subparsers.add_parser("record-review")
    record_review_parser.add_argument("--id", required=True)
    record_review_parser.set_defaults(func=cmd_record_review)

    reset_review_parser = subparsers.add_parser("reset-review")
    reset_review_parser.add_argument("--id", required=True)
    reset_review_parser.set_defaults(func=cmd_reset_review)

    tree_roots_parser = subparsers.add_parser("tree-roots")
    tree_roots_parser.set_defaults(func=cmd_tree_roots)

    tree_children_parser = subparsers.add_parser("tree-children")
    tree_children_parser.add_argument("--parent", required=True)
    tree_children_parser.set_defaults(func=cmd_tree_children)

    tree_summary_parser = subparsers.add_parser("tree-summary")
    tree_summary_parser.set_defaults(func=cmd_tree_summary)

    tree_check_parser = subparsers.add_parser("tree-check")
    tree_check_parser.add_argument("--threshold", type=int, default=8)
    tree_check_parser.set_defaults(func=cmd_tree_check)

    agenda_parser = subparsers.add_parser("agenda")
    agenda_parser.add_argument("--days", type=int, default=3)
    agenda_parser.set_defaults(func=cmd_agenda)

    return parser


def main() -> int:
    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help", "help"}:
        print(HELP_TEXT)
        return 0

    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        print(HELP_TEXT)
        return 1

    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR\t{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
