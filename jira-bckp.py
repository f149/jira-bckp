# BCKP CLOUD JIRA & CONFLUENCE SCRIPT
# MBASM v.2.1 22/01/24 07:25:22

# ------------- CHANGE LOG -------------
# + Init site bckp

import requests
import sys
import re
import time
import boto3
from botocore.exceptions import NoCredentialsError
import os
from tqdm import tqdm




def start_session(email, token):
    session = requests.Session()
    session.auth = (email, token)
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    
    return session


def init_backup(url, session):
    json  = b'{"cbAttachments": "true", "exportToCloud": "true"}'
    
    confluence_start = session.post(url + '/wiki/rest/obm/1.0/runbackup', data=json)
    jira_start = session.post(url + '/rest/backup/1/export/runbackup', data=json)
    print(" --- CONF_START --- \n", confluence_start.text)
    print(" --- JIRA_START --- \n", jira_start.text)


def get_backup_file_name(url, session):
    try:
        confluence_backup_info = session.get( url + '/wiki/rest/obm/1.0/getprogress')
        confluence_backup_file = str(re.search('(?<=fileName\":\")(.*?)(?=\")', confluence_backup_info.text).group(1))

        jira_last_task_id = session.get(url + '/rest/backup/1/export/lastTaskId').text
        jira_backup_info  = session.get(url + '/rest/backup/1/export/getProgress?taskId=' + jira_last_task_id)
        jira_backup_file  = re.search('(?<=result":")(.*?)(?=\",)', jira_backup_info.text).group(1)

        print(url + confluence_backup_file)
        print(url + jira_backup_file)

        return confluence_backup_file, jira_backup_file

    except AttributeError:
        print('----------- ERROR -----------')
        print(confluence_backup_info.text)
        exit(1)


def download_backup(url, session, local_backup_folder):

    backup_files = get_backup_file_name(url, session)
    confluence_path, jira_path = backup_files
    backup_timestamp = time.strftime("%Y%m%d_%H%M%S")
    date = time.strftime("%Y%m%d")
    local_files = os.listdir(local_backup_folder)

    for file_path in backup_files:
        if file_path.startswith("temp/"):
            file_link = url + '/wiki/download/' + confluence_path
            service   = 'confluence_backup-'
            file_name = service + backup_timestamp + '.zip'

        elif file_path.startswith("export/download/"):
            file_link = url + '/plugins/servlet/' + jira_path
            service   = 'jira_backup-'
            file_name = service + backup_timestamp + '.zip'

        backup_file = session.get(file_link, stream=True)
        backup_file.raise_for_status()

        for file in local_files:
            if any(file.startswith(service + date) for file in local_files):
                print(' --- TODAYS BACKUP IS ALREADY DOWNLOADED ---')
                print('LOCAL FILES: ', local_files )
                print('BACKUP FILE:', file_name)
                break
            else:

                #          -------- WITHOUT PROGRESSBAR IN TERMINAL --------
                #
                #                print("DOWNLOAD: ", file_name)
                #                with open(local_backup_folder + file_name, 'wb') as handle:
                #                    for block in backup_file.iter_content(chunk_size=1024):
                #                        handle.write(block)
                #            print("DOWNLOADED:", file_name)
                #    print(" --- ALL BACKUP FILES DOWNLOADED TO LOCAL FOLDER ---", backup_timestamp)
                #
                #           -------------------------------------------------

                with open(local_backup_folder + file_name, 'wb') as handle, tqdm(
                    desc=f"Downloading {file_name}",
                    total=int(backup_file.headers.get('content-length', 0)),
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as pbar:
                    for block in backup_file.iter_content(chunk_size=1024):
                        handle.write(block)
                        pbar.update(len(block))
            print("DOWNLOADED:", file_name)
    print(" --- ALL BACKUP FILES DOWNLOADED TO LOCAL FOLDER ---", backup_timestamp)



def upload_backup_to_s3(bucket_name, access_key, secret_key, local_backup_folder):

    local_files = os.listdir(local_backup_folder)
    s3_folder   = 'atlassian_backups'
    
    if len(local_files) < 1:
        print(" --- NO FILES FOUND --- ")

    try:
        for local_file_name in local_files:
            s3 = boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
            local_file_path = os.path.join(local_backup_folder, local_file_name)
            file_size = os.path.getsize(local_file_path)
            s3_object_key = os.path.join(s3_folder, local_file_name)

            with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"UPLOADING: {local_file_name}") as pbar:
                s3.upload_file(local_file_path, bucket_name, s3_object_key, Callback=lambda bytes_uploaded: pbar.update(bytes_uploaded))
            print(f" --- UPLOAD FINISHED ---\n {bucket_name}/{local_file_name}")


    except NoCredentialsError:
        print(" --- AWS USER CREDENTIALS NOT FOUND --- ")
        return None


