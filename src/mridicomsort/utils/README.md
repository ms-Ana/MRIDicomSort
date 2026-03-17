#Data organization

For raw DICOM exports, run these steps:

1. dicom_organize.py: move files to a target directory and organize them by PatientID and StudyDate.
2. compare_folders.py: compare two folders by file checksums; report mismatches.
3. merge_folders.py: merge one folder into another, preserving directory structure (to merge multiple experts)
