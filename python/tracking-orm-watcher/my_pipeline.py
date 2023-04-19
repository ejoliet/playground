import os
import time
import queue
import threading
#from db import SQLiteTracking
# using ORM and dm:
from orm2db import SQLiteTracking, PipelineTracking

# Initialize the task queue
task_queue = queue.Queue()
tracking = SQLiteTracking('/content/database.db')

# Define the function to process a file
def process_file(filename):
    # Do some processing on the file
    print("File " + filename + " processed - 10 seconds")
    time.sleep(10)
    pass

# Define the function to update tracking information
def update_tracking(filename, status, retries):
    # Update the tracking information for the file
    print("DB updated on "+filename+" with status "+status+"\n")
    tracking.update_tracking(filename, status, retries)
    pass

# Define the function to watch for new files in a folder
def watch_folder(folder_path):
    # Get the list of files in the folder
    files = os.listdir(folder_path)
# is there "todo" files not done? Yes, add them to the queue to process them
    todo_files = tracking.session.query(PipelineTracking).filter_by(status="todo").all()
    for file in todo_files:
      task_queue.put(file)
      print("File " + file + " found not done")
    # Watch for new files in the folder
    while True:
        # Check for new files
        new_files = [f for f in os.listdir(folder_path) if f not in files]
        if new_files:
            # Add each new file to the task queue
            for file in new_files:
                task_queue.put(file)
                update_tracking(file, "todo", 0)

            # Update the list of files to include the new files
            files += new_files

        # Wait for a short period before checking again
        time.sleep(1)

# Define the function to process files from the task queue
def process_files():
    while True:
        # Get the next file from the task queue
        file = task_queue.get()

        # Attempt to process the file
        retries = 0
        while retries < 3:
            try:
                process_file(file)
                update_tracking(file, "done", retries)
                break
            except Exception as e:
                retries += 1
                update_tracking(file, "failed", retries, str(e))
                with open("error.log", "a") as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: Error processing {filename}: {str(e)}\n")


        # Mark the task as complete in the queue
        task_queue.task_done()

# Start processing files from the task queue in a separate thread
processing_thread = threading.Thread(target=process_files)
processing_thread.start()

# Start watching the folder for new files in a separate thread
folder_thread = threading.Thread(target=watch_folder, args=("/content/watching",))
folder_thread.start()

folder_thread.join()
processing_thread.join()
