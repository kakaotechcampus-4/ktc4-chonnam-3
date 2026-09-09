import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('check_contracts', Path(__file__).resolve().parents[1]/'check_contracts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RefTests(unittest.TestCase):
    def test_real_partial_contract_refs_resolve(self):
        document = json.loads((module.CONTRACTS/'openapi.yaml').read_text())
        result = module.inline_refs(document, module.CONTRACTS)
        schema = result['paths']['/me']['get']['responses']['200']['content']['application/json']['schema']
        self.assertEqual(schema['properties']['githubLinked']['type'], 'boolean')

    def test_remote_ref_is_rejected_without_network(self):
        with self.assertRaises(ValueError):
            module.inline_refs({'$ref': 'https://example.com/schema'}, module.CONTRACTS)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            module.inline_refs({'$ref': './../outside.schema.json'}, module.CONTRACTS)

    def test_cycles_fail_instead_of_recursing_forever(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'loop.schema.json').write_text('{"$ref":"./loop.schema.json"}')
            with self.assertRaises(ValueError):
                module.inline_refs({'$ref':'./loop.schema.json'}, root)


if __name__ == '__main__':
    unittest.main()
