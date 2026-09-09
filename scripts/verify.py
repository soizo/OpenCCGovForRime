"""Deploy public upstreams and check real candidate behavior in a fresh Rime home."""
import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

TEST_REPOS = ('rime-prelude', 'rime-essay', 'rime-stroke', 'rime-pinyin-simp',
              'rime-ice', 'rime-luna-pinyin', 'rime-cangjie', 'rime-wubi')


def check_candidates(baseline: list, simplified: list, traditional: list, expected: str) -> None:
    if not baseline or simplified != baseline:
        raise ValueError('Simplified candidates differ from upstream or are empty')
    if expected not in traditional:
        raise ValueError(f'Missing government-standard candidate: {expected}; got {traditional}')
    if len(traditional) != len(set(traditional)):
        raise ValueError('Duplicate converted candidates')


def query(probe: Path, shared: Path, user: Path, sid: str, keys: str, options: list) -> tuple:
    result = subprocess.run([str(probe), str(shared), str(user), 'query', sid, keys, *options],
                            text=True, capture_output=True, timeout=60, check=False)
    if result.returncode or 'opencc config not found' in result.stderr:
        raise ValueError(f'Rime query failed: {sid}/{keys}\n{result.stderr[-4000:]}')
    candidates, defaults = [], {}
    for line in result.stdout.splitlines():
        parts = line.split('\t')
        if parts[0] == 'candidate':
            candidates.append(parts[1])
        elif parts[0] == 'default':
            if len(parts) != 3 or parts[2] not in ('0', '1'):
                raise ValueError('Invalid probe option output')
            defaults[parts[1]] = 1 if parts[2] == '1' else 0
    return candidates, defaults


def prepare_native(source: Path, target: Path) -> None:
    """Compile OpenCC 1.1.9 baseline data used by classic Rime clients."""
    target.mkdir(exist_ok=True)
    compiled = set()

    def visit(node):
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            if 'file' in node:
                name = node['file']
                if node.get('type') != 'ocd2' or not re.fullmatch(r'[A-Za-z0-9_]+\.ocd2', name):
                    raise ValueError('Unsafe native dictionary reference')
                if name not in compiled:
                    dictionary = source / 'dictionary' / (Path(name).stem + '.txt')
                    subprocess.run(['opencc_dict', '-i', str(dictionary), '-o', str(target / name),
                                    '-f', 'text', '-t', 'ocd2'], check=True)
                    compiled.add(name)
            for child in node.values():
                visit(child)

    for name in ('s2t', 't2s', 't2hk', 't2tw'):
        path = source / 'config' / (name + '.json')
        try:
            config = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f'Invalid baseline config: {path}') from error
        visit(config)
        shutil.copyfile(path, target / path.name)


def prepare(upstreams: Path, package: Path, shared: Path, user: Path, entries: list) -> None:
    shared.mkdir()
    user.mkdir()
    for repo in TEST_REPOS:
        source = upstreams / repo
        if not source.is_dir():
            raise ValueError(f'Test upstream missing: {repo}')
        for path in source.iterdir():
            if path.is_file() and path.suffix in ('.yaml', '.txt'):
                shutil.copyfile(path, shared / path.name)
        for directory in ('lua', 'cn_dicts', 'en_dicts', 'opencc'):
            if (source / directory).is_dir():
                shutil.copytree(source / directory, shared / directory, dirs_exist_ok=True)
    # Native baseline conversions stay separate from the namespaced package.
    prepare_native(upstreams / 'OpenCC/data', shared / 'opencc')
    # Ice's calendar scripts explicitly resolve files under user_data_dir/lua.
    shutil.copytree(shared / 'lua', user / 'lua')
    shutil.copytree(package / 'opencc', user / 'opencc')
    for path in package.glob('*.schema.yaml'):
        shutil.copyfile(path, user / path.name)
    ids = [entry[key] for entry in entries for key in ('base', 'id')]
    custom = {'patch': {'schema_list': [{'schema': sid} for sid in ids]}}
    (user / 'default.custom.yaml').write_text(yaml.safe_dump(custom), encoding='utf-8')


def verify(upstreams: Path, package: Path, probe: Path) -> dict:
    try:
        entries = json.loads((package / 'schemes.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError('Package scheme manifest is unreadable') from error
    report = {'platform': platform.platform(), 'schemes': [],
              'opencc': subprocess.run(['opencc', '--version'], check=True, capture_output=True, text=True).stdout.strip(),
              'files': {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in package.rglob('*') if p.is_file()}}
    with tempfile.TemporaryDirectory(prefix='govrime-verify-') as temp:
        root = Path(temp)
        shared, user = root / 'shared', root / 'user'
        prepare(upstreams, package, shared, user, entries)
        deployment = subprocess.run([str(probe), str(shared), str(user), 'deploy'], capture_output=True, text=True, timeout=600, check=False)
        if deployment.returncode:
            raise ValueError('Rime deployment failed:\n' + deployment.stderr[-8000:])
        report['runtime'] = deployment.stdout.strip()
        for entry in entries:
            sid, family = entry['base'], entry['family']
            if family == 'ice':
                keys = {'rime_ice': 'wei', 'double_pinyin': 'wz', 'double_pinyin_abc': 'wq',
                        'double_pinyin_flypy': 'ww', 'double_pinyin_jiajia': 'ww',
                        'double_pinyin_mspy': 'wz', 'double_pinyin_sogou': 'wz', 'double_pinyin_ziguang': 'wk'}.get(sid)
                if keys is None:
                    # New ice double pinyin: find the code producing 为, then
                    # require the same full-schema behavior as existing schemes.
                    for key in 'abcdefghijklmnopqrstuvwxyz':
                        try:
                            values, _ = query(probe, shared, user, sid, 'w' + key, ['traditionalization=0'])
                        except ValueError:
                            continue
                        if '为' in values:
                            keys = 'w' + key
                            break
                    if keys is None:
                        raise ValueError(f'New double pinyin has no validated wei input: {sid}')
                original_opts = simple_opts = ['traditionalization=0']
                traditional_opts = ['traditionalization=1']
                expected, default_option, default_value = '爲', 'traditionalization', 0
            elif family == 'wubi':
                keys, expected = 'wyl', '僞'
                original_opts, simple_opts = [], ['gov_traditional=0']
                traditional_opts = ['gov_traditional=1']
                default_option, default_value = 'gov_traditional', 0
            else:
                option = 'zh_hans' if family == 'luna' else 'simplification'
                keys, expected = ('wei', '爲') if family == 'luna' else ('oikf', '僞')
                original_opts = [option + '=1']
                simple_opts = [option + '=1', 'gov_traditional=0']
                traditional_opts = [option + '=0', 'gov_traditional=1']
                default_option, default_value = 'gov_traditional', 1
            baseline, _ = query(probe, shared, user, sid, keys, original_opts)
            simplified, defaults = query(probe, shared, user, entry['id'], keys, simple_opts)
            traditional, _ = query(probe, shared, user, entry['id'], keys, traditional_opts)
            check_candidates(baseline, simplified, traditional, expected)
            if defaults[default_option] != default_value:
                raise ValueError(f'Wrong initial state: {sid} {defaults}')
            report['schemes'].append({'id': entry['id'], 'keys': keys, 'expected': expected,
                                      'simplified_unchanged': True, 'traditional_unique': True, 'default_correct': True})
            print('PASS', entry['id'], flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('upstreams', 'package', 'probe', 'report'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.upstreams, args.package, args.probe.resolve())
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
