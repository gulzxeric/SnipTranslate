import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest

from screen_translate import google_translate
from screen_translate.google_translate import TranslationError, TranslationService, translate


def test_public_preserves_block_order_empty_positions_and_sentence_segments():
    seen = []

    def handler(request):
        assert request.url.host == "translate.googleapis.com"
        assert request.url.params["client"] == "gtx"
        assert request.url.params["sl"] == "auto"
        text = request.url.params["q"]
        seen.append(text)
        if '\n' in text:
            value = '\n'.join(f'译文:{line}。' for line in text.split('\n'))
            return httpx.Response(200, json=[[[value, text]], None, 'en'])
        return httpx.Response(200, json=[[[f"译文:{text}", text], ["。", "!"]], None, "en"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = translate(["second", "", "first", "  ", "second"], client=client)
    assert result.texts == ["译文:second。", "", "译文:first。", "  ", "译文:second。"]
    assert result.detected_language == "en"
    assert seen == ["second\nfirst\nsecond"]


def test_public_batch_collapsed_lines_falls_back_without_misplacing_regions():
    seen = []
    def handler(request):
        text = request.url.params['q']
        seen.append(text)
        value = '合并了两段' if '\n' in text else f'译文:{text}'
        return httpx.Response(200, json=[[[value, text]], None, 'en'])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert translate(['one', 'two'], client=client).texts == ['译文:one', '译文:two']
    assert seen == ['one\ntwo', 'one', 'two']


def test_public_multiline_input_and_large_blocks_remain_separate():
    seen = []
    def handler(request):
        text = request.url.params['q']
        seen.append(text)
        return httpx.Response(200, json=[[[text.upper(), text]], None, 'en'])
    texts = ['a\nb', 'c'*2800, 'd'*2800, 'e']
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert translate(texts, client=client).texts == [item.upper() for item in texts]
    assert 'a\nb' in seen and 'c'*2800 in seen and 'd'*2800+'\ne' in seen


def test_official_posts_batch_keeps_key_out_of_url_and_decodes_html():
    def handler(request):
        assert request.method == "POST"
        assert request.url.host == "translation.googleapis.com"
        assert "private-key" not in str(request.url)
        assert request.headers["x-goog-api-key"] == "private-key"
        assert json.loads(request.content) == {"q": ["one", "two"], "target": "zh-CN", "format": "text"}
        return httpx.Response(200, json={"data": {"translations": [
            {"translatedText": "一 &amp; 二", "detectedSourceLanguage": "en"},
            {"translatedText": "第二", "detectedSourceLanguage": "en"},
        ]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = translate(["one", "", "two"], api_key="private-key", provider="official", client=client)
    assert result.texts == ["一 & 二", "", "第二"]
    assert result.detected_language == "en"


def test_official_passes_explicit_source():
    def handler(request):
        assert json.loads(request.content)["source"] == "en"
        return httpx.Response(200, json={"data": {"translations": [{"translatedText": "你好"}]}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert translate(["hello"], source="en", api_key="key", provider="official", client=client).texts == ["你好"]


@pytest.mark.parametrize("status,expected", [(429, "频繁"), (403, "拒绝"), (503, "暂时不可用"), (400, "请求失败")])
def test_http_failures_are_actionable_and_never_return_source(status, expected):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text="private-key"))) as client:
        with pytest.raises(TranslationError, match=expected) as error:
            translate(["hello"], client=client)
    assert "private-key" not in str(error.value)


@pytest.mark.parametrize("payload", [{}, [], [None], [[[]]], [[[None]]], [[[]], None, "en"]])
def test_malformed_public_payload_is_an_error(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        with pytest.raises(TranslationError):
            translate(["hello"], client=client)


def test_truncated_official_batch_is_not_paired_to_wrong_blocks():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "data": {"translations": [{"translatedText": "你好"}]}
    }))) as client:
        with pytest.raises(TranslationError, match="行数"):
            translate(["hello", "world"], api_key="key", provider="official", client=client)


def test_captive_portal_html_is_not_treated_as_translation():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html>sign in</html>"))) as client:
        with pytest.raises(TranslationError, match="无效数据"):
            translate(["hello"], client=client)


@pytest.mark.parametrize("error_type,expected", [(httpx.ConnectTimeout, "超时"), (httpx.ProxyError, "代理"), (httpx.ConnectError, "无法连接")])
def test_network_error_does_not_echo_sensitive_exception_details(error_type, expected):
    def handler(request):
        raise error_type("proxy password and private-key", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TranslationError, match=expected) as error:
            translate(["hello"], client=client)
    assert "private-key" not in str(error.value)
    assert "password" not in str(error.value)


@pytest.mark.parametrize("kwargs", [
    {"texts": ["x"] * 129},
    {"texts": ["x" * 4001]},
    {"texts": ["x" * 4000] * 6},
    {"texts": ["hello"], "provider": "unknown"},
    {"texts": ["hello"], "provider": "official"},
    {"texts": ["hello"], "proxy": "invalid-proxy"},
    {"texts": ["hello"], "target": "auto"},
])
def test_invalid_settings_and_oversized_input_fail_before_network(kwargs):
    def handler(request):
        pytest.fail("Invalid input must not trigger a request")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TranslationError):
            translate(**kwargs, client=client)


def test_empty_input_needs_no_request():
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("No network needed"))) as client:
        assert translate([], client=client).texts == []
        assert translate(["", "  "], client=client).texts == ["", "  "]


