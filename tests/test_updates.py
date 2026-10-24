import httpx
import pytest

from screen_translate.updates import check_for_updates, RELEASES_URL


def test_update_check_finds_new_preview_and_keeps_link_on_our_repository():
    payload = [{'tag_name': 'v0.1.0'}, {'tag_name': 'v0.2.0', 'prerelease': True,
        'html_url': 'https://untrusted.example/'}, {'tag_name': 'invalid'},
        {'tag_name': 'v99.0.0', 'draft': True}]
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        info = check_for_updates('0.1.0', client=client)
    assert info.latest == 'v0.2.0' and info.preview
    assert info.url == RELEASES_URL+'/tag/v0.2.0'


def test_update_check_is_not_an_automatic_download():
    seen = []
    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json=[{'tag_name': 'v0.2.0'}])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check_for_updates('0.2.0', client=client).latest is None
    assert seen == ['api.github.com']


@pytest.mark.parametrize('status,payload', [(403, {}), (200, {})])
def test_update_error_is_actionable_without_echoing_response_secrets(status, payload):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload))) as client:
        with pytest.raises(RuntimeError, match='GitHub 发布页'):
            check_for_updates('0.1.0', client=client)
