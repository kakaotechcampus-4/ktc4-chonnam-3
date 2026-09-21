import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
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

    def test_real_partial_contract_internal_refs_are_preserved(self):
        document = module.load_yaml_document(module.CONTRACTS/'openapi.yaml')
        result = module.inline_refs(document, module.CONTRACTS)
        schema = result['components']['responses']['Error']['content']['application/json']['schema']
        self.assertEqual(schema['$ref'], '#/components/schemas/ApiError')
        self.assertIn('ApiError', result['components']['schemas'])

    def test_external_schema_file_ref_is_inlined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'me-response.schema.json').write_text(json.dumps({
                '$schema': 'https://json-schema.org/draft/2020-12/schema',
                'type': 'object',
                'properties': {'githubLinked': {'type': 'boolean'}},
            }))
            result = module.inline_refs({'$ref': './me-response.schema.json'}, root)
        self.assertEqual(result['properties']['githubLinked']['type'], 'boolean')
        self.assertNotIn('$schema', result)

    def test_auth_fetch_surface_keeps_browser_routes_separate(self):
        document = module.load_yaml_document(module.CONTRACTS/'openapi.yaml')
        auth_paths = {path for path in document['paths'] if path.startswith('/auth') or path == '/me'}
        self.assertEqual(auth_paths, {
            '/auth/refresh',
            '/auth/logout',
            '/me',
        })
        self.assertEqual(document['paths']['/auth/refresh']['post']['operationId'], 'refreshToken')
        self.assertIn('frontend/docs/api-spec.md', document['info']['description'])
        self.assertNotIn('401', document['paths']['/auth/logout']['post']['responses'])

    def test_auth_and_frontend_contracts_coexist(self):
        document = module.load_yaml_document(module.CONTRACTS/'openapi.yaml')
        schemas = module.inline_refs(document, module.CONTRACTS)['components']['schemas']
        for path in ('/me/profile', '/me/home', '/me/interviews'):
            self.assertIn(path, document['paths'])
        self.assertNotIn('details', schemas['ApiError']['properties']['error']['required'])
        self.assertIn('retryAfter', schemas['ApiError']['properties']['error']['properties'])
        Draft202012Validator(schemas['MeResponse']).validate({
            'name': 'User', 'avatarUrl': None, 'githubLinked': True,
        })
        self.assertIn('extractStatus', schemas['DocumentPreviewResponse']['required'])
        self.assertIn('id', schemas['RepositoryCard']['required'])
        self.assertIn('skipped', schemas['StepStatus']['enum'])

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
