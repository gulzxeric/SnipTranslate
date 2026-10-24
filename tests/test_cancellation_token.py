from screen_translate.cancellation import CancellationToken, check_cancelled, CancelledError
import pytest


def test_native_cancel_callbacks_run_once_and_can_be_unregistered():
    token = CancellationToken()
    calls = []
    token.register(lambda: calls.append('native inference'))
    unregister = token.register(lambda: calls.append('completed stage'))
    unregister()
    token.set()
    token.set()
    assert calls == ['native inference']
    with pytest.raises(CancelledError):
        check_cancelled(token)


def test_registering_after_cancellation_terminates_immediately():
    token = CancellationToken()
    token.set()
    calls = []
    token.register(lambda: calls.append('terminated'))
    assert calls == ['terminated']
