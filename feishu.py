import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
CONFIG_PATH = DATA_DIR / "feishu-config.json"

LARK_CLI = os.environ.get(
    "LARK_CLI_PATH",
    str(Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@larksuite/cli/bin/lark-cli.exe"),
)

HELP_TEXT = """feishu.py — Feishu Wiki sync tool (via lark-cli)

Uses lark-cli (https://github.com/larksuite/cli) to sync knowledge entries to Feishu Wiki.

Prerequisites:
  1. lark-cli installed:   npm install -g @larksuite/cli
  2. App configured:       lark-cli config init --new
  3. User authorized:      lark-cli auth login --recommend

Commands:
  config --space-id <space_id>
    Set target wiki space ID.

  status
    Show current config and lark-cli auth status.

  spaces
    List available wiki spaces.

  sync [--id <knowledge_id>] [--all] [--parent <topic>] [--dry-run]
    Sync knowledge entries to Feishu Wiki.

  sync-tree [--space-id <id>] [--dry-run]
    Sync entire knowledge tree (roots first, then children).
"""


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def run_lark(*args) -> dict:
    cmd = [LARK_CLI] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR\tlark-cli not found at: {LARK_CLI}")
        print("Install with: npm install -g @larksuite/cli")
        sys.exit(1)

    output = result.stdout.strip()
    if output:
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw": output}
    if result.returncode != 0:
        err = result.stderr.strip()
        return {"error": err, "returncode": result.returncode}
    return {}


def read_knowledge_entry(path: Path) -> dict:
    import yaml as yaml_lib

    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) >= 3:
        meta = yaml_lib.safe_load(parts[1]) or {}
        content = parts[2].strip()
    else:
        meta = {}
        content = text.strip()
    meta["content"] = content
    return meta


def cmd_config(args):
    config = load_config()
    if args.space_id:
        config["space_id"] = args.space_id
    if not config.get("space_id"):
        print("ERROR\t--space-id is required on first config.")
        return 1
    config.setdefault("node_mapping", {})
    save_config(config)
    print(f"OK\tSpace ID: {config['space_id']}")
    return 0


