"""Run from the project root: python -m unittest discover -s backend/tests -v."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.api.routes.models import router
from app.core.config import settings
from app.core.model_keys import decrypt_api_key
from app.core.security import create_access_token
from app.db.database import Base, get_db_session
from app.models import User, ModelConfig
from app.rag.llm_service import LLMError, LLMService
from app.rag.model_registry import PROVIDERS, resolve_llm
from app.schemas.model_config import ModelConfigInput


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_provider_protocols_and_stream_usage_chunks(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider['id']):
                requests = []

                def handle(request):
                    requests.append(request)
                    payload = json.loads(request.content)
                    if payload['stream']:
                        return httpx.Response(200, text='data:{"choices":[]}\n\ndata: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n\n')
                    return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})

                service = LLMService(provider=provider['id'], api_key='' if provider['id'] == 'ollama' else 'test-only-key', base_url='http://test.local/v1', model='test-model', allow_mock=False)
                service._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
                try:
                    self.assertEqual(await service.chat([{'role': 'user', 'content': 'test'}], temperature=0), 'OK')
                    self.assertEqual(''.join([part async for part in service.chat([], stream=True)]), 'OK')
                    self.assertEqual(requests[0].url.path, '/v1/chat/completions')
                    self.assertEqual(json.loads(requests[0].content)['temperature'], 0)
                    if provider['id'] == 'ollama':
                        self.assertNotIn('authorization', requests[0].headers)
                    else:
                        self.assertEqual(requests[0].headers['authorization'], 'Bearer test-only-key')
                finally:
                    await service.close()

    async def test_reasoning_parameters_and_safe_errors(self):
        service = LLMService(provider='openrouter', model='openai/gpt-5', api_key='test-secret', allow_mock=False)
        data = service._payload([], False, 0, 2048)
        self.assertNotIn('temperature', data)
        self.assertEqual(data['max_completion_tokens'], 2048)
        service._http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={'error': 'test-secret'})))
        try:
            with self.assertRaises(LLMError) as error:
                await service.chat([])
            self.assertIn('401', str(error.exception))
            self.assertNotIn('test-secret', str(error.exception))
        finally:
            await service.close()

    def test_url_validation_and_ollama_normalization(self):
        payload = dict(name='test', provider='ollama', model='qwen3:4b', base_url='http://localhost:11434')
        self.assertEqual(ModelConfigInput(**payload).base_url, 'http://localhost:11434/v1')
        payload['base_url'] = 'https://example.com/v1/chat/completions/'
        self.assertEqual(ModelConfigInput(**payload).base_url, 'https://example.com/v1')
        for url in ['file:///etc/passwd', 'https://key@example.com/v1', 'https://example.com?api_key=secret', 'https://{WorkspaceId}.example.com/v1']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ModelConfigInput(**{**payload, 'base_url': url})


class ModelApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.key_patch = patch.object(settings, 'MODEL_ENCRYPTION_KEY_FILE', str(Path(self.directory.name) / 'key'))
        self.key_patch.start()
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as session:
            session.add_all([User(id=i, username=f'user{i}', email=f'user{i}@example.com', hashed_password='unused', role='developer') for i in [1, 2]])
            await session.commit()
        self.app = FastAPI()
        self.app.include_router(router, prefix='/api/v1')

        async def database():
            async with self.sessions() as session:
                yield session

        self.app.dependency_overrides[get_db_session] = database
        self.auth1 = {'Authorization': 'Bearer ' + create_access_token({'sub': '1'})}
        self.auth2 = {'Authorization': 'Bearer ' + create_access_token({'sub': '2'})}
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://app.local', headers=self.auth1)
        self.payload = dict(name='编程模型', provider='deepseek', base_url='https://api.deepseek.com', model='deepseek-flash', api_key='test-only-secret', is_default=False)

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.dispose()
        self.key_patch.stop()
        self.directory.cleanup()

    async def create(self, **changes):
        response = await self.client.post('/api/v1/models', json={**self.payload, **changes})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def test_encryption_key_preservation_and_defaults(self):
        first = await self.create()
        second = await self.create(name='另一个模型', model='second')
        self.assertTrue(first['is_default'])
        self.assertFalse(second['is_default'])
        self.assertNotIn('api_key', first)
        self.assertNotIn('test-only-secret', json.dumps(first))
        async with self.sessions() as session:
            row = await session.get(ModelConfig, first['id'])
            self.assertNotEqual(row.encrypted_api_key, 'test-only-secret')
            self.assertEqual(decrypt_api_key(row.encrypted_api_key), 'test-only-secret')
        updated = {**self.payload, 'name': '重命名'}
        updated.pop('api_key')
        self.assertEqual((await self.client.put(f"/api/v1/models/{first['id']}", json=updated)).status_code, 200)
        async with self.sessions() as session:
            row = await session.get(ModelConfig, first['id'])
            self.assertEqual(decrypt_api_key(row.encrypted_api_key), 'test-only-secret')
        self.assertEqual((await self.client.post(f"/api/v1/models/{second['id']}/default")).status_code, 200)
        listing = (await self.client.get('/api/v1/models')).json()
        self.assertEqual([row['id'] for row in listing if row['is_default']], [second['id']])
        self.assertEqual((await self.client.delete(f"/api/v1/models/{second['id']}")).status_code, 204)
        self.assertTrue((await self.client.get('/api/v1/models')).json()[0]['is_default'])

    async def test_authentication_and_cross_user_isolation(self):
        profile = await self.create()
        self.assertEqual((await self.client.get('/api/v1/models', headers={'Authorization': ''})).status_code, 401)
        self.assertEqual((await self.client.get('/api/v1/models', headers=self.auth2)).json(), [])
        for method, path in [('put', ''), ('delete', ''), ('post', '/test'), ('post', '/default')]:
            arguments = {'json': self.payload} if method == 'put' else {}
            response = await getattr(self.client, method)(f"/api/v1/models/{profile['id']}{path}", headers=self.auth2, **arguments)
            self.assertEqual(response.status_code, 404)
        for action in ['discover', 'test-connection']:
            response = await self.client.post(f"/api/v1/models/{action}?model_id={profile['id']}", headers=self.auth2, json=self.payload)
            self.assertEqual(response.status_code, 404)

    async def test_validation_and_provider_change_does_not_reuse_key(self):
        response = await self.client.post('/api/v1/models', json={**self.payload, 'api_key': ''})
        self.assertEqual(response.status_code, 400)
        response = await self.client.post('/api/v1/models', json={**self.payload, 'name': '   '})
        self.assertEqual(response.status_code, 422)
        profile = await self.create()
        changed = {**self.payload, 'provider': 'openai', 'base_url': 'https://api.openai.com/v1'}
        changed.pop('api_key')
        self.assertEqual((await self.client.put(f"/api/v1/models/{profile['id']}", json=changed)).status_code, 400)
        local = await self.create(provider='ollama', base_url='http://localhost:11434', model='qwen3:4b', api_key='')
        self.assertFalse(local['has_api_key'])
        self.assertEqual(local['base_url'], 'http://localhost:11434/v1')

    async def test_connection_and_model_discovery_use_saved_key(self):
        profile = await self.create()
        seen = []

        def handler(request):
            seen.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'data': [{'id': 'b'}, {'id': 'a'}]})
            return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})

        def client(service):
            service._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return service._http_client

        body = {**self.payload}
        body.pop('api_key')
        with patch.object(LLMService, '_get_client', client):
            response = await self.client.post(f"/api/v1/models/test-connection?model_id={profile['id']}", json=body)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['response'], 'OK')
        real_client = httpx.AsyncClient
        with patch('app.api.routes.models.httpx.AsyncClient', side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)):
            response = await self.client.post(f"/api/v1/models/discover?model_id={profile['id']}", json=body)
            self.assertEqual(response.json()['models'], ['a', 'b'])
        self.assertTrue(all(request.headers['Authorization'] == 'Bearer test-only-secret' for request in seen))

    async def test_selected_and_default_connections_are_independent(self):
        first = await self.create(model='first')
        second = await self.create(model='second', api_key='second-secret')
        async with self.sessions() as session:
            a = await resolve_llm(session, 1, first['id'])
            b = await resolve_llm(session, 1, second['id'])
            default = await resolve_llm(session, 1, None)
        self.assertEqual((a._model, b._model, default._model), ('first', 'second', 'first'))
        self.assertEqual((a._api_key, b._api_key), ('test-only-secret', 'second-secret'))

    async def test_rag_and_agent_routes_select_model_including_streaming(self):
        from app.api.routes import chat
        self.app.include_router(chat.router, prefix='/api/v1')
        first = await self.create(model='first')
        second = await self.create(model='second')

        class Pipeline:
            def __init__(self, llm):
                self.llm = llm

            async def answer(self, **kwargs):
                return {'answer': self.llm._model, 'sources': [], 'thinking': ''}

            run = answer

            async def stream_answer(self, **kwargs):
                yield {'type': 'token', 'data': self.llm._model}
                yield {'type': 'done', 'data': {'answer': self.llm._model, 'sources': []}}

            stream_run = stream_answer

        with patch.object(chat, 'RAGPipeline', Pipeline), patch.object(chat, 'CodeAgent', Pipeline), patch('app.db.database.async_session_factory', self.sessions):
            for mode in ['rag', 'agent']:
                with self.subTest(mode=mode):
                    response = await self.client.post('/api/v1/chat/ask', json={'query': 'test', 'mode': mode, 'model_id': second['id']})
                    self.assertEqual(response.json()['answer'], 'second')
                    response = await self.client.post('/api/v1/chat/ask', json={'query': 'test', 'mode': mode})
                    self.assertEqual(response.json()['answer'], 'first')
                    response = await self.client.post('/api/v1/chat/stream', json={'query': 'test', 'mode': mode, 'model_id': second['id']})
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('event: done', response.text)
                    self.assertIn('second', response.text)
                    response = await self.client.post('/api/v1/chat/stream', headers=self.auth2, json={'query': 'test', 'mode': mode, 'model_id': first['id']})
                    self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