def test_official_network_exception_remains_redacted_in_exception_logs(caplog):
    secret = "private-cloud-key-never-log"

    def handler(request):
        raise httpx.ConnectError(f"Rejected API key {secret}", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            translate(["hello"], provider="official", api_key=secret, client=client)
        except TranslationError:
            logging.getLogger("test.translation").exception("Translation job failed")
    assert "Translation job failed" in caplog.text
    assert secret not in caplog.text


@pytest.fixture
def service_clients(monkeypatch):
    clients = []

    def install(handler):
        def create(proxy):
            client = httpx.Client(transport=httpx.MockTransport(handler))
            clients.append((proxy, client))
            return client

        monkeypatch.setattr(google_translate, "_new_client", create)
        return TranslationService(), clients

    return install


def test_service_reuses_client_without_caching_results_or_api_keys(service_clients):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": {"translations": [{"translatedText": "你好"}]}})
        return httpx.Response(200, json=[[["你好", "hello"]], None, "en"])

    service, clients = service_clients(handler)
    try:
        assert service.translate(["hello"]).texts == ["你好"]
        assert service.translate(["hello"]).texts == ["你好"]
        service.translate(["hello"], provider="official", api_key="first-key")
        service.translate(["hello"], provider="official", api_key="second-key")
        service.translate(["hello"], target="ja")
        assert len(clients) == 1
        assert not clients[0][1].is_closed
        assert len(requests) == 5
        assert requests[2].headers["X-Goog-Api-Key"] == "first-key"
        assert requests[3].headers["X-Goog-Api-Key"] == "second-key"
        assert "X-Goog-Api-Key" not in requests[4].headers
        assert requests[4].url.params["tl"] == "ja"
    finally:
        service.close()
    assert clients[0][1].is_closed
    service.close()
    with pytest.raises(TranslationError, match="已关闭"):
        service.translate(["hello"])
    assert len(clients) == 1


def test_service_replaces_connection_when_proxy_changes_and_when_cleared(service_clients):
    service, clients = service_clients(lambda request: httpx.Response(200, json=[[["你好"]]]))
    try:
        service.translate(["hello"], proxy="http://127.0.0.1:8080")
        service.translate(["hello"], proxy="http://127.0.0.1:8081")
        assert clients[0][1].is_closed
        assert not clients[1][1].is_closed
        service.translate(["hello"], proxy="")
        assert clients[1][1].is_closed
        assert not clients[2][1].is_closed
        assert [proxy for proxy, _ in clients] == ["http://127.0.0.1:8080", "http://127.0.0.1:8081", ""]
    finally:
        service.close()
    assert all(client.is_closed for _, client in clients)


def test_service_defers_closing_in_flight_connection_on_proxy_change_and_exit(service_clients):
    started, release = Event(), Event()

    def handler(request):
        if request.url.params["q"] == "first":
            started.set()
            assert release.wait(5), "Test did not release the in-flight request"
        return httpx.Response(200, json=[[["译文"]]])

    service, clients = service_clients(handler)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.translate, ["first"])
        try:
            assert started.wait(5)
            assert service.translate(["second"], proxy="http://127.0.0.1:8080").texts == ["译文"]
            assert not clients[0][1].is_closed
            service.close()
            assert clients[1][1].is_closed
            assert not clients[0][1].is_closed
            with pytest.raises(TranslationError, match="已关闭"):
                service.translate(["third"])
        finally:
            release.set()
            service.close()
        assert pending.result(timeout=5).texts == ["译文"]
    assert all(client.is_closed for _, client in clients)


def test_service_validation_and_empty_input_do_not_create_connections(service_clients):
    service, clients = service_clients(lambda request: pytest.fail("No request expected"))
    try:
        assert service.translate(["", "  "]).texts == ["", "  "]
        with pytest.raises(TranslationError):
            service.translate(["hello"], proxy="invalid-proxy")
        with pytest.raises(TranslationError):
            service.translate(["hello"], provider="official")
        assert not clients
    finally:
        service.close()


@pytest.mark.parametrize("error_type", [ValueError, ImportError, httpx.InvalidURL])
def test_service_failed_proxy_replacement_preserves_old_connection_and_redacts_logs(monkeypatch, caplog, error_type):
    original_client = httpx.Client
    clients = []
    secret = "proxy-password-never-log"

    def create(**kwargs):
        if kwargs["proxy"]:
            raise error_type(f"Proxy rejected {secret}")
        client = original_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[[["你好"]]])))
        clients.append(client)
        return client

    monkeypatch.setattr(google_translate.httpx, "Client", create)
    service = TranslationService()
    try:
        service.translate(["hello"])
        try:
            service.translate(["hello"], proxy=f"http://user:{secret}@127.0.0.1:8080")
        except TranslationError:
            logging.getLogger("test.translation").exception("Client replacement failed")
        else:
            pytest.fail("Invalid proxy initialization must fail")
        assert "Client replacement failed" in caplog.text
        assert secret not in caplog.text
        assert not clients[0].is_closed
        assert service.translate(["hello"]).texts == ["你好"]
        assert len(clients) == 1
    finally:
        service.close()


def test_service_network_failures_are_redacted_and_client_remains_reusable(service_clients, caplog):
    attempts = 0
    secret = "cloud-key-never-log"

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError(f"Bad key {secret}", request=request)
        return httpx.Response(200, json={"data": {"translations": [{"translatedText": "你好"}]}})

    service, clients = service_clients(handler)
    try:
        try:
            service.translate(["hello"], provider="official", api_key=secret)
        except TranslationError:
            logging.getLogger("test.translation").exception("Service request failed")
        assert "Service request failed" in caplog.text
        assert secret not in caplog.text
        assert service.translate(["hello"], provider="official", api_key=secret).texts == ["你好"]
        assert len(clients) == 1
    finally:
        service.close()
