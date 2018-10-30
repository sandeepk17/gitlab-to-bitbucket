#!/usr/bin/env python
import json
import os
import re
import subprocess
import shutil
import requests
import yaml
import datetime

configs = yaml.load(open('config.yml', 'r'))

GITLAB_ENDPOINT = configs["GITLAB_ENDPOINT"]
GITLAB_TOKEN = configs["GITLAB_TOKEN"]

BITBUCKET_ENDPOINT = configs["BITBUCKET_ENDPOINT"]
BITBUCKET_TEAM = configs["BITBUCKET_TEAM"]
BITBUCKET_USERNAME = configs["BITBUCKET_USERNAME"]
BITBUCKET_PASSWORD = configs["BITBUCKET_PASSWORD"]

BB_PROJECT_NAME_SUBSTITUTION_REGEX = "[^A-Za-z0-9_]+"

bitbucket = requests.Session()
bitbucket.auth = (BITBUCKET_USERNAME, BITBUCKET_PASSWORD)

def list_gitlab_repositories():
    repositories = []
    page = 1
    while True:
        params = {"page": page, "per_page": 100, "private_token": GITLAB_TOKEN, "order_by": "last_activity_at", "sort": "desc"}
        url = os.path.join(GITLAB_ENDPOINT, "projects", "all")
        res = requests.get(url, params=params)
        if len(res.json()) > 0:
          repositories += res.json()
          page += 1
        else:
          break
    print("Found {} repositories on gitlab".format(len(repositories)))
    return repositories

def list_bitbucket_projects():
    url = os.path.join(BITBUCKET_ENDPOINT, "teams", BITBUCKET_TEAM, "projects/")
    projects = []
    while url:
        res = bitbucket.get(url)
        payload = res.json()
        projects += payload["values"]
        url = payload.get("next", None)
    print("\n\n============Project Keys in Bitbucket:===========\n\n")
    for p in projects:
        print(p.get("key"))
    return projects

def list_bitbucket_repositories():
    url = os.path.join(BITBUCKET_ENDPOINT, "repositories", BITBUCKET_TEAM)
    repositories = []
    while url:
        res = bitbucket.get(url)
        payload = res.json()
        repositories += payload["values"]
        url = payload.get("next", None)
    return repositories

def generate_key(name):
    keyname = re.sub("[^A-Za-z0-9_]+", "", name.upper())
    return keyname

def create_bitbucket_project(name):
    payload = {
        "name": re.sub(BB_PROJECT_NAME_SUBSTITUTION_REGEX, "", name),
        "key": generate_key(name),
        "is_private": True
    }
    url = os.path.join(BITBUCKET_ENDPOINT, "teams", BITBUCKET_TEAM, "projects/")
    print("Payload: {}\nURL: {}".format(payload, url))
    res = bitbucket.post(url, json=payload)
    if not 200 <= res.status_code < 300:
        raise ValueError("could not create project {0}: {1}".format(name, res.text))
    else:
        print("Creating Bitbucket Project: {}".format(name))

def create_bitbucket_repository(name, project):
    payload = {"scm": "git", "is_private": True, "project": {"key": generate_key(project)}}
    url = os.path.join(BITBUCKET_ENDPOINT, "repositories", BITBUCKET_TEAM, name.lower())
    print("Creating bitbucket repository\nPayload: {}\nURL: {}".format(payload, url))
    res = bitbucket.post(url, json=payload)
    if not 200 <= res.status_code < 300:
        if not "Repository with this Slug and Owner already exists." in res.text:
            if not "Project with this Owner and Key already exists." in res.text:
                raise ValueError("could not create repository {0}: {1}".format(name, res.text))
    return res.json()

def clone_repository(repository):
    project_dir = os.path.join("/tmp", repository["namespace"]["path"], repository["path"])
    if os.path.exists(project_dir) and os.listdir(project_dir):
        #return False
        print("Deleting " + project_dir)
        shutil.rmtree(project_dir)
    os.makedirs(project_dir, exist_ok=True)
    subprocess.run(["git", "clone", "--mirror", repository["ssh_url_to_repo"], project_dir])
    return project_dir

def upload_repository(bb_repo, gl_repo, project):
    #TODO: Handle original gitlab repo name and new bitbucket repo name.
    project_dir = os.path.join("/tmp", project, gl_repo)
    remote = "git@bitbucket.org:{0}/{1}.git".format(BITBUCKET_TEAM, bb_repo)
    subprocess.run(["git", "remote", "add", "bitbucket", remote], cwd=project_dir)
    subprocess.run(["git", "push", "--all", "bitbucket"], cwd=project_dir)
    subprocess.run(["git", "push", "--tags", "bitbucket"], cwd=project_dir)

