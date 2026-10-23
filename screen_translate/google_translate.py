"""Google Translation clients with an explicit public/Cloud provider choice.

Only recognized text is sent to Google. Images never leave the OCR module.
The public endpoint is not an official supported Cloud API and can reject
requests; failures are surfaced to the user instead of returning source text.
"""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from html import unescape
from typing import Any
from urllib.parse import urlsplit

import httpx

from .models import TranslationResult


PUBLIC_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
CLOUD_ENDPOINT = "https://translation.googleapis.com/language/translate/v2"
MAX_BLOCKS = 128
MAX_CHARACTERS = 20000
MAX_BLOCK_CHARACTERS = 4000
PUBLIC_BATCH_CHARACTERS = 3000


class TranslationError(RuntimeError):
    """A translation failed; the message can be shown directly in the UI."""


def _check_response(response: httpx.Response, provider: str) -> Any:
    status = response.status_code
    if status == 429:
        raise TranslationError("谷歌翻译请求过于频繁或配额已用完（429），请稍后重试。")
    if status in (401, 403):
        if provider == "official":
            raise TranslationError("谷歌 Cloud 翻译拒绝了请求，请检查 API Key、API 启用状态和计费设置。")
        raise TranslationError("谷歌公共翻译接口拒绝访问，请检查网络或在设置中切换到 Cloud API。")
    if 500 <= status:
        raise TranslationError(f"谷歌翻译服务暂时不可用（{status}），请稍后重试。")
    if not 200 <= status < 300:
        raise TranslationError(f"谷歌翻译请求失败（{status}），请检查语言和接口设置。")
    try:
        return response.json()
    except (ValueError, UnicodeDecodeError):
        raise TranslationError("谷歌翻译返回了无效数据，网络可能拦截了请求。") from None


def _parse_public(payload: Any) -> tuple[str, str]:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise TranslationError("谷歌公共翻译响应格式异常，请重试或使用 Cloud API。")
    pieces: list[str] = []
    for segment in payload[0]:
        if not isinstance(segment, list) or not segment or not isinstance(segment[0], str):
            raise TranslationError("谷歌公共翻译响应不完整，请重试。")
        pieces.append(segment[0])
    translated = "".join(pieces)
    if not translated.strip():
        raise TranslationError("谷歌翻译没有返回译文，请重试。")
    detected = payload[2] if len(payload) > 2 and isinstance(payload[2], str) else ""
    return translated, detected


def _public_one(client: httpx.Client, text: str, target: str, source: str) -> tuple[str, str]:
    response = client.get(
        PUBLIC_ENDPOINT,
        params={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
    )
    return _parse_public(_check_response(response, "public"))


def _public_groups(texts):
    """Bound query size and keep multiline callers on the exact single path."""
    group = []
    length = 0
    for index, text in enumerate(texts):
        multiline = '\n' in text or '\r' in text
        if group and (multiline or length + len(text) + 1 > PUBLIC_BATCH_CHARACTERS):
            yield group
            group, length = [], 0
        if multiline or len(text) >= PUBLIC_BATCH_CHARACTERS:
            yield [(index, text)]
        else:
            group.append((index, text))
            length += len(text) + 1
    if group:
        yield group


def _public_group(client, group, target, source):
    if len(group) == 1:
        return [_public_one(client, group[0][1], target, source)]
    translated, language = _public_one(client, '\n'.join(text for _, text in group), target, source)
    lines = translated.replace('\r\n', '\n').split('\n')
    if len(lines) == len(group) and all(line.strip() for line in lines):
        return [(line, language) for line in lines]
    # Google may collapse line breaks. Discard the ambiguous batch and obtain
    # separate results rather than placing text over the wrong image region.
    return [_public_one(client, text, target, source) for _, text in group]


def _official(
    client: httpx.Client, texts: list[str], target: str, source: str, api_key: str
) -> TranslationResult:
    body: dict[str, Any] = {"q": texts, "target": target, "format": "text"}
    if source != "auto":
        body["source"] = source
    response = client.post(
        CLOUD_ENDPOINT,
        headers={"X-Goog-Api-Key": api_key},
        json=body,
    )
    payload = _check_response(response, "official")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise TranslationError("谷歌 Cloud 翻译响应格式异常，请重试。")
    items = payload["data"].get("translations")
    if not isinstance(items, list) or len(items) != len(texts):
        raise TranslationError("谷歌 Cloud 翻译返回的行数不完整，请重试。")
    translated: list[str] = []
    languages: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("translatedText"), str):
            raise TranslationError("谷歌 Cloud 翻译响应中缺少译文，请重试。")
        value = unescape(item["translatedText"])
        if not value.strip():
            raise TranslationError("谷歌 Cloud 翻译返回了空译文，请重试。")
        translated.append(value)
        language = item.get("detectedSourceLanguage", "")
        if isinstance(language, str) and language:
            languages.append(language)
    return TranslationResult(translated, Counter(languages).most_common(1)[0][0] if languages else "")


