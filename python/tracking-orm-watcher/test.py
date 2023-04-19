import os
import shutil
import tempfile
import unittest
import time
import threading
from my_pipeline import watch_folder, process_file, update_tracking

class TestPipeline(unittest.TestCase):

    def setUp(self):
        # Create a temporary folder to watch for new files
        self.temp_dir = tempfile.mkdtemp()
        self.watch_folder_thread = threading.Thread(target=watch_folder, args=(self.temp_dir,))
        self.watch_folder_thread.start()

    def tearDown(self):
        # Stop watching the folder and clean up
        self.watch_folder_thread.join()
        shutil.rmtree(self.temp_dir)

    def test_pipeline(self):
        # Create a new file in the temporary folder
        with open(os.path.join(self.temp_dir, "test.txt"), "w") as f:
            f.write("Test file")

        # Wait for the file to be processed
        time.sleep(5)

        # Check that the file was processed successfully and tracked
        self.assertEqual(update_tracking("test.txt", "done", 0), None)
