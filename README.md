# Migrate Gitlab Repositories and Projects to Bitbucket

*Code for migrating all repositories and projects in Gitlab to Bitbucket*

### Instructions

1. Make sure you have Python 3.x installed

2. Install the required libraries by running the command ```$ pip install -r requirements.txt```

3. Copy config.yml.example to config.yml and edit the file to include details of API Keys, endpoints and credentials of your gitlab and bitbucket accounts

4. Run the script. Eg: ```python3.6 gitlab-to-bitbucket.py```

### Notes

1. The API versions supported and tested are:
    * Gitlab API: v3
    * Bitbucket API: v2

2. Due to naming restrictions in Bitbucket, some project and repository names might be slightly changed.

3. You can check the report containing the mappings of Gitlab and Bitbucket repositories in the output file generated as ``gl_to_bb_migration_report_<timestamp>.json``

### References

Thanks to https://github.com/giordy and https://github.com/danhper for the original code contributed here:

https://gist.github.com/danhper/f49da483a5b59dec9484b42ad5d25caa

https://gist.github.com/giordy/4b3c6eb34b09967ee73739b33a8e9eab