def _validate(texts: list[str], target: str, source: str, provider: str, proxy: str) -> None:
    if provider not in ("public", "official"):
        raise TranslationError("未知的翻译接口，请在设置中选择公共接口或 Cloud API。")
    if not isinstance(texts, list) or any(not isinstance(item, str) for item in texts):
        raise TranslationError("待翻译内容必须是文本列表。")
    if len(texts) > MAX_BLOCKS or sum(map(len, texts)) > MAX_CHARACTERS:
        raise TranslationError(f"本次截图文字过多，请缩小截图范围（最多 {MAX_BLOCKS} 行、{MAX_CHARACTERS} 字符）。")
    if any(len(item) > MAX_BLOCK_CHARACTERS for item in texts):
        raise TranslationError(f"单行文字超过 {MAX_BLOCK_CHARACTERS} 字符，请缩小截图范围。")
    if not isinstance(target, str) or not target.strip() or target == "auto":
        raise TranslationError("请选择有效的目标语言。")
    if not isinstance(source, str) or not source.strip():
        raise TranslationError("请选择有效的原文语言。")
    if proxy:
        try:
            parsed = urlsplit(proxy)
            valid = parsed.scheme in ("http", "https", "socks5", "socks5h") and parsed.hostname and parsed.port
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            raise TranslationError("代理地址无效，请使用 http://127.0.0.1:端口 等完整地址。")


def translate(
    texts: list[str],
    target: str = "zh-CN",
    source: str = "auto",
    api_key: str = "",
    proxy: str = "",
    provider: str = "public",
    *,
    client: httpx.Client | None = None,
) -> TranslationResult:
    """Translate OCR lines, preserving their exact order and empty positions.

    ``client`` is an optional caller-owned HTTP client used by focused tests.
    Network requests use verified TLS and bounded timeouts by default.
    """
    _validate(texts, target, source, provider, proxy)
    if provider == "official" and not api_key.strip():
        raise TranslationError("使用谷歌 Cloud 翻译需要 API Key，请先在设置中填写。")
    indices = [index for index, item in enumerate(texts) if item.strip()]
    if not indices:
        return TranslationResult(list(texts))
    active = [texts[index] for index in indices]
    try:
        context = nullcontext(client) if client is not None else httpx.Client(
            proxy=proxy or None,
            timeout=httpx.Timeout(20.0, connect=8.0, pool=8.0),
            limits=httpx.Limits(max_connections=3, max_keepalive_connections=3),
            headers={"User-Agent": "ScreenshotTranslate/1.0", "Accept": "application/json"},
            verify=True,
            follow_redirects=False,
        )
        with context as http:
            if provider == "official":
                result = _official(http, active, target, source, api_key.strip())
            else:
                groups = list(_public_groups(active))
                pool = ThreadPoolExecutor(max_workers=min(3, len(groups)), thread_name_prefix="google")
                futures = {}
                pairs = [("", "")] * len(active)
                try:
                    futures = {
                        pool.submit(_public_group, http, group, target, source): group
                        for group in groups
                    }
                    for future in as_completed(futures):
                        for (index, _), pair in zip(futures[future], future.result(), strict=True):
                            pairs[index] = pair
                finally:
                    # On any failure discard queued work immediately. Only the
                    # at most three in-flight requests keep their finite timeout.
                    for future in futures:
                        future.cancel()
                    pool.shutdown(wait=True, cancel_futures=True)
                languages = [language for _, language in pairs if language]
                result = TranslationResult(
                    [item for item, _ in pairs],
                    Counter(languages).most_common(1)[0][0] if languages else "",
                )
    except httpx.TimeoutException:
        raise TranslationError("连接谷歌翻译超时，请检查网络或代理设置后重试。") from None
    except httpx.ProxyError:
        raise TranslationError("无法连接代理服务器，请检查代理地址和端口。") from None
    except httpx.HTTPError:
        raise TranslationError("无法连接谷歌翻译，请检查网络、代理和系统证书设置。") from None
    except (ValueError, ImportError):
        raise TranslationError("网络或代理配置无效，请检查设置；SOCKS 代理需要 httpx[socks]。") from None
    output = list(texts)
    for index, value in zip(indices, result.texts, strict=True):
        output[index] = value
    return TranslationResult(output, result.detected_language)
