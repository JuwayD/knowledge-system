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
PLANS_DIR = DATA_DIR / "plans"
LESSONS_DIR = DATA_DIR / "lessons"
DIGESTS_DIR = DATA_DIR / "digests"
MEMOS_DIR = DATA_DIR / "memos"
CONFIG_PATH = DATA_DIR / "feishu-config.json"

CATEGORY_DEFS = {
    "knowledge": {"label": "知识库", "dir": KNOWLEDGE_DIR},
    "plans": {"label": "学习计划", "dir": PLANS_DIR},
    "lessons": {"label": "课堂记录", "dir": LESSONS_DIR},
    "digests": {"label": "消化记录", "dir": DIGESTS_DIR},
    "memos": {"label": "备忘录", "dir": MEMOS_DIR},
}

LARK_CLI = os.environ.get(
    "LARK_CLI_PATH",
    str(Path(os.environ.get("APPDATA", "")) / "npm/node_modules/@larksuite/cli/bin/lark-cli.exe"),
)

HELP_TEXT = """feishu.py — Feishu Wiki sync tool (via lark-cli)

Uses lark-cli (https://github.com/larksuite/cli) to sync knowledge entries to Feishu Wiki.

Prerequisites:
  1. lark-cli installed:   npm install -g @larksuite/cli
  2. App configured:       lark-cli config init --app-id <id> --app-secret-stdin --brand feishu
  3. User authorized:      lark-cli auth login --recommend

Commands:
  setup
    First-time setup: choose or create a wiki space for knowledge-system.

  status
    Show current config and lark-cli auth status.

  spaces
    List available wiki spaces.

  pull [--all] [--node-token <token>]
    Pull nodes FROM Feishu to local cache.
    --all: pull all nodes in the space
    --node-token: pull a specific node

  sync [--id <knowledge_id>] [--all] [--parent <topic>] [--dry-run]
    Push local knowledge to Feishu (create or update).

  sync-tree [--dry-run]
    Push entire knowledge tree.
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


def cmd_setup(args):
    config = load_config()
    if config.get("space_id"):
        print(f"Already configured: space_id={config['space_id']}")
        print("Run 'feishu.py config --space-id <new_id>' to change.")
        return 0

    print("=== knowledge-system 飞书首次配置 ===\n")
    result = run_lark("wiki", "spaces", "list")
    spaces = []
    if "data" in result and "items" in result["data"]:
        spaces = result["data"]["items"]

    if spaces:
        print("已有知识库：")
        for i, space in enumerate(spaces, 1):
            print(f"  {i}. {space['name']} ({space['space_id']})")
        print(f"  {len(spaces) + 1}. [新建] 创建专用知识库")

        try:
            choice = int(input("\n请选择 (输入编号): ").strip())
        except (ValueError, EOFError):
            choice = len(spaces) + 1

        if 1 <= choice <= len(spaces):
            selected = spaces[choice - 1]
            config["space_id"] = selected["space_id"]
            print(f"\n已选择: {selected['name']}")
        else:
            create_result = run_lark(
                "api", "POST", "/open-apis/wiki/v2/spaces",
                "--data", json.dumps({"name": "知识系统", "description": "knowledge-system 自动同步的知识库"}),
            )
            if create_result.get("ok") or create_result.get("code") == 0:
                new_space = create_result.get("data", {}).get("space", {})
                config["space_id"] = new_space.get("space_id", "")
                print(f"\n已创建新知识库: 知识系统 ({config['space_id']})")
            else:
                print(f"\n创建失败: {json.dumps(create_result, ensure_ascii=False)}")
                print("请手动指定: feishu.py config --space-id <id>")
                return 1
    else:
        print("未找到已有知识库，将自动创建...")
        create_result = run_lark(
            "api", "POST", "/open-apis/wiki/v2/spaces",
            "--data", json.dumps({"name": "知识系统", "description": "knowledge-system 自动同步的知识库"}),
        )
        if create_result.get("ok") or create_result.get("code") == 0:
            new_space = create_result.get("data", {}).get("space", {})
            config["space_id"] = new_space.get("space_id", "")
            print(f"已创建: 知识系统 ({config['space_id']})")
        else:
            print(f"创建失败: {json.dumps(create_result, ensure_ascii=False)}")
            return 1

    config.setdefault("node_mapping", {})
    save_config(config)
    print(f"\n配置已保存。后续所有知识将同步到此知识库。")
    return 0


def cmd_pull(args):
    config = load_config()
    space_id = config.get("space_id")
    if not space_id:
        print("ERROR\tNo space_id. Run: feishu.py setup")
        return 1

    if args.node_token:
        _pull_single(config, args.node_token)
    elif args.all:
        _pull_all(config, space_id)
    else:
        print("ERROR\tSpecify --all or --node-token <token>")
        return 1
    return 0


def _pull_all(config: dict, space_id: str):
    result = run_lark(
        "wiki", "nodes", "list",
        "--params", json.dumps({"space_id": space_id}),
        "--page-all",
    )
    nodes = []
    if "data" in result and "items" in result["data"]:
        nodes = result["data"]["items"]

    if not nodes:
        print("NO_NODES\tWiki space is empty.")
        return

    mapping = config.get("node_mapping", {})
    print(f"Found {len(nodes)} nodes. Pulling...")

    node_token_to_topic = {}
    for node in nodes:
        node_token = node.get("node_token", "")
        obj_token = node.get("obj_token", "")
        title = node.get("title", "")
        parent_token = node.get("parent_node_token", "")
        node_token_to_topic[node_token] = title

        content = ""
        if obj_token:
            fetch_result = run_lark("docs", "+fetch", "--doc", obj_token)
            content = _extract_markdown(fetch_result)

        local_id = f"knowledge-feishu-{node_token}"
        payload = {
            "id": local_id,
            "topic": title,
            "summary": "",
            "tags": [],
            "parent": "",
            "prerequisites": [],
            "related": [],
            "learned_at": "",
            "review_count": 0,
            "updated_at": _now_iso(),
            "created_at": "",
            "content": content,
            "feishu_node_token": node_token,
            "feishu_obj_token": obj_token,
        }

        path = KNOWLEDGE_DIR / f"{local_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_knowledge_file(path, payload)
        mapping[title] = {
            "node_token": node_token,
            "doc_id": obj_token,
            "local_id": local_id,
            "synced_at": _now_iso(),
        }
        print(f"  PULLED\t{title} -> {local_id}")

    for node in nodes:
        parent_token = node.get("parent_node_token", "")
        if parent_token and parent_token in node_token_to_topic:
            title = node.get("title", "")
            parent_topic = node_token_to_topic[parent_token]
            local_id = f"knowledge-feishu-{node['node_token']}"
            path = KNOWLEDGE_DIR / f"{local_id}.md"
            if path.exists():
                data = read_knowledge_file(path)
                data["parent"] = parent_topic
                write_knowledge_file(path, data)

    config["node_mapping"] = mapping
    save_config(config)
    print(f"Done. {len(nodes)} nodes pulled.")


def _pull_single(config: dict, node_token: str):
    result = run_lark(
        "wiki", "nodes", "list",
        "--params", json.dumps({"space_id": config["space_id"], "node_token": node_token}),
    )
    nodes = result.get("data", {}).get("items", [])
    if not nodes:
        print(f"NOT_FOUND\tNode {node_token}")
        return

    node = nodes[0]
    obj_token = node.get("obj_token", "")
    title = node.get("title", "")

    content = ""
    if obj_token:
        fetch_result = run_lark("docs", "+fetch", "--doc", obj_token)
        content = _extract_markdown(fetch_result)

    local_id = f"knowledge-feishu-{node_token}"
    payload = {
        "id": local_id,
        "topic": title,
        "summary": "",
        "tags": [],
        "parent": "",
        "prerequisites": [],
        "related": [],
        "learned_at": "",
        "review_count": 0,
        "updated_at": _now_iso(),
        "created_at": "",
        "content": content,
        "feishu_node_token": node_token,
        "feishu_obj_token": obj_token,
    }

    path = KNOWLEDGE_DIR / f"{local_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_knowledge_file(path, payload)

    mapping = config.get("node_mapping", {})
    mapping[title] = {
        "node_token": node_token,
        "doc_id": obj_token,
        "local_id": local_id,
        "synced_at": _now_iso(),
    }
    config["node_mapping"] = mapping
    save_config(config)
    print(f"PULLED\t{title} -> {local_id}")


def _extract_markdown(fetch_result: dict) -> str:
    content = fetch_result.get("data", {}).get("content", "")
    if isinstance(content, str) and content:
        return content
    body = fetch_result.get("data", {}).get("body", {})
    if isinstance(body, dict):
        blocks = body.get("blocks", [])
        lines = []
        for block in blocks:
            text = _extract_block_text(block)
            if text:
                lines.append(text)
        return "\n".join(lines)
    return ""


def _extract_block_text(block: dict) -> str:
    btype = block.get("block_type", "")
    data = block.get(btype, block)
    elements = data.get("elements", []) if isinstance(data, dict) else []
    texts = []
    for el in elements:
        if isinstance(el, dict):
            tr = el.get("text_run", {})
            if isinstance(tr, dict):
                texts.append(tr.get("content", ""))
    text = "".join(texts)
    prefix = {"heading1": "# ", "heading2": "## ", "heading3": "### "}.get(btype, "")
    return f"{prefix}{text}" if text else ""


def write_knowledge_file(path: Path, data: dict):
    import yaml as yaml_lib
    meta = {k: v for k, v in data.items() if k != "content"}
    content = data.get("content", "")
    text = "---\n" + yaml_lib.dump(meta, allow_unicode=True, default_flow_style=False) + "---\n\n" + content + "\n"
    path.write_text(text, encoding="utf-8")


def read_knowledge_file(path: Path) -> dict:
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


def _ensure_category_root(config: dict, kind: str) -> str:
    category_roots = config.setdefault("category_roots", {})
    if category_roots.get(kind):
        return category_roots[kind]
    label = CATEGORY_DEFS.get(kind, {}).get("label", kind)
    result = _create_doc(label, f"# {label}\n\n", config["space_id"])
    if result.get("ok"):
        node_token = result.get("data", {}).get("doc_url", "").split("/")[-1]
        doc_id = result.get("data", {}).get("doc_id", "")
        category_roots[kind] = node_token
        config["category_roots"] = category_roots
        mapping = config.get("node_mapping", {})
        mapping[f"__category__{kind}"] = {"node_token": node_token, "doc_id": doc_id}
        config["node_mapping"] = mapping
        save_config(config)
        return node_token
    return ""


def _sync_entry(entry: dict, config: dict, kind: str = "knowledge") -> str:
    topic = entry.get("topic", entry.get("title", entry.get("id", "")))
    parent = entry.get("parent", "") if kind == "knowledge" else ""
    content = entry.get("content", "")
    updated_at = entry.get("updated_at", "")
    entry_id = entry.get("id", "")
    mapping = config.get("node_mapping", {})
    space_id = config.get("space_id", "")

    map_key = f"{kind}:{entry_id}" if kind != "knowledge" else topic

    existing = mapping.get(map_key)
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
    if kind == "knowledge" and parent and parent in mapping:
        parent_node_token = mapping[parent].get("node_token", "")
    elif kind != "knowledge":
        parent_node_token = _ensure_category_root(config, kind)

    if parent_node_token:
        result = _create_child_node(topic, content, space_id, parent_node_token)
    else:
        result = _create_doc(topic, content, space_id)

    if result.get("ok"):
        node_token = result.get("data", {}).get("doc_url", "").split("/")[-1]
        doc_id = result.get("data", {}).get("doc_id", "")
        mapping[map_key] = {
            "node_token": node_token,
            "doc_id": doc_id,
            "kind": kind,
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
    kind = getattr(args, "kind", "knowledge")
    kind_dir = CATEGORY_DEFS.get(kind, {}).get("dir", KNOWLEDGE_DIR)
    entries = []
    if hasattr(args, "id") and args.id:
        path = kind_dir / f"{args.id}.md"
        if path.exists():
            entries.append(read_knowledge_entry(path))
    elif hasattr(args, "all") and args.all:
        for path in sorted(kind_dir.glob("*.md")):
            entries.append(read_knowledge_entry(path))
    elif hasattr(args, "parent") and args.parent:
        for path in sorted(kind_dir.glob("*.md")):
            entry = read_knowledge_entry(path)
            if entry.get("parent") == args.parent:
                entries.append(entry)
    return entries


def cmd_sync(args):
    config = load_config()
    if not config.get("space_id"):
        print("ERROR\tNo space_id configured. Run: feishu.py config --space-id <id>")
        return 1

    kind = getattr(args, "kind", "knowledge")
    entries = _collect_entries(args)
    if not entries:
        print("NO_ENTRIES\tNo matching entries found.")
        return 0

    print(f"Syncing {len(entries)} {kind} entries...")
    for entry in entries:
        topic = entry.get("topic", entry.get("title", entry.get("id", "")))
        if args.dry_run:
            existing = config.get("node_mapping", {}).get(topic if kind == "knowledge" else f"{kind}:{entry.get('id','')}", {})
            status = "UPDATE" if existing.get("node_token") else "CREATE"
            parent_info = f" (parent: {entry.get('parent')})" if entry.get("parent") else ""
            print(f"  [{status}] {topic}{parent_info}")
            continue

        result = _sync_entry(entry, config, kind=kind)
        print(f"  {result}\t{topic}")

    print(f"Done. {len(entries)} entries processed.")
    return 0


def cmd_sync_tree(args):
    config = load_config()
    space_id = args.space_id or config.get("space_id")
    if not space_id:
        print("ERROR\tNo space_id. Run: feishu.py setup")
        return 1

    if args.dry_run:
        print(f"Dry-run: would sync all data to space {space_id}")
        for kind, defn in CATEGORY_DEFS.items():
            kind_dir = defn["dir"]
            if not kind_dir.exists():
                continue
            entries = [read_knowledge_entry(p) for p in sorted(kind_dir.glob("*.md"))]
            print(f"\n  [{defn['label']}] {len(entries)} entries")
            for e in entries:
                print(f"    - {e.get('topic', e.get('title', e.get('id', '')))}")
        return 0

    total = 0

    for kind, defn in CATEGORY_DEFS.items():
        kind_dir = defn["dir"]
        if not kind_dir.exists():
            continue
        entries = [read_knowledge_entry(p) for p in sorted(kind_dir.glob("*.md"))]
        if not entries:
            continue

        print(f"\n[{defn['label']}] {len(entries)} entries...")

        if kind == "knowledge":
            roots = [e for e in entries if not e.get("parent")]
            children = [e for e in entries if e.get("parent")]
            for entry in roots:
                result = _sync_entry(entry, config, kind="knowledge")
                print(f"  {result}\t{entry.get('topic')}")
            for entry in children:
                parent_topic = entry.get("parent", "")
                map_key = parent_topic
                if map_key not in config.get("node_mapping", {}):
                    print(f"  SKIP\t{entry.get('topic')} (parent '{parent_topic}' not synced)")
                    continue
                result = _sync_entry(entry, config, kind="knowledge")
                print(f"  {result}\t{entry.get('topic')}")
        else:
            for entry in entries:
                result = _sync_entry(entry, config, kind=kind)
                title = entry.get("topic", entry.get("title", entry.get("id", "")))
                print(f"  {result}\t{title}")

        total += len(entries)

    print(f"\nDone. {total} total entries processed.")
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

    setup_parser = subparsers.add_parser("setup")
    setup_parser.set_defaults(func=cmd_setup)

    status_parser = subparsers.add_parser("status")
    status_parser.set_defaults(func=cmd_status)

    spaces_parser = subparsers.add_parser("spaces")
    spaces_parser.set_defaults(func=cmd_spaces)

    pull_parser = subparsers.add_parser("pull")
    pull_parser.add_argument("--all", action="store_true")
    pull_parser.add_argument("--node-token")
    pull_parser.set_defaults(func=cmd_pull)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--id")
    sync_parser.add_argument("--all", action="store_true")
    sync_parser.add_argument("--parent")
    sync_parser.add_argument("--kind", default="knowledge", choices=list(CATEGORY_DEFS.keys()))
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
