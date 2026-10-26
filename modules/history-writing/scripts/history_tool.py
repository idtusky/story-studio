"""Portable corpus search, text checks, and read-only update discovery."""
import argparse
import hashlib
import json
import math
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERA_ALIASES = {
    '宋代': {'宋', '北宋', '南宋'}, '宋朝': {'宋', '北宋', '南宋'},
    '汉代': {'西汉', '东汉', '东汉末'}, '汉朝': {'西汉', '东汉', '东汉末'},
    '唐代': {'唐', '武周'}, '明代': {'明', '明初', '明末'},
    '清代': {'清', '晚清'}, '三国': {'三国', '曹魏', '蜀汉', '孙吴'},
}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def records():
    return json.loads((ROOT / 'corpus/catalog.json').read_text(encoding='utf-8'))


def corpus_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Corpus path escapes skill directory')
    return path


def normalize(text):
    return ''.join(c.casefold() for c in text if unicodedata.category(c)[0] in 'LN')


def grams(text):
    value = normalize(text)
    return {value[i:i+5] for i in range(max(0, len(value)-4))}


def era_match(record, requested):
    values = {record['era'], *record['era_tags']}
    return bool(values & ERA_ALIASES.get(requested, {requested}))


def search(args):
    candidates = []
    for record in records():
        if args.era and not era_match(record, args.era):
            continue
        if args.person and args.person not in record['people']:
            continue
        if args.template and record['template'] != args.template:
            continue
        if args.account and record['account'] != args.account:
            continue
        if args.conflict and args.conflict not in record['conflict']:
            continue
        if args.cluster and args.cluster != record['cluster']:
            continue
        if record['cluster'] in args.exclude_cluster:
            continue
        haystack = ' '.join(str(record.get(k, '')) for k in
                            ['title', 'people', 'era_tags', 'conflict', 'cluster', 'next_angle'])
        terms = args.query.split()
        if terms and not all(term.casefold() in haystack.casefold() for term in terms):
            continue
        score = sum(3 if term in record['title'] else 1 for term in terms)
        candidates.append((score, record))
    available = len(candidates)
    chosen, seen_accounts, seen_clusters = [], set(), set()
    while candidates and len(chosen) < args.limit:
        candidates.sort(key=lambda pair: (
            -(pair[0] + (2 if pair[1]['cluster'] not in seen_clusters else 0)
              + (1 if pair[1]['account'] not in seen_accounts else 0)), pair[1]['id']))
        _, record = candidates.pop(0)
        chosen.append({k: record[k] for k in ['id', 'title', 'account', 'era', 'era_tags',
                      'people', 'conflict', 'template', 'cluster', 'metrics', 'risk',
                      'next_angle', 'raw_path', 'clean_path']})
        seen_accounts.add(record['account'])
        seen_clusters.add(record['cluster'])
    emit({'matched': available, 'returned': len(chosen), 'records': chosen,
          'note': 'No automatic filter relaxation. Rank is relevance and diversity, not predicted performance.'})
    return 0


def read(args):
    catalog = {r['id']: r for r in records()}
    missing = [key for key in args.ids if key not in catalog]
    if missing:
        raise ValueError('Unknown IDs: ' + ', '.join(missing))
    for key in args.ids:
        r = catalog[key]
        print(f"\n# {key} {r['title']}\n")
        emit({k: r[k] for k in ['account', 'template', 'cluster', 'risk', 'fact_status']})
        print(corpus_path(r['clean_path'] if args.clean else r['raw_path']).read_text(encoding='utf-8-sig'))
    return 0


