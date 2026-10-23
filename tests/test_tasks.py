from shiboken6 import delete
from screen_translate.companion import Task


def test_background_warmup_can_finish_after_window_teardown():
    called = []
    task = Task(lambda: called.append(True))
    delete(task.signals)
    task.run()
    assert called == [True]


def test_background_failure_can_finish_after_window_teardown():
    def fail():
        raise ValueError('test failure')
    task = Task(fail)
    delete(task.signals)
    task.run()
