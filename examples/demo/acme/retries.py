import time


def retry_demo(action):
    for attempt in range(3):
        try:
            return action()
        except ValueError:
            pass
        time.sleep(0.001)
    return None
