import asyncio
from concurrent.futures import CancelledError, ThreadPoolExecutor
from threading import Event

import httpx
import pytest

from screen_translate import async_translate
from screen_translate.async_translate import InterruptibleTranslationService


def test_cancel_aborts_http_request_and_accepts_next_translation(monkeypatch):
    started, aborted, cancel = Event(), Event(), Event()
    async def handler(request):
        if request.url.params['q'] == 'slow':
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                aborted.set()
                raise
        return httpx.Response(200, json=[[[request.url.params['q'].upper()]], None, 'en'])
    clients = []
    def create(proxy):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return client
    monkeypatch.setattr(async_translate, '_new_client', create)
    service = InterruptibleTranslationService()
    try:
        with ThreadPoolExecutor(max_workers=1) as worker:
            pending = worker.submit(service.translate, ['slow'], cancel_event=cancel)
            assert started.wait(2)
            cancel.set()
            with pytest.raises(CancelledError):
                pending.result(timeout=2)
        assert aborted.wait(2)
        assert service.translate(['next']).texts == ['NEXT']
        assert len(clients) == 1
    finally:
        service.close(wait=True)
    assert clients[0].is_closed
    assert not service._thread.is_alive()


def test_async_batch_order_empty_positions_and_collapse_fallback(monkeypatch):
    calls = []
    async def handler(request):
        text = request.url.params['q']
        calls.append(text)
        value = 'collapsed' if '\n' in text else text.upper()
        return httpx.Response(200, json=[[[value]], None, 'en'])
    monkeypatch.setattr(async_translate, '_new_client', lambda _: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    service = InterruptibleTranslationService()
    try:
        assert service.translate(['one', '', 'two']).texts == ['ONE', '', 'TWO']
        assert calls == ['one\ntwo', 'one', 'two']
    finally:
        service.close(wait=True)


def test_async_official_key_redacted_and_proxy_connections_retired(monkeypatch):
    clients = []
    attempts = 0
    async def handler(request):
        nonlocal attempts
        attempts += 1
        assert request.headers['X-Goog-Api-Key'] == 'private-key'
        if attempts == 1:
            raise httpx.ConnectError('private-key and proxy-password', request=request)
        return httpx.Response(200, json={'data': {'translations': [{'translatedText': '一 &amp; 二'}]}})
    def create(proxy):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return client
    monkeypatch.setattr(async_translate, '_new_client', create)
    service = InterruptibleTranslationService()
    try:
        with pytest.raises(async_translate.TranslationError) as error:
            service.translate(['one'], provider='official', api_key='private-key')
        assert 'private-key' not in str(error.value) and 'proxy-password' not in str(error.value)
        assert service.translate(['one'], provider='official', api_key='private-key', proxy='http://127.0.0.1:8080').texts == ['一 & 二']
        assert clients[0].is_closed
    finally:
        service.close(wait=True)
    assert all(client.is_closed for client in clients)