class Migrator:
    def __init__(self):
        self.repositories = list_gitlab_repositories()
        bb_projs = list_bitbucket_projects()
        self.projects = set(project["name"] for project in bb_projs)
        self.bb_repositories = list_bitbucket_repositories()
        self.fout = open("gl_to_bb_migration_report_" + datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S") + ".json", 'w')

    def __del__(self):
        self.fout.close()

    def delete_bb_repos_and_projects(self):
        bb_repos = self.bb_repositories
        for repo in bb_repos:
            url = os.path.join(BITBUCKET_ENDPOINT, "repositories", BITBUCKET_TEAM, repo.get("uuid"))
            print("Trying to delete repo: {}".format(url))
            r = bitbucket.delete(url)
            print(r.status_code)
            print(r.text)
        bb_projs = list_bitbucket_projects()
        for p in bb_projs:
            url = os.path.join(BITBUCKET_ENDPOINT, "teams", BITBUCKET_TEAM, "projects", p.get("key"))
            print("Trying project delete api: {}".format(url))
            r = bitbucket.delete(url)
            print(r.status_code)
            print(r.text)

    def migrate_repositories(self):
        for repository in self.repositories:
            self.migrate_repository(repository)

    def ensure_project_exists(self, project):
        bb_project_name = re.sub(BB_PROJECT_NAME_SUBSTITUTION_REGEX, "", project)
        if bb_project_name not in self.projects:
            create_bitbucket_project(bb_project_name)
            self.projects.add(bb_project_name)

    def matching_repos(self, gl_repository):
        exact_matches = []
        name_matches = []
        for bb_repo in self.bb_repositories:
            if gl_repository.get("path").lower() == bb_repo.get("name").lower():
                name_matches.append(bb_repo)
                if re.sub(BB_PROJECT_NAME_SUBSTITUTION_REGEX, "", gl_repository.get("namespace").get("path")).lower() == bb_repo.get("project").get("key").lower():
                    exact_matches.append(bb_repo)
        print("\n------Matches Found:-------\n")
        print("Exact Matches: {}".format(exact_matches))
        print("Name Matches: {}".format(name_matches))
        return {"exact_matches": exact_matches, "name_matches": name_matches}

    def migrate_repository(self, repository):
        output = {"gl_full_path": repository.get("path_with_namespace"), "gl_web": repository.get("web_url"), "gl_ssh": repository.get("ssh_url_to_repo"), "gl_http": repository.get("http_url_to_repo")}
        project = repository["namespace"]["path"]
        self.ensure_project_exists(project)
        repos_on_bb = self.matching_repos(repository)
        exact_matches = repos_on_bb.get("exact_matches")
        name_matches = repos_on_bb.get("name_matches")
        final_bb_repo = None
        if len(exact_matches) > 0:
            print("Repo is already present: {}".format(repository))
            final_bb_repo = exact_matches[0]
        else:
            if len(name_matches) == 0:
                new_repo_name = repository["path"]
                print("Repo not present. Creating: {}".format(repository))
            elif len(name_matches) > 0:
                new_repo_name = repository["path"] + "_" + project + "_" + re.sub(BB_PROJECT_NAME_SUBSTITUTION_REGEX, "", repository.get("owner", {}).get("username", ""))
                print("Repo name is present, but in a different project. Need to create a new one with a different name")
            project_dir = clone_repository(repository)
            if not project_dir:
                return
            final_bb_repo = create_bitbucket_repository(new_repo_name, project)
            final_bb_repo.update({"project": {"key": generate_key(project), "name": re.sub(BB_PROJECT_NAME_SUBSTITUTION_REGEX, "", project)}})
            self.bb_repositories.append(final_bb_repo)
            upload_repository(new_repo_name, repository["path"], project)
        print("\n\n==========Final BB Repo=========\n" + str(final_bb_repo))
        bb_repo_details = {"bb_full_path": final_bb_repo.get("full_name"),
                "uuid": final_bb_repo.get("uuid"), 
                "bb_web": final_bb_repo.get("links").get("html").get("href"), 
                "bb_ssh": final_bb_repo.get("links").get("clone")[1].get("href"), 
                "bb_https": final_bb_repo.get("links").get("clone")[0].get("href")}
        print("\n========================\n\n")
        output.update(bb_repo_details)
        self.fout.write(json.dumps(output) + "\n")

def main():
    migrator = Migrator()
    del_bb_repos_and_projects = input("Do you want to delete all repos and projects in BB? (y/n): ")
    if del_bb_repos_and_projects == "y":
        migrator.delete_bb_repos_and_projects()
        print("Deletion Done. Please run the script again for starting the migration. Exiting...")
        return()
    migrator.migrate_repositories()
    del migrator

if __name__ == '__main__':
    main()

