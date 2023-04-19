# Summary

pseudo code design a pipeline for watching a folder and processing newly created files while monitor the folder for new files, and then queueing them. Might be using Celery in the future.

We used ORM to define a table for tracking the files, and updating their status in the sqlite database.

The following steps were suggested:

Define a function to process the file, and use Celery to queue up the task for processing.
Define a model class using ORM, and create a database table to track the files.
Initialize the table if it doesn't exist.
Use the ORM to update the status of the file in the database.

## Future

Modify the script to use Celery to queue up tasks for processing, and monitor the folder for new files with status "todo".
Implement error handling and logging to track any issues with processing the files.

Overall, the proposed solution would provide an efficient and scalable way to process large numbers of files, while also tracking their status and retries.

We didn't consider what would happen if the folder gets new file while the system is down.
There should be a task to read from a particular data persisted with the latest files in the folder and compare at the beginning.
