"""Catch lost conversion stages, unsafe paths, and wrong switch/filter adaptation."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/generate.py'


def generator():
    if not SCRIPT.exists():
        raise AssertionError('scripts/generate.py has not been implemented')
    spec = importlib.util.spec_from_file_location('generate', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema(family):
    data = {'schema': {'schema_id': 'wubi86', 'name': '五笔86'},
            'switches': [{'name': 'ascii_mode', 'reset': 0}],
            'engine': {'filters': []}}
    if family == 'ice':
        data['schema'] = {'schema_id': 'rime_ice', 'name': '雾凇拼音'}
        data['switches'].append({'name': 'traditionalization', 'states': ['简', '繁']})
        data['engine']['filters'] = ['simplifier@emoji', 'simplifier@traditionalize', 'uniquifier']
        data['traditionalize'] = {'option_name': 'traditionalization', 'opencc_config': 's2t.json', 'tags': ['abc']}
    elif family == 'luna':
        data['schema'] = {'schema_id': 'luna_pinyin', 'name': '朙月拼音'}
        data['switches'].append({'options': ['zh_hant', 'zh_hans', 'zh_hant_hk', 'zh_hant_tw'], 'states': ['傳統', '简化', '港', '臺']})
        data['engine']['filters'] = ['simplifier@zh_hans', 'simplifier@zh_hant_hk', 'simplifier@zh_hant_tw', 'uniquifier']
    elif family == 'cangjie':
        data['schema'] = {'schema_id': 'cangjie5', 'name': '倉頡五代'}
        data['switches'].append({'name': 'simplification', 'states': ['漢字', '汉字']})
        data['engine']['filters'] = ['simplifier', 'uniquifier', 'single_char_filter']
    return data


class GenerateTests(unittest.TestCase):
    def test_four_families_preserve_defaults_and_finish_conversion_before_dedup(self):
        g = generator()
        for family, suffix in [('ice', '大陆'), ('luna', '大陸'), ('cangjie', '大陸'), ('wubi', '大陆')]:
            with self.subTest(family=family):
                source = schema(family)
                result = g.generate_schema(source, family, suffix)
                patch = result['__patch']
                self.assertEqual(result['schema']['schema_id'], source['schema']['schema_id'] + '_gov')
                self.assertEqual(result['schema']['name'], source['schema']['name'] + suffix)
                filters = patch['engine/filters']
                self.assertLess(filters.index('simplifier@gov_traditional'), filters.index('uniquifier'))
                self.assertEqual(patch['switches'][0], source['switches'][0])
                if family in ('luna', 'cangjie'):
                    self.assertEqual(patch['switches'][1]['reset'], 0)
                    self.assertEqual(len(patch['switches'][1]['options']), 2)
                if family == 'wubi':
                    self.assertEqual(patch['switches'][-1]['reset'], 0)
                if family == 'ice':
                    self.assertEqual(patch['gov_traditional']['tags'], ['abc'])
                    self.assertIn('simplifier@emoji', filters)
                if family == 'cangjie':
                    self.assertEqual(filters[-1], 'single_char_filter')

    def test_name_suffix_uses_display_text_and_requires_ambiguous_override(self):
        g = generator()
        self.assertEqual(g.name_suffix('雾凇拼音'), '大陆')
        self.assertEqual(g.name_suffix('倉頡五代'), '大陸')
        with self.assertRaises(ValueError):
            g.name_suffix('朙月拼音')
        with self.assertRaises(ValueError):
            g.name_suffix('小鹤雙拼')

    def test_package_discovers_only_ice_double_pinyin_and_preserves_input(self):
        g = generator()
        import yaml
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for repo, family, ids in [
                ('rime-ice', 'ice', ['rime_ice', 'double_pinyin_new', 't9']),
                ('rime-luna-pinyin', 'luna', ['luna_pinyin']),
                ('rime-cangjie', 'cangjie', ['cangjie5']),
                ('rime-wubi', 'wubi', ['wubi86']),
            ]:
                directory = root / repo
                directory.mkdir()
                for sid in ids:
                    data = schema(family)
                    data['schema']['schema_id'] = sid
                    (directory / (sid + '.schema.yaml')).write_text(yaml.safe_dump(data, allow_unicode=True))
            sources = g.discover_schemas(root)
            self.assertEqual({d['schema']['schema_id'] for d, _ in sources},
                             {'rime_ice', 'double_pinyin_new', 'luna_pinyin', 'cangjie5', 'wubi86'})

    def test_unknown_upstream_structure_fails_closed(self):
        g = generator()
        data = schema('ice')
        data['engine']['filters'].remove('simplifier@traditionalize')
        with self.assertRaises(ValueError):
            g.generate_schema(data, 'ice', '大陆')

    def test_compile_normalization_and_reject_path_escape(self):
        g = generator()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = root / 'source', root / 'target'
            source.mkdir()
            (source / 'normalize.txt').write_text('神\t神\n', encoding='utf-8')
            (source / 'characters.txt').write_text('裏\t里\n', encoding='utf-8')
            config = {'name': 'test', 'normalization': [{'dict': {'type': 'text', 'file': 'normalize.txt'}}],
                      'conversion_chain': [{'dict': {'type': 'text', 'file': 'characters.txt'}}]}
            for name in ('t2gov_keep_simp', 's2t'):
                (source / (name + '.json')).write_text(json.dumps(config), encoding='utf-8')
            g.compile_opencc(source, target)
            compiled = target / 'govrime_t2gov_keep_simp.json'
            actual = subprocess.run(['opencc', '-c', str(compiled)], input='神裏', text=True, capture_output=True, check=True)
            self.assertEqual(actual.stdout, '神里')
            payload = json.loads(compiled.read_text())
            self.assertEqual(len(payload['conversion_chain']), 2)
            self.assertNotIn('normalization', payload)
            self.assertTrue(all(p.name.startswith('govrime_') for p in target.iterdir()))
            config['conversion_chain'][0]['dict']['file'] = '../outside.txt'
            (source / 's2t.json').write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                g.compile_opencc(source, root / 'unsafe')


if __name__ == '__main__':
    unittest.main()