def cmd_status(args):
    config = load_config()
    space_id = config.get("space_id", "")
    mapping = config.get("node_mapping", {})

    print(f"Space ID:  {space_id or '(not set)'}")
    print(f"Mapped:    {len(mapping)} nodes")
    if mapping:
        for topic, info in list(mapping.items())[:10]:
            print(f"  {topic} -> {info.get('node_token', 'N/A')}")
        if len(mapping) > 10:
            print(f"  ... and {len(mapping) - 10} more")

    print("\n--- lark-cli auth status ---")
    result = run_lark("auth", "status")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_spaces(args):
    result = run_lark("wiki", "spaces", "list")
    if "data" in result and "items" in result["data"]:
        for space in result["data"]["items"]:
            marker = " <-- current" if space.get("space_id") == load_config().get("space_id") else ""
            print(f"  {space['space_id']}  {space['name']}{marker}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _create_doc(title: str, markdown: str, wiki_space: str) -> dict:
    result = run_lark("docs", "+create", "--title", title, "--markdown", markdown, "--wiki-space", wiki_space)
    return result


def _create_child_node(title: str, markdown: str, space_id: str, parent_node_token: str) -> dict:
    node_result = run_lark(
        "wiki", "+node-create",
        "--title", title,
        "--space-id", space_id,
        "--parent-node-token", parent_node_token,
    )
    if not node_result.get("ok"):
        return node_result
    data = node_result.get("data", {})
    node_token = data.get("node_token", "")
    obj_token = data.get("obj_token", "")
    if markdown and obj_token:
        run_lark(
            "docs", "+update",
            "--doc", obj_token,
            "--markdown", markdown,
            "--mode", "overwrite",
        )
    return {"ok": True, "data": {"node_token": node_token, "doc_id": obj_token, "doc_url": f"https://www.feishu.cn/wiki/{node_token}"}}


def _update_doc(doc_id: str, markdown: str, title: str = "") -> dict:
    cmd_args = [
        "docs", "+update",
        "--doc", doc_id,
        "--markdown", markdown,
        "--mode", "overwrite",
    ]
    if title:
        cmd_args += ["--new-title", title]
    return run_lark(*cmd_args)


def _sync_entry(entry: dict, config: dict) -> str:
    topic = entry.get("topic", "")
    parent = entry.get("parent", "")
    content = entry.get("content", "")
    updated_at = entry.get("updated_at", "")
    mapping = config.get("node_mapping", {})
    space_id = config.get("space_id", "")

    existing = mapping.get(topic)
    if existing and existing.get("node_token"):
        synced_at = existing.get("synced_at", "")
        if synced_at and updated_at and updated_at <= synced_at:
            return "SKIP"

        doc_id = existing.get("doc_id", "")
        if doc_id and content:
            result = _update_doc(doc_id, content, topic)
            if result.get("ok") is False:
                return f"FAILED: {json.dumps(result, ensure_ascii=False)}"
        existing["synced_at"] = updated_at or _now_iso()
        config["node_mapping"] = mapping
        save_config(config)
        return "UPDATED"

    parent_node_token = ""
    if parent and parent in mapping:
        parent_node_token = mapping[parent].get("node_token", "")

    if parent_node_token:
        result = _create_child_node(topic, content, space_id, parent_node_token)
    else:
        result = _create_doc(topic, content, space_id)

    if result.get("ok"):
        node_token = result.get("data", {}).get("doc_url", "").split("/")[-1]
        doc_id = result.get("data", {}).get("doc_id", "")
        mapping[topic] = {
            "node_token": node_token,
            "doc_id": doc_id,
            "synced_at": updated_at or _now_iso(),
        }
        config["node_mapping"] = mapping
        save_config(config)
        return f"CREATED -> {node_token}"
    else:
        return f"FAILED: {json.dumps(result, ensure_ascii=False)}"


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _collect_entries(args) -> list:
    entries = []
    if hasattr(args, "id") and args.id:
        path = KNOWLEDGE_DIR / f"{args.id}.md"
        if path.exists():
            entries.append(read_knowledge_entry(path))
    elif hasattr(args, "all") and args.all:
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            entries.append(read_knowledge_entry(path))
    elif hasattr(args, "parent") and args.parent:
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            entry = read_knowledge_entry(path)
            if entry.get("parent") == args.parent:
                entries.append(entry)
    return entries


def cmd_sync(args):
    config = load_config()
    if not config.get("space_id"):
        print("ERROR\tNo space_id configured. Run: feishu.py config --space-id <id>")
        return 1

    entries = _collect_entries(args)
    if not entries:
        print("NO_ENTRIES\tNo matching knowledge entries found.")
        return 0

    print(f"Syncing {len(entries)} entries...")
    for entry in entries:
        topic = entry.get("topic", "")
        if args.dry_run:
            existing = config.get("node_mapping", {}).get(topic, {})
            status = "UPDATE" if existing.get("node_token") else "CREATE"
            parent_info = f" (parent: {entry.get('parent')})" if entry.get("parent") else " (root)"
            print(f"  [{status}] {topic}{parent_info}")
            continue

        result = _sync_entry(entry, config)
        print(f"  {result}\t{topic}")

    print(f"Done. {len(entries)} entries processed.")
    return 0


def cmd_sync_tree(args):
    config = load_config()
    space_id = args.space_id or config.get("space_id")
    if not space_id:
        print("ERROR\tNo space_id. Run: feishu.py config --space-id <id>")
        return 1

    mapping = config.get("node_mapping", {})

    all_entries = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        all_entries.append(read_knowledge_entry(path))

    roots = [e for e in all_entries if not e.get("parent")]
    children = [e for e in all_entries if e.get("parent")]

    if args.dry_run:
        print(f"Would sync {len(roots)} roots + {len(children)} children to space {space_id}")
        for e in roots:
            existing = config.get("node_mapping", {}).get(e.get("topic", ""), {})
            status = "UPDATE" if existing.get("node_token") else "CREATE"
            print(f"  [{status}] {e.get('topic')} (root)")
        for e in children:
            existing = config.get("node_mapping", {}).get(e.get("topic", ""), {})
            status = "UPDATE" if existing.get("node_token") else "CREATE"
            print(f"  [{status}] {e.get('topic')} (parent: {e.get('parent')})")
        return 0

    print(f"Syncing tree: {len(roots)} roots + {len(children)} children...")

    for entry in roots:
        result = _sync_entry(entry, config)
        print(f"  {result}\t{entry.get('topic')}")

    for entry in children:
        parent_topic = entry.get("parent", "")
        if parent_topic not in config.get("node_mapping", {}):
            print(f"  SKIP\t{entry.get('topic')} (parent '{parent_topic}' not yet synced)")
            continue
        result = _sync_entry(entry, config)
        print(f"  {result}\t{entry.get('topic')}")

    total = len(config.get("node_mapping", {}))
    print(f"Done. {total} total nodes mapped.")
    return 0


def main() -> int:
    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help", "help"}:
        print(HELP_TEXT)
        return 0

    parser = argparse.ArgumentParser(description="Feishu Wiki sync via lark-cli")
    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser("config")
    config_parser.add_argument("--space-id", required=True)
    config_parser.set_defaults(func=cmd_config)

    status_parser = subparsers.add_parser("status")
    status_parser.set_defaults(func=cmd_status)

    spaces_parser = subparsers.add_parser("spaces")
    spaces_parser.set_defaults(func=cmd_spaces)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--id")
    sync_parser.add_argument("--all", action="store_true")
    sync_parser.add_argument("--parent")
    sync_parser.add_argument("--dry-run", action="store_true")
    sync_parser.set_defaults(func=cmd_sync)

    sync_tree_parser = subparsers.add_parser("sync-tree")
    sync_tree_parser.add_argument("--space-id")
    sync_tree_parser.add_argument("--dry-run", action="store_true")
    sync_tree_parser.set_defaults(func=cmd_sync_tree)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        print(HELP_TEXT)
        return 1

    try:
        return args.func(args) or 0
    except Exception as exc:
        print(f"ERROR\t{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
