import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileHandler(FileSystemEventHandler):
    def __init__(self, queue, tracker):
        self.queue = queue
        self.tracker = tracker

    def on_created(self, event):
        print(event)
        if event.is_directory:
            return
        self.queue.put(event.src_path)

class Watcher:
    def __init__(self, folder, queue, tracker):
        self.folder = folder
        self.queue = queue
        self.tracker = tracker
        self.observer = Observer()
        self.observer.schedule(FileHandler(self.queue, self.tracker), self.folder, recursive=False)

    def start(self):
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()

class Processor:
    def __init__(self, queue, tracker):
        self.queue = queue
        self.tracker = tracker

    def process_file(self, file_path):
        try:
            # do processing here
            print(f"Processing file: {file_path}")
            self.tracker.update_status(file_path, "done")
        except Exception as e:
            print(f"Error processing file: {file_path} - {e}")
            self.tracker.update_status(file_path, "failed")

    def run(self):
        while True:
            file_path = self.queue.get()
            self.tracker.update_status(file_path, "in progress")
            self.process_file(file_path)

class Tracker:
    def __init__(self, db):
        self.db = db

    def update_status(self, file_path, status):
        retries = self.get_retries(file_path)
        run_count = self.get_run_count(file_path)
        if status == "in progress":
            run_count += 1
        elif status == "failed":
            retries += 1
            run_count += 1
        self.db.execute("UPDATE files SET status = ?, retries = ?, run_count = ? WHERE file_path = ?", (status, retries, run_count, file_path))
        self.db.commit()

    def get_retries(self, file_path):
        result = self.db.execute("SELECT retries FROM files WHERE file_path = ?", (file_path,))
        row = result.fetchone()
        if row is None:
            return 0
        else:
            return row[0]

    def get_run_count(self, file_path):
        result = self.db.execute("SELECT run_count FROM files WHERE file_path = ?", (file_path,))
        row = result.fetchone()
        if row is None:
            return 0
        else:
            return row[0]

if __name__ == "__main__":
    import sqlite3
    db = sqlite3.connect("file_tracker.db")
    db.execute("CREATE TABLE IF NOT EXISTS files (file_path TEXT PRIMARY KEY, status TEXT, retries INTEGER, run_count INTEGER)")
    db.commit()

    from queue import Queue
    queue = Queue()

    tracker = Tracker(db)
    watcher = Watcher("/content/watching", queue, tracker)
    watcher.start()

    processor = Processor(queue, tracker)
    processor.run()

    watcher.stop()
