import json
import logging

import httpx
import pytest

from screen_translate.google_translate import TranslationError, translate


def test_public_preserves_block_order_empty_positions_and_sentence_segments():
    seen = []

    def handler(request):
        assert request.url.host == "translate.googleapis.com"
        assert request.url.params["client"] == "gtx"
        assert request.url.params["sl"] == "auto"
        text = request.url.params["q"]
        seen.append(text)
        return httpx.Response(200, json=[[[f"译文:{text}", text], ["。", "!"]], None, "en"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = translate(["second", "", "first", "  ", "second"], client=client)
    assert result.texts == ["译文:second。", "", "译文:first。", "  ", "译文:second。"]
    assert result.detected_language == "en"
    assert sorted(seen) == ["first", "second", "second"]


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
