import os
import boto3
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash_operator import BashOperator
from airflow.providers.celery.operators.celery import CeleryOperator
from models import FileMetadata

default_args = {
    'owner': 'myuser',
    'start_date': datetime(2023, 4, 14),
    'provide_context': True,
    'depends_on_past': False,
    'retries': 0
}

dag = DAG(
    dag_id='mydag',
    default_args=default_args,
    schedule_interval=timedelta(minutes=5),
    catchup=False
)

def process_file(ds, **kwargs):
    filename = kwargs['filename']
    # process the file here
    metadata = FileMetadata(filename=filename, created_at=datetime.now())
    metadata.save()

def queue_tasks(ds, **kwargs):
    # queue tasks using Celery or AWS Batch Job here
    pass

def watch_folder(ds, **kwargs):
    folder = '/path/to/folder'
    for filename in os.listdir(folder):
        if filename.endswith('.txt'):
            print('Processing file:', filename)
            ti = kwargs['ti']
            ti.xcom_push(key='filename', value=filename)

watch_folder_task = PythonOperator(
    task_id='watch_folder',
    provide_context=True,
    python_callable=watch_folder,
    dag=dag
)

process_file_task = PythonOperator(
    task_id='process_file',
    provide_context=True,
