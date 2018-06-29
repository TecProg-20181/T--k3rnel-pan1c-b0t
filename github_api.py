import json
import requests

GITHUB_TOKEN_FILE = "github.txt"
GITHUB_OWNER = "TecProg-20181"
GITHUB_REPO = "T--k3rnel-pan1c-b0t"


class GithubIssuesApi():
    def __init__(self):
        self.token = self._read_github_token(GITHUB_TOKEN_FILE)
        self.url = 'https://api.github.com/repos/{}/{}/issues'.format(
            GITHUB_OWNER, GITHUB_REPO)
        self.headers = {
            'Authorization': 'token {}'.format(self.token),
            'Content-Type': 'application/json'
        }

    def _read_github_token(self, file):
        try:
            file = open(file, 'r')
            return file.readline()
        except Exception as ex:
            print('Could not open file!\n' + ex)

    def get_issues(self):
        r = requests.get(self.url, headers=self.headers)
        return json.loads(r.text)

    def post_issue(self, task):
        print(task.name)
        body = {
            "title": task.name,
            "body": task.name,
            "assignees": ['victorsfleite'],
            "milestone": 3,
            "labels": [
                'k3rnelPan1cB0t'
            ]
        }

        r = requests.post(self.url, headers=self.headers, data=body)
        issue = json.loads(r.text)

        print(issue)
        return issue.url


if __name__ == '__main__':
    # github = GithubIssuesApi()
    # issues = github.get_issues()

    # print(json)
    pass
