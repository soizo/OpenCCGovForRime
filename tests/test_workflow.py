"""Execute the publish shell against a fake remote; failed uploads stay drafts."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


class WorkflowTests(unittest.TestCase):
        def test_upload_failure_never_exposes_release_and_retry_recovers(self):
                root = Path(__file__).resolve().parents[1]
                workflow = yaml.safe_load(
                        (root / ".github/workflows/release.yml").read_text()
                )
                script = workflow["jobs"]["publish"]["steps"][-1]["run"]
                with tempfile.TemporaryDirectory() as temp:
                        directory = Path(temp)
                        gh = directory / "gh"
                        gh.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ['STATE'])
state = json.loads(path.read_text()) if path.exists() else {}
args = sys.argv[1:]
if args[0] == 'api':
    if state: print(os.environ['TAG'] + '\\t' + str(state['draft']).lower())
elif args[:2] == ['release', 'create']:
    state = {'draft': '--draft' in args, 'asset': False}
    path.write_text(json.dumps(state))
    if os.environ.get('FAIL_UPLOAD') == '1': sys.exit(1)
    state['asset'] = True
elif args[:2] == ['release', 'upload']:
    if os.environ.get('FAIL_UPLOAD') == '1': sys.exit(1)
    state['asset'] = True
elif args[:2] == ['release', 'edit']:
    if not state.get('asset'): sys.exit(2)
    state['draft'] = False
else:
    sys.exit(3)
if state: path.write_text(json.dumps(state))
""")
                        gh.chmod(0o755)
                        state = directory / "state.json"
                        env = {
                                **os.environ,
                                "PATH": str(directory)
                                + os.pathsep
                                + os.environ["PATH"],
                                "TAG": "gov-" + "a" * 64,
                                "COMMIT": "b" * 40,
                                "GH_REPO": "example/test",
                                "NOTES": "test",
                                "STATE": str(state),
                                "FAIL_UPLOAD": "1",
                        }
                        failed = subprocess.run(
                                ["bash", "-euo", "pipefail", "-c", script],
                                env=env,
                                capture_output=True,
                                text=True,
                                check=False,
                        )
                        self.assertNotEqual(failed.returncode, 0)
                        self.assertEqual(
                                json.loads(state.read_text()),
                                {"draft": True, "asset": False},
                        )
                        env["FAIL_UPLOAD"] = "0"
                        subprocess.run(
                                ["bash", "-euo", "pipefail", "-c", script],
                                env=env,
                                capture_output=True,
                                text=True,
                                check=True,
                        )
                        self.assertEqual(
                                json.loads(state.read_text()),
                                {"draft": False, "asset": True},
                        )


if __name__ == "__main__":
        unittest.main()
