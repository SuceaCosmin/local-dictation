from local_dictation.dispatch import EventDispatcher


def test_events_delivered_in_order_on_other_thread():
    import threading
    seen, threads = [], set()
    d = EventDispatcher()
    d.set_handler(lambda b, k: (seen.append((b, k)), threads.add(threading.current_thread())))
    d.start()
    for i in range(50):
        d.submit("record", "pressed" if i % 2 == 0 else "released")
    d.stop()
    assert seen == [("record", "pressed" if i % 2 == 0 else "released") for i in range(50)]
    assert threading.current_thread() not in threads


def test_handler_exception_does_not_kill_dispatcher():
    seen = []

    def handler(binding, kind):
        if kind == "boom":
            raise RuntimeError("x")
        seen.append(kind)

    d = EventDispatcher()
    d.set_handler(handler)
    d.start()
    d.submit("record", "boom")
    d.submit("record", "ok")
    d.stop()
    assert seen == ["ok"]


def test_submit_without_handler_is_harmless():
    d = EventDispatcher()
    d.start()
    d.submit("record", "pressed")
    d.stop()
