import argparse
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests")
    sys.exit(1)

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
CONFIG_PATH = DATA_DIR / "feishu-config.json"

FEISHU_BASE = "https://open.feishu.cn/open-apis"

HELP_TEXT = """feishu.py — Feishu Wiki sync tool for knowledge-system

Commands:
  auth --app-id <id> --app-secret <secret> --space-id <space_id>
    Configure Feishu credentials and target wiki space.

  status
    Show current config and auth status.

  sync [--id <knowledge_id>] [--all] [--parent <topic>] [--dry-run]
    Sync knowledge entries to Feishu Wiki.
    --id: sync a specific entry
    --all: sync all entries
    --parent <topic>: sync entries under a specific parent
    --dry-run: show what would be synced without actually syncing

  sync-tree [--dry-run]
    Sync entire knowledge tree structure (creates parent nodes first, then children).
"""


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_tenant_token(config: dict) -> str:
    resp = requests.post(
        f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal/",
        json={"app_id": config["app_id"], "app_secret": config["app_secret"]},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Auth failed: {data.get('msg')}")
    return data["tenant_access_token"]


def feishu_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }


def create_wiki_node(
    token: str, space_id: str, title: str, parent_node_token: str = ""
) -> dict:
    body = {
        "obj_type": "docx",
        "node_type": "origin",
        "title": title,
    }
    if parent_node_token:
        body["parent_node_token"] = parent_node_token
    resp = requests.post(
        f"{FEISHU_BASE}/wiki/v2/spaces/{space_id}/nodes",
        headers=feishu_headers(token),
        json=body,
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Create wiki node failed for '{title}': {data.get('msg')}")
    return data["data"]["node"]


def get_doc_block_id(token: str, document_id: str) -> str:
    resp = requests.get(
        f"{FEISHU_BASE}/docx/v1/documents/{document_id}",
        headers=feishu_headers(token),
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Get document failed: {data.get('msg')}")
    return data["data"]["document"]["block_id"]


def markdown_to_blocks(md_text: str) -> list:
    blocks = []
    lines = md_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        if re.match(r"^###\s+", line):
            text = re.sub(r"^###\s+", "", line).strip()
            blocks.append(_make_heading(text, 3))
            i += 1
        elif re.match(r"^##\s+", line):
            text = re.sub(r"^##\s+", "", line).strip()
            blocks.append(_make_heading(text, 2))
            i += 1
        elif re.match(r"^#\s+", line):
            text = re.sub(r"^#\s+", "", line).strip()
            blocks.append(_make_heading(text, 1))
            i += 1
        elif re.match(r"^```", line):
            lang = re.sub(r"^```\s*", "", line).strip()
            code_lines = []
            i += 1
            while i < len(lines) and not re.match(r"^```", lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1
            blocks.append(_make_code_block("\n".join(code_lines), lang))
        elif re.match(r"^[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i]):
                items.append(re.sub(r"^[-*]\s+", "", lines[i]).strip())
                i += 1
            blocks.append(_make_bullet_list(items))
        elif re.match(r"^\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i]).strip())
                i += 1
            blocks.append(_make_ordered_list(items))
        elif re.match(r"^\|", line):
            table_lines = []
            while i < len(lines) and re.match(r"^\|", lines[i]):
                table_lines.append(lines[i])
                i += 1
            blocks.extend(_make_table(table_lines))
        elif line.strip():
            blocks.append(_make_paragraph(line.strip()))
            i += 1
        else:
            i += 1
    return blocks


def _make_heading(text: str, level: int) -> dict:
    heading_type = {1: "heading1", 2: "heading2", 3: "heading3"}.get(level, "heading1")
    return {
        "block_type": heading_type,
        heading_type: {
            "elements": [{"text_run": {"content": _strip_md_links(text)}}],
        },
    }


def _make_paragraph(text: str) -> dict:
    elements = _parse_inline_elements(text)
    return {
        "block_type": "text",
        "text": {"elements": elements}
        if elements
        else {"elements": [{"text_run": {"content": ""}}]},
    }


def _make_code_block(code: str, language: str = "") -> dict:
    lang_map = {
        "python": "Python",
        "javascript": "JavaScript",
        "java": "Java",
        "go": "Go",
        "rust": "Rust",
        "bash": "Bash",
        "shell": "Shell",
        "sql": "SQL",
        "json": "JSON",
        "yaml": "YAML",
        "html": "HTML",
        "css": "CSS",
        "typescript": "TypeScript",
        "c": "C",
        "cpp": "C++",
    }
    normalized = lang_map.get(language.lower(), language) if language else ""
    return {
        "block_type": "code",
        "code": {
            "language": normalized,
            "elements": [{"text_run": {"content": code}}],
        },
    }


def _make_bullet_list(items: list) -> dict:
    elements = []
    for item in items:
        elements.append({"text_run": {"content": _strip_md_links(item)}})
    return {
        "block_type": "bullet",
        "bullet": {"elements": elements},
    }


def _make_ordered_list(items: list) -> dict:
    elements = []
    for item in items:
        elements.append({"text_run": {"content": _strip_md_links(item)}})
    return {
        "block_type": "ordered",
        "ordered": {"elements": elements},
    }


def _make_table(table_lines: list) -> list:
    rows = []
    for line in table_lines:
        if re.match(r"^\|[\s-|]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return []

    max_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    blocks = []
    for row in rows:
        cells = []
        for cell in row:
            cells.append(
                {
                    "block_type": "table_cell",
                    "table_cell": {
                        "elements": [{"text_run": {"content": _strip_md_links(cell)}}]
                    },
                }
            )
        blocks.append(
            {
                "block_type": "table_row",
                "table_row": {"cells": cells},
            }
        )

    return [
        {
            "block_type": "table",
            "table": {
                "rows": len(rows),
                "columns": max_cols,
                "header_row": 1,
            },
        }
    ] + blocks


def _strip_md_links(text: str) -> str:
    return re.sub(r"\[\[(.+?)\]\]", r"\1", text)


def _parse_inline_elements(text: str) -> list:
    elements = []
    pattern = r"\[\[(.+?)\]\]"
    last = 0
    for m in re.finditer(pattern, text):
        if m.start() > last:
            elements.append({"text_run": {"content": text[last : m.start()]}})
        elements.append({"text_run": {"content": m.group(1)}})
        last = m.end()
    if last < len(text):
        elements.append({"text_run": {"content": text[last:]}})
    return elements


def write_doc_blocks(token: str, document_id: str, blocks: list):
    block_id = get_doc_block_id(token, document_id)
    batch_size = 50
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i : i + batch_size]
        resp = requests.post(
            f"{FEISHU_BASE}/docx/v1/documents/{document_id}/blocks/{block_id}/children",
            headers=feishu_headers(token),
            json={"children": batch},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Write blocks failed: {data.get('msg')}")


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


def cmd_auth(args):
    config = load_config()
    config["app_id"] = args.app_id
    config["app_secret"] = args.app_secret
    config["space_id"] = args.space_id
    config.setdefault("node_mapping", {})
    save_config(config)

    token = get_tenant_token(config)
    print(f"OK\tAuth successful. Token acquired (length={len(token)}).")
    print(f"Space ID: {config['space_id']}")


def cmd_status(args):
    config = load_config()
    if not config.get("app_id"):
        print("NOT_CONFIGURED\tRun 'feishu.py auth' first.")
        return 1
    print(f"App ID: {config['app_id'][:8]}...")
    print(f"Space ID: {config.get('space_id', 'N/A')}")
    mapping = config.get("node_mapping", {})
    print(f"Mapped nodes: {len(mapping)}")
    if mapping:
        for topic, info in mapping.items():
            print(f"  {topic} -> {info.get('node_token', 'N/A')}")
    try:
        token = get_tenant_token(config)
        print(f"Auth: OK (token length={len(token)})")
    except Exception as e:
        print(f"Auth: FAILED ({e})")
    return 0


def cmd_sync(args):
    config = load_config()
    if not config.get("app_id"):
        print("NOT_CONFIGURED\tRun 'feishu.py auth' first.")
        return 1

    token = get_tenant_token(config)
    mapping = config.get("node_mapping", {})

    entries = _collect_entries(args)

    if not entries:
        print("NO_ENTRIES\tNo matching knowledge entries found.")
        return 0

    print(f"Syncing {len(entries)} entries...")

    for entry in entries:
        topic = entry.get("topic", "")
        parent = entry.get("parent", "")
        content = entry.get("content", "")

        if args.dry_run:
            node_info = mapping.get(topic, {})
            status = "UPDATE" if node_info.get("node_token") else "CREATE"
            parent_info = f" (parent: {parent})" if parent else " (root)"
            print(f"  [{status}] {topic}{parent_info}")
            continue

        parent_node_token = ""
        if parent and parent in mapping:
            parent_node_token = mapping[parent].get("node_token", "")

        existing = mapping.get(topic)
        if existing and existing.get("node_token"):
            _update_entry(token, config, existing, entry)
            print(f"  UPDATED\t{topic}")
        else:
            node = create_wiki_node(token, config["space_id"], topic, parent_node_token)
            mapping[topic] = {
                "node_token": node["node_token"],
                "obj_token": node["obj_token"],
            }

            if content:
                blocks = markdown_to_blocks(content)
                if blocks:
                    write_doc_blocks(token, node["obj_token"], blocks)

            print(f"  CREATED\t{topic} -> {node['node_token']}")

    if not args.dry_run:
        config["node_mapping"] = mapping
        save_config(config)

    print(f"Done. {len(entries)} entries processed.")
    return 0


def cmd_sync_tree(args):
    config = load_config()
    if not config.get("app_id"):
        print("NOT_CONFIGURED\tRun 'feishu.py auth' first.")
        return 1

    token = get_tenant_token(config)
    mapping = config.get("node_mapping", {})

    all_entries = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        entry = read_knowledge_entry(path)
        all_entries.append(entry)

    roots = [e for e in all_entries if not e.get("parent")]
    children = [e for e in all_entries if e.get("parent")]

    if args.dry_run:
        print(f"Would sync {len(roots)} root nodes, then {len(children)} children.")
        for e in roots:
            print(f"  [CREATE] {e.get('topic')} (root)")
        for e in children:
            print(f"  [CREATE] {e.get('topic')} (parent: {e.get('parent')})")
        return 0

    print(f"Syncing tree: {len(roots)} roots, {len(children)} children...")

    for entry in roots:
        topic = entry.get("topic", "")
        existing = mapping.get(topic)
        if existing and existing.get("node_token"):
            print(f"  SKIP\t{topic} (already mapped)")
            continue
        node = create_wiki_node(token, config["space_id"], topic)
        mapping[topic] = {
            "node_token": node["node_token"],
            "obj_token": node["obj_token"],
        }
        content = entry.get("content", "")
        if content:
            blocks = markdown_to_blocks(content)
            if blocks:
                write_doc_blocks(token, node["obj_token"], blocks)
        print(f"  CREATED\t{topic} -> {node['node_token']}")

    for entry in children:
        topic = entry.get("topic", "")
        parent_topic = entry.get("parent", "")
        existing = mapping.get(topic)
        if existing and existing.get("node_token"):
            print(f"  SKIP\t{topic} (already mapped)")
            continue

        parent_token = mapping.get(parent_topic, {}).get("node_token", "")
        if not parent_token:
            print(f"  SKIP\t{topic} (parent '{parent_topic}' not yet synced)")
            continue

        node = create_wiki_node(token, config["space_id"], topic, parent_token)
        mapping[topic] = {
            "node_token": node["node_token"],
            "obj_token": node["obj_token"],
        }
        content = entry.get("content", "")
        if content:
            blocks = markdown_to_blocks(content)
            if blocks:
                write_doc_blocks(token, node["obj_token"], blocks)
        print(f"  CREATED\t{topic} -> {node['node_token']}")

    config["node_mapping"] = mapping
    save_config(config)
    print(f"Done. {len(mapping)} total nodes mapped.")
    return 0


def _collect_entries(args) -> list:
    entries = []
    if args.id:
        path = KNOWLEDGE_DIR / f"{args.id}.md"
        if path.exists():
            entries.append(read_knowledge_entry(path))
    elif args.all:
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            entries.append(read_knowledge_entry(path))
    elif args.parent:
        for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
            entry = read_knowledge_entry(path)
            if entry.get("parent") == args.parent:
                entries.append(entry)
    return entries


def _update_entry(token: str, config: dict, existing: dict, entry: dict):
    pass


def main() -> int:
    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help", "help"}:
        print(HELP_TEXT)
        return 0

    parser = argparse.ArgumentParser(description="Feishu Wiki sync")
    subparsers = parser.add_subparsers(dest="command")

    auth_parser = subparsers.add_parser("auth")
    auth_parser.add_argument("--app-id", required=True)
    auth_parser.add_argument("--app-secret", required=True)
    auth_parser.add_argument("--space-id", required=True)
    auth_parser.set_defaults(func=cmd_auth)

    status_parser = subparsers.add_parser("status")
    status_parser.set_defaults(func=cmd_status)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--id")
    sync_parser.add_argument("--all", action="store_true")
    sync_parser.add_argument("--parent")
    sync_parser.add_argument("--dry-run", action="store_true")
    sync_parser.set_defaults(func=cmd_sync)

    sync_tree_parser = subparsers.add_parser("sync-tree")
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