def hooks(args):
    data = json.loads((ROOT / 'corpus/hook_analysis.json').read_text(encoding='utf-8'))
    candidates = []
    for record in data['records']:
        kinds = {record['primary']}
        if args.include_secondary:
            kinds.update(record['secondary'])
        if args.type and args.type not in kinds:
            continue
        if args.id and record['id'] != args.id:
            continue
        if args.era and not era_match(record, args.era):
            continue
        if args.person and args.person not in record['people']:
            continue
        candidates.append(record)
    available = len(candidates)
    chosen, accounts, clusters = [], set(), set()
    while candidates and len(chosen) < args.limit:
        candidates.sort(key=lambda r: (
            -(2 * (r['cluster'] not in clusters) + (r['account'] not in accounts)), r['id']))
        record = candidates.pop(0)
        chosen.append(record)
        accounts.add(record['account'])
        clusters.add(record['cluster'])
    emit({'matched': available, 'returned': len(chosen), 'records': chosen,
          'method': data['method'],
          'note': 'Writing examples only; inspect issue and original text. No performance ranking or fact certification.'})
    return 0


def count(args):
    text = Path(args.file).read_text(encoding='utf-8-sig')
    value = sum(unicodedata.category(c)[0] in 'LN' for c in text)
    with_punctuation = sum(not c.isspace() for c in text)
    selected = with_punctuation if args.include_punctuation else value
    result = {'file': str(Path(args.file).resolve()), 'letters_and_numbers': value,
              'non_whitespace_characters': with_punctuation, 'count': selected,
              'scope': 'Entire file is body; no automatic title or Markdown stripping.'}
    if args.target is not None:
        lower = math.ceil(args.target * (1 - args.tolerance))
        upper = math.floor(args.target * (1 + args.tolerance))
        result.update(target=args.target, allowed=[lower, upper], passed=lower <= selected <= upper)
    emit(result)
    return 0 if result.get('passed', True) else 1


def audit(args):
    query = grams(Path(args.file).read_text(encoding='utf-8-sig'))
    matches = []
    for r in records():
        other = grams(corpus_path(r['clean_path']).read_text(encoding='utf-8-sig'))
        common = query & other
        union = query | other
        matches.append({'id': r['id'], 'title': r['title'], 'cluster': r['cluster'],
                        'jaccard': round(len(common)/len(union), 4) if union else 0,
                        'draft_gram_coverage': round(len(common)/len(query), 4) if query else 0,
                        'shared_grams': sorted(common)[:30]})
    matches.sort(key=lambda r: (-r['jaccard'], r['id']))
    emit({'usable_grams': len(query), 'matches': matches[:args.limit],
          'note': 'Character-overlap candidates only; inspect quotations and semantic repetition manually.'})
    return 0


def scan(args):
    source = Path(args.source).resolve()
    if not source.is_dir():
        raise ValueError('Source must be an existing directory')
    catalog = records()
    hashes = {r['original_sha256']: r['id'] for r in catalog}
    known_names = {Path(r['original_path']).name: r['id'] for r in catalog}
    seen, changes = set(), []
    for path in sorted(source.rglob('*.md')):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            key = hashes[digest]
            seen.add(key)
            state = 'unchanged_content'
        else:
            key = known_names.get(path.name)
            state = 'changed_candidate' if key else 'new_candidate'
            if key:
                seen.add(key)
        changes.append({'path': str(path), 'status': state, 'matched_id': key, 'sha256': digest})
    emit({'source': str(source), 'files': changes,
          'not_found_in_scan': [r['id'] for r in catalog if r['id'] not in seen],
          'note': 'Read-only. Missing originals are not deleted. Renamed changes need video-ID review.'})
    return 0


