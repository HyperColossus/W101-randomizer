"""Command-line entry point for importing a local, pinned SpiralDB checkout."""
import argparse
import json
from pathlib import Path

from .core import RandomizerError
from .spiraldb import import_spiraldb


def main(argv=None):
    parser = argparse.ArgumentParser(description='Import source references from SpiralDB')
    parser.add_argument('--spiraldb', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--spell-overlay')
    parser.add_argument('--curation', help='optional manually verified overlay pinned to SpiralDB checksum')
    parser.add_argument('--settings', help='seed/mode configuration, requires --manifest')
    parser.add_argument('--manifest', help='also build a deterministic gameplay manifest')
    parser.add_argument('--quest-prefix', default='WC-')
    parser.add_argument('--start-zone', default='WizardCity/WC_Hub')
    args = parser.parse_args(argv)
    try:
        if Path(args.out).resolve() == Path(args.report).resolve():
            raise RandomizerError('catalog and report output paths must differ')
        overlay = None
        if args.spell_overlay:
            overlay = json.loads(Path(args.spell_overlay).read_text(encoding='utf-8'))
            if not isinstance(overlay, list):
                raise RandomizerError('spell overlay must be a JSON array')
        catalog, report = import_spiraldb(args.spiraldb, quest_prefix=args.quest_prefix,
                                          start_zone=args.start_zone, spell_overlay=overlay)
        if args.curation:
            from .curation import curate_spiraldb
            approvals = json.loads(Path(args.curation).read_text(encoding='utf-8'))
            catalog, report['curation'] = curate_spiraldb(catalog, approvals)
            report['safe_to_generate_manifest'] = any(
                'attack' in s.get('tags', []) and s['pips'] <= 2 and s['min_level'] <= 1
                for s in catalog['spells'])
            report['import_counts']['curated_spells'] = len(catalog['spells'])
        if bool(args.settings) != bool(args.manifest):
            raise RandomizerError('--settings and --manifest are required together')
        outputs = [(args.out, catalog), (args.report, report)]
        if args.manifest:
            from .core import generate_manifest
            settings = json.loads(Path(args.settings).read_text(encoding='utf-8'))
            outputs.append((args.manifest, generate_manifest(catalog, settings)))
        if len({str(Path(path).resolve()) for path, _ in outputs}) != len(outputs):
            raise RandomizerError('outputs must use different paths')
        for output, data in outputs:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic output: write complete file then replace.
            partial = path.with_suffix(path.suffix + '.tmp')
            partial.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            partial.replace(path)
        print('SpiralDB catalog:', args.out)
        print('Source audit report:', args.report)
        if args.manifest:
            print('Game adapter manifest:', args.manifest)
        print(json.dumps(report['import_counts'], indent=2, sort_keys=True))
        if not report['safe_to_generate_manifest']:
            print('Unverified starter spells: no gameplay manifest is ready yet.')
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f'error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
