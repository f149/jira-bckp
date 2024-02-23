### Atlassian backup script
--init : create backup file on site backupe manager ~ 40min
--download : download backup to local folder specified in script setup 
--upload : upload local backup files to AWS S3
--delete-local : if backup file present in AWS 3 - delete local file 
--delete-s3 : takes a list of all files, sort by date leaves 4 (by default) and deletes all the oldest backups. 
--get-link : get a backup file link for manual downloading
