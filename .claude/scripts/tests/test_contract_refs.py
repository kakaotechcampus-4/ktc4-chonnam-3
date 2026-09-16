import importlib.util
import tempfile
import unittest
from pathlib import Path

from yaml.constructor import ConstructorError

spec = importlib.util.spec_from_file_location('check_contracts', Path(__file__).resolve().parents[1]/'check_contracts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RefTests(unittest.TestCase):
    def test_yaml_documents_are_loaded_without_json_subset_restrictions(self):
        loader = getattr(module, 'load_yaml_document', None)
        self.assertIsNotNone(loader, 'checker must expose its safe YAML loader')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'openapi.yaml'
            path.write_text('openapi: 3.1.0\ninfo:\n  title: DEVON\n  version: 1.0.0\n')
            self.assertEqual(loader(path)['info']['title'], 'DEVON')

    def test_yaml_loader_rejects_python_object_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'unsafe.yaml'
            path.write_text('value: !!python/object/apply:builtins.str [unsafe]\n')
            with self.assertRaises(ConstructorError):
                module.load_yaml_document(path)

    def test_internal_component_ref_is_preserved_for_openapi_validator(self):
        reference = '#/components/schemas/ApiError'
        self.assertEqual(module.inline_refs({'$ref': reference}, module.CONTRACTS), {'$ref': reference})

    def test_real_partial_contract_refs_resolve(self):
        document = module.load_yaml_document(module.CONTRACTS/'openapi.yaml')
        result = module.inline_refs(document, module.CONTRACTS)
        response_ref = result['paths']['/me']['get']['responses']['200']['content']['application/json']['schema']
        self.assertEqual(response_ref, {'$ref': '#/components/schemas/MeResponse'})
        schema = result['components']['schemas']['MeResponse']
        self.assertEqual(schema['properties']['githubLinked']['type'], 'boolean')

    def test_auth_surface_and_cookie_schemes_are_complete(self):
        document = module.load_yaml_document(module.CONTRACTS/'openapi.yaml')
        auth_paths = {path for path in document['paths'] if path.startswith('/auth') or path == '/me'}
        self.assertEqual(auth_paths, {
            '/auth/github/login',
            '/auth/github/callback',
            '/auth/refresh',
            '/auth/logout',
            '/me',
        })
        self.assertEqual(set(document['components']['securitySchemes']), {
            'AccessTokenCookie',
            'RefreshTokenCookie',
            'OAuthStateCookie',
        })

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
