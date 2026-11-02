"""Cooperative cancellation shared by GUI and the private Wordcraft process."""


class ProcessingCancelled(RuntimeError):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise ProcessingCancelled('Обработка отменена. Исходный документ не изменён.')
