import os
import time
import threading
from collections import deque
from typing import List

class File:
    def __init__(self, path):
        self.path = path

class Observable:
    def __init__(self):
        self.observers = set()

    def register(self, observer):
        self.observers.add(observer)

    def unregister(self, observer):
        self.observers.discard(observer)

    def notify(self, *args, **kwargs):
        for observer in self.observers:
            observer.onEvent(*args, **kwargs)

class Watcher(Observable):
    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.queue = deque()
        self._lock = threading.Lock()
        self.stopped = False

    def start(self):
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    def stop(self):
        self.stopped = True
        self.thread.join()

    def _run(self):
        while not self.stopped:
            for filename in os.listdir(self.folder):
                filepath = os.path.join(self.folder, filename)
                if os.path.isfile(filepath):
                    file = File(filepath)
                    with self._lock:
                        self.queue.append(file)
                        self.notify("file_created", file)

            time.sleep(1)

class Processor:
    def __init__(self):
        pass

    def process(self, file: File):
        # TODO: Add file processing logic here
        print(f"Processing {file.path}")
        time.sleep(2)

class Tracker:
    def __init__(self):
        pass

    def update_tracking(self, files: List[File], status: str, retries: int, run_count: int):
        # TODO: Add tracking logic here
        print(f"Updating tracking for {len(files)} files with status '{status}'")

class Pipeline:
    def __init__(self, watcher, processor, tracker):
        self.watcher = watcher
        self.processor = processor
        self.tracker = tracker

    def onEvent(self, event, file):
        if event == "file_created":
            with self.watcher._lock:
                self.watcher.queue.append(file)
                self.tracker.update_tracking([file], "todo", 0, 0)
        elif event == "file_processed":
            self.tracker.update_tracking([file], "done", 0, 1)

    def start(self):
        self.watcher.register(self)
        self.watcher.start()

        while True:
            if len(self.watcher.queue) > 0:
               file = self.watcher.queue.popleft()
            else:
               continue

            self.processor.process(file)
            self.notify("file_processed", file)

    def notify(self, event, file):
        self.onEvent(event, file)

if __name__ == "__main__":
    watcher = Watcher("/content/watching")
    processor = Processor()
    tracker = Tracker()
    pipeline = Pipeline(watcher, processor, tracker)

    pipeline.start()
