"""Reusable HTTPS connections with cancellable requests on a dedicated event loop."""
import asyncio
from collections import Counter
from concurrent.futures import CancelledError, TimeoutError
from threading import Lock, Thread

import httpx

from .cancellation import check_cancelled
from .google_translate import (CLOUD_ENDPOINT, PUBLIC_ENDPOINT, TranslationError,
    _check_response, _parse_official, _parse_public, _public_groups, _validate)
from .models import TranslationResult


def _new_client(proxy):
    return httpx.AsyncClient(proxy=proxy or None, verify=True, follow_redirects=False,
        timeout=httpx.Timeout(20, connect=8, pool=8),
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=3, keepalive_expiry=120),
        headers={'User-Agent': 'ScreenshotTranslate/1.0', 'Accept': 'application/json'})


class InterruptibleTranslationService:
    """Blocking worker API; cancelling aborts the underlying async HTTP task."""
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run_loop, name='translation-http', daemon=True)
        self._lock = Lock()
        self._closed = False
        self._tasks = set()
        self._clients = {}
        self._current = None
        self._proxy = None
        self._thread.start()

    def _run_loop(self):
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def translate(self, texts, target='zh-CN', source='auto', api_key='', proxy='', provider='public',
                  *, cancel_event=None):
        check_cancelled(cancel_event)
        _validate(texts, target, source, provider, proxy)
        if provider == 'official' and not api_key.strip():
            raise TranslationError('使用谷歌 Cloud 翻译需要 API Key，请先在设置中填写。')
        with self._lock:
            if self._closed:
                raise TranslationError('翻译服务已关闭，请重新启动翻译助手。')
            future = asyncio.run_coroutine_threadsafe(
                self._translate(texts, target, source, api_key, proxy, provider), self._loop)
        try:
            while True:
                check_cancelled(cancel_event)
                try:
                    return future.result(timeout=.05)
                except TimeoutError:
                    if future.done():
                        raise
                    continue
        except CancelledError:
            future.cancel()
            raise

    async def _translate(self, texts, target, source, api_key, proxy, provider):
        task = asyncio.current_task()
        self._tasks.add(task)
        client = None
        try:
            indices = [i for i, text in enumerate(texts) if text.strip()]
            if not indices:
                return TranslationResult(list(texts))
            if self._current is None or self._proxy != proxy:
                previous = self._current
                client = _new_client(proxy)
                self._current, self._proxy = client, proxy
                if previous is not None and self._clients.get(previous, 0) == 0:
                    self._clients.pop(previous, None)
                    await previous.aclose()
            client = self._current
            self._clients[client] = self._clients.get(client, 0) + 1
            active = [texts[i] for i in indices]
            if provider == 'official':
                body = {'q': active, 'target': target, 'format': 'text'}
                if source != 'auto':
                    body['source'] = source
                response = await client.post(CLOUD_ENDPOINT, headers={'X-Goog-Api-Key': api_key.strip()}, json=body)
                translated = _parse_official(_check_response(response, 'official'), len(active))
            else:
                semaphore = asyncio.Semaphore(3)
                async def one(text):
                    response = await client.get(PUBLIC_ENDPOINT,
                        params={'client': 'gtx', 'sl': source, 'tl': target, 'dt': 't', 'q': text})
                    return _parse_public(_check_response(response, 'public'))
                async def group(items):
                    async with semaphore:
                        if len(items) == 1:
                            return [await one(items[0][1])]
                        text, language = await one('\n'.join(text for _, text in items))
                        lines = text.replace('\r\n', '\n').split('\n')
                        if len(lines) == len(items) and all(line.strip() for line in lines):
                            return [(line, language) for line in lines]
                        return [await one(text) for _, text in items]
                groups = list(_public_groups(active))
                requests = [asyncio.create_task(group(items)) for items in groups]
                try:
                    results = await asyncio.gather(*requests)
                finally:
                    for request in requests:
                        if not request.done():
                            request.cancel()
                    await asyncio.gather(*requests, return_exceptions=True)
                pairs = [('', '')] * len(active)
                for items, values in zip(groups, results, strict=True):
                    for (index, _), value in zip(items, values, strict=True):
                        pairs[index] = value
                languages = [language for _, language in pairs if language]
                translated = TranslationResult([text for text, _ in pairs],
                    Counter(languages).most_common(1)[0][0] if languages else '')
            output = list(texts)
            for index, text in zip(indices, translated.texts, strict=True):
                output[index] = text
            return TranslationResult(output, translated.detected_language)
        except (httpx.TimeoutException, asyncio.TimeoutError):
            raise TranslationError('连接谷歌翻译超时，请检查网络或代理设置后重试。') from None
        except httpx.ProxyError:
            raise TranslationError('无法连接代理服务器，请检查代理地址和端口。') from None
        except httpx.HTTPError:
            raise TranslationError('无法连接谷歌翻译，请检查网络、代理和系统证书设置。') from None
        except (ValueError, ImportError, httpx.InvalidURL):
            raise TranslationError('网络或代理配置无效，请检查设置。') from None
        finally:
            if client in self._clients:
                self._clients[client] -= 1
                if self._clients[client] == 0 and client is not self._current:
                    self._clients.pop(client)
                    await client.aclose()
            self._tasks.discard(task)

    async def _shutdown(self):
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        clients = set(self._clients)
        if self._current is not None:
            clients.add(self._current)
        await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)
        self._clients.clear()
        self._current = None
        self._loop.call_soon(self._loop.stop)

    def close(self, wait=False):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._shutdown_future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        if wait:
            self._shutdown_future.result(timeout=5)
            self._thread.join(timeout=5)
