"""stdlib-only command-line tool for offline manifests and simulated character rolls."""
import argparse
import json
import os
from pathlib import Path
from .core import RandomizerError, generate_manifest, validate_catalog
from .progression import SpellProgression
from .runtime import RunStore
from .api import make_server


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as fp:
        json.dump(value, fp, indent=2, sort_keys=True)
        fp.write("\n")
        fp.flush()
        os.fsync(fp.fileno())
    temp.replace(target)


def main(argv=None):
    parser = argparse.ArgumentParser(description="W101 offline seed/character planner (NOT a running private server)")
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="create a seeded world manifest")
    g.add_argument("--catalog", required=True)
    g.add_argument("--settings", required=True)
    g.add_argument("--out", required=True)
    p = sub.add_parser("progress", help="simulate per-character progression")
    p.add_argument("--catalog", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--character", required=True)
    p.add_argument("--level", type=int, required=True)
    p = sub.add_parser("draft", help="choose one spell from an already-generated draft")
    p.add_argument("--catalog", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--character", required=True)
    p.add_argument("--level", type=int, required=True)
    p.add_argument("--spell", required=True)
    api = sub.add_parser('serve', help='run trusted loopback-only HTTP bridge (NO game server)')
    api.add_argument('--catalog', required=True)
    api.add_argument('--manifest', required=True)
    api.add_argument('--db', required=True)
    api.add_argument('--host', default='127.0.0.1')
    api.add_argument('--port', default=18951, type=int)
    api.add_argument('--allow-demo', action='store_true', help='allow fake demo IDs for local tests ONLY')
    stat = sub.add_parser('status', help='inspect bridge database state')
    stat.add_argument('--catalog', required=True)
    stat.add_argument('--manifest', required=True)
    stat.add_argument('--db', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            catalog, settings = load(args.catalog), load(args.settings)
            manifest = generate_manifest(catalog, settings)
            save(args.out, manifest)
            print(f"Saved {args.out} ({manifest['manifest_sha256'][:12]})")
            return 0
        catalog, manifest = load(args.catalog), load(args.manifest)
        validate_catalog(catalog)
        from .core import fingerprint
        if fingerprint(catalog) != manifest["catalog_sha256"]:
            raise RandomizerError("catalog no longer matches manifest")
        if args.command in ('serve', 'status'):
            if args.command == 'serve':
                token = os.environ.get('W101_API_TOKEN', '')
                if not args.allow_demo and any(str(x.get('id', '')).startswith('demo-') for x in catalog.get('spells', [])):
                    raise RandomizerError('sample demo IDs are not allowed for live bridge; supply a verified catalog')
            store = RunStore(args.db, catalog, manifest)
            if args.command == 'status':
                print(json.dumps(store.status(), indent=2, sort_keys=True))
                return 0
            server = make_server(store, token, host=args.host, port=args.port)
            print(f'Loopback bridge listening at http://{args.host}:{server.server_port} (no game integration)', flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        state = load(args.state) if Path(args.state).exists() else None
        engine = SpellProgression(catalog, manifest, state)
        if args.command == "progress":
            result = engine.level_to(args.character, args.level)
        else:
            result = engine.choose_draft(args.character, args.level, args.spell)
        save(args.state, engine.state)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