def delete_old_backup_s3(bucket_name, access_key, secret_key, max_files=4):

    try:
        s3 = boto3.client('s3', aws_access_key_id=access_key, aws_secret_access_key=secret_key)
        objects = s3.list_objects_v2(Bucket=bucket_name)['Contents']
        print(" --- S3 FILES LIST --- \n ", objects)

        sorted_objects = sorted(objects, key=lambda x: x['LastModified'])

        files_to_delete = sorted_objects[:-max_files]
        print(" --- DELETED FILE LIST --- \n")
        for obj in files_to_delete:
            print(obj)
            if obj['Key'] == 'atlassian_backups/.DS_Store':
                s3.delete_object(Bucket=bucket_name, Key=['Key'])
            else:
                s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                print(f" --- FILE DELETED ---\n {obj['Key']} ")

    except NoCredentialsError:
        print('--- ERROR ---')
        exit(1)



def delete_local_backup(bucket_name, aws_access_key, aws_secret_key, local_backup_folder):

    local_files = os.listdir(local_backup_folder)
    #print(" --- LOCAL FILES ---\n", local_files)

    try:
        s3 = boto3.client('s3', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
        response = s3.list_objects_v2(Bucket=bucket_name)

        if 'Contents' in response:
            s3_file_list = [obj['Key'] for obj in response['Contents']]
            for s3_file_name in s3_file_list:
                s3_file_name = s3_file_name.split('/')[-1]
                local_files = os.listdir(local_backup_folder)

                if s3_file_name in local_files:
                    local_file_path = os.path.join(local_backup_folder, s3_file_name)
                    os.remove(local_file_path)
                    print(f" --- LOCAL FILE DELETED ---\n {local_file_path}")
                else:
                    print(f" --- NO LOCAL MATCHES FOUND ---\n {s3_file_name} ")

    except Exception as e:
        print(f"An error occurred: {e}")


def main():
# ------------ ATLASSIAN INFO ------------
    url     = 
    email   = 
    token   = 
    session = start_session(email, token)

# ------------- AWS S3 INFO  -------------
    aws_bucket_name = 
    aws_access_key  = 
    aws_secret_key  = 

# ------------- SERVICE INFO -------------
    #local_backup_folder = '/opt/jira-backup/backup_files'
    local_backup_folder = 'backup_files2/'

# ----------- SCRIPT ARGUMENTS -----------
    if len(sys.argv) < 2:
        print("Use with: --init, --download, --upload, --delete-local, --delete-s3, --get-link ")
        sys.exit(1)

    method = sys.argv[1]

    if method == '--init':
        init_backup(url, session)
    
    elif method == '--download':
        download_backup(url, session, local_backup_folder)

    elif method == '--upload':
        upload_backup_to_s3(aws_bucket_name, aws_access_key, aws_secret_key, local_backup_folder)

    elif method == '--delete-local':
        delete_local_backup(aws_bucket_name, aws_access_key, aws_secret_key, local_backup_folder)

    elif method == '--delete-s3':
        delete_old_backup_s3(aws_bucket_name, aws_access_key, aws_secret_key)

    elif method == '--get-link':
        get_backup_file_name(url, session)
 
    else:
        print("Method not found, use --help")

if __name__ == '__main__':
    main()
