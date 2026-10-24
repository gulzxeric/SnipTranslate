"""Read public GitHub release metadata; downloads remain an explicit browser action."""
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from packaging.version import InvalidVersion, Version


RELEASES_URL = 'https://github.com/gulzxeric/SnipTranslate/releases'
API_URL = 'https://api.github.com/repos/gulzxeric/SnipTranslate/releases'


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str | None = None
    url: str = RELEASES_URL
    preview: bool = False


def check_for_updates(current, *, client=None):
    owned = client is None
    http = client
    try:
        if http is None:
            http = httpx.Client(timeout=10, follow_redirects=False,
                headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'SnipTranslate'})
        response = http.get(API_URL, params={'per_page': 30})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError('Invalid release list')
        candidates = []
        for item in payload:
            if not isinstance(item, dict) or item.get('draft'):
                continue
            tag = item.get('tag_name')
            if not isinstance(tag, str):
                continue
            try:
                version = Version(tag.removeprefix('v'))
            except InvalidVersion:
                continue
            if version > Version(current):
                candidates.append((version, tag, bool(item.get('prerelease'))))
        if not candidates:
            return UpdateInfo(current)
        _, tag, preview = max(candidates, key=lambda item: item[0])
        return UpdateInfo(current, tag, RELEASES_URL+'/tag/'+quote(tag, safe=''), preview)
    except (httpx.HTTPError, ValueError, ImportError):
        raise RuntimeError('暂时无法检查更新。请稍后重试，或直接查看 GitHub 发布页。') from None
    finally:
        if owned and http is not None:
            http.close()