def validate(args):
    errors, ids, videos = [], set(), set()
    catalog = records()
    required = {'id', 'video_id', 'account', 'title', 'era', 'era_tags', 'people',
                'conflict', 'template', 'cluster', 'risk', 'structure', 'source_class',
                'raw_path', 'clean_path', 'original_sha256', 'fact_status'}
    for r in catalog:
        key = r.get('id', '<missing>')
        if required - r.keys():
            errors.append(f'{key}: missing fields {sorted(required-r.keys())}')
            continue
        if key in ids or r['video_id'] in videos:
            errors.append(f'{key}: duplicate ID')
        ids.add(key)
        videos.add(r['video_id'])
        for field in ['era_tags', 'people']:
            if not isinstance(r[field], list):
                errors.append(f'{key}: {field} must be a list')
        for field in ['raw_path', 'clean_path']:
            if not corpus_path(r[field]).is_file():
                errors.append(f'{key}: missing {field}')
        raw = corpus_path(r['raw_path'])
        if raw.is_file() and hashlib.sha256(raw.read_bytes()).hexdigest() != r['original_sha256']:
            errors.append(f'{key}: raw hash mismatch')
        meta = corpus_path(f'corpus/meta/{key}.json')
        if not meta.is_file() or json.loads(meta.read_text(encoding='utf-8')) != r:
            errors.append(f'{key}: meta and catalog mismatch')
    hook_data = json.loads((ROOT / 'corpus/hook_analysis.json').read_text(encoding='utf-8'))
    hook_rows = hook_data['records']
    if len(hook_rows) != len(catalog) or {r['id'] for r in hook_rows} != ids:
        errors.append('Hook analysis must cover every catalog ID exactly once')
    indexed = {r['id']: r for r in catalog}
    for r in hook_rows:
        original = indexed.get(r['id'])
        if original is None:
            continue
        if r['raw_sha256'] != original['original_sha256'] or r['raw_path'] != original['raw_path']:
            errors.append(f"{r['id']}: hook source mismatch")
        if any(r[k] != original[k] for k in ['era', 'era_tags', 'people', 'account', 'cluster']):
            errors.append(f"{r['id']}: stale hook metadata")
        if r['primary'] not in hook_data['types'] or any(k not in hook_data['types'] for k in r['secondary']):
            errors.append(f"{r['id']}: unknown hook type")
        raw_path = corpus_path(original['raw_path'])
        if raw_path.is_file():
            raw = raw_path.read_text(encoding='utf-8-sig')
            body = raw.split('## 口播逐字稿', 1)[-1].strip()
            body = body.removeprefix('来源：视频音轨转写').strip()
            if not r['hook_unit'] or not body.startswith(r['hook_unit']):
                errors.append(f"{r['id']}: hook is not a verbatim body opening")
        if r['hook_unit_units'] != sum(unicodedata.category(c)[0] in 'LN' for c in r['hook_unit']):
            errors.append(f"{r['id']}: hook count mismatch")
    emit({'records': len(catalog), 'passed': not errors, 'errors': errors})
    return 0 if not errors else 1


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('Must be positive')
    return number


def fraction(value):
    number = float(value)
    if not 0 <= number < 1:
        raise argparse.ArgumentTypeError('Must be between 0 (inclusive) and 1 (exclusive)')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('search')
    p.add_argument('--query', default='')
    for option in ['era', 'person', 'template', 'account', 'conflict', 'cluster']:
        p.add_argument('--' + option)
    p.add_argument('--exclude-cluster', action='append', default=[])
    p.add_argument('--limit', type=positive, default=5)
    p.set_defaults(run=search)
    p = sub.add_parser('read')
    p.add_argument('ids', nargs='+')
    p.add_argument('--clean', action='store_true')
    p.set_defaults(run=read)
    p = sub.add_parser('hooks')
    for option in ['type', 'id', 'era', 'person']:
        p.add_argument('--' + option)
    p.add_argument('--include-secondary', action='store_true')
    p.add_argument('--limit', type=positive, default=5)
    p.set_defaults(run=hooks)
    p = sub.add_parser('count')
    p.add_argument('file')
    p.add_argument('--target', type=positive)
    p.add_argument('--tolerance', type=fraction, default=0)
    p.add_argument('--include-punctuation', action='store_true')
    p.set_defaults(run=count)
    p = sub.add_parser('audit')
    p.add_argument('file')
    p.add_argument('--limit', type=positive, default=5)
    p.set_defaults(run=audit)
    p = sub.add_parser('scan')
    p.add_argument('source')
    p.set_defaults(run=scan)
    p = sub.add_parser('validate')
    p.set_defaults(run=validate)
    args = parser.parse_args()
    try:
        return args.run(args)
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
