"""The release gate must reject missing, changed, or duplicate candidates."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def verifier():
    path = Path(__file__).resolve().parents[1] / 'scripts/verify.py'
    spec = importlib.util.spec_from_file_location('verify', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyTests(unittest.TestCase):
    def test_prepare_baseline_uses_classic_configs_not_host_opencc_defaults(self):
        module = verifier()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'data'
            (source / 'config').mkdir(parents=True)
            (source / 'dictionary').mkdir()
            (source / 'dictionary/Chars.txt').write_text('为\t為\n', encoding='utf-8')
            dictionary = {'type': 'ocd2', 'file': 'Chars.ocd2'}
            config = {'name': 'baseline', 'segmentation': {'type': 'mmseg', 'dict': dictionary},
                      'conversion_chain': [{'dict': dictionary}]}
            for name in ('s2t', 't2s', 't2hk', 't2tw'):
                (source / f'config/{name}.json').write_text(json.dumps(config))
            module.prepare_native(source, root / 'native')
            result = subprocess.run(['opencc', '-c', str(root / 'native/s2t.json')], input='为',
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout, '為')

    def test_gate_rejects_invalid_candidates(self):
        module = verifier()
        module.check_candidates(['伪'], ['伪'], ['僞'], '僞')
        for baseline, simplified, traditional in [([], [], ['僞']), (['伪'], ['偽'], ['僞']),
                                                   (['伪'], ['伪'], ['偽']), (['伪'], ['伪'], ['僞', '僞'])]:
            with self.subTest(traditional=traditional, simplified=simplified), self.assertRaises(ValueError):
                module.check_candidates(baseline, simplified, traditional, '僞')


if __name__ == '__main__':
    unittest.main()
