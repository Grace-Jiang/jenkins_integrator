import json
import re
import requests
import dateutil.parser
from enum import Enum
from flask import Flask
from flask import request
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)


class Trigger_action(Enum):
    Pull_Request_Approved = 0
    Pull_Request_Merged = 1
    Manual_comment = 2
    UNKNOWN = 100


class Review(object):
    def __init__(self, review_json):
        self.reviewer = review_json.get("user").get("login")
        self.state = review_json.get("state")
        self.time = dateutil.parser.parse(review_json.get("submitted_at"))

    def __str__(self):
        return "Review Info: USER=" + self.reviewer + "\t STATE=" + self.state + "\t TIME:" + str(self.time)

    def is_early_than(self, another_review):
        return (self.time < another_review.time)

    def is_approved(self):
        if self.state.lower() == "approved":
            return True
        else:
            return False


class jenkins_req(object):

    PR_APPROVED_URL_BASE = u'http://ccmts-pipeline.cisco.com:8080/job/Pipeline1/buildWithParameters'
    PR_APPROVED_URL_BASE_dev = u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline1/buildWithParameters'
    PR_MERGED_URL = u'http://ccmts-pipeline.cisco.com:8080/job/Pipeline2_build/buildWithParameters'
    PR_MERGED_URL_dev = u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline2_build/buildWithParameters'
    COMMENT_MAGIC_WORDS = {
        'rerun p1 dev': {
            'URL': u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline1/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        },
        'rerun p2 dev': {
            'URL': u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline2_build/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        },
        'rerun p1': {
            'URL': u'http://ccmts-pipeline.cisco.com:8080/job/Pipeline1/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        },
        'rerun p2': {
            'URL': u'http://ccmts-pipeline.cisco.com:8080/job/Pipeline2_build/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        },
        'rerun dev': {
            'URL': u'http://ccmts-pipeline:8080/job/Development/job/Github_Pipeline1/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        }

    }



    def __init__(self, webhook_payload, is_production):
        self.webhook_payload = webhook_payload
        self.is_production = is_production
        self.trigger_event_type = self.get_trigger_type()
        print("Trigger Event Type: %s" % self.trigger_event_type)

    def get_base_url(self, event_type, is_production):
        if Trigger_action.Manual_comment == event_type:
            comment = self.webhook_payload.get("comment").get("body").strip()
            for key, _ in self.COMMENT_MAGIC_WORDS.items():
                if (comment == key):
                    return self.COMMENT_MAGIC_WORDS[key]['URL']

        if event_type == Trigger_action.Pull_Request_Approved:
            if is_production:
                return self.PR_APPROVED_URL_BASE
            else:
                return self.PR_APPROVED_URL_BASE_dev
        elif event_type == Trigger_action.Pull_Request_Merged:
            if is_production:
                return self.PR_MERGED_URL
            else:
                return self.PR_MERGED_URL_dev

    def get_pull_request_approver_list(self):
        self.reviews_url = self.PR_api_url + "/reviews"

        response = requests.get(self.reviews_url)
        if response.status_code != 200:
            raise Exception("Get PR review info fail! From URL:" + self.reviews_url)

        reviews_dict = {}
        approver_list = []
        for item in response.json():
            review = Review(item)
            if review.reviewer in reviews_dict:
                cur_review = reviews_dict[review.reviewer]
                if cur_review.is_early_than(review):
                    reviews_dict[review.reviewer] = review
            else:
                reviews_dict[review.reviewer] = review

        print(reviews_dict)
        for reviewer in reviews_dict:
            print(reviews_dict[reviewer])
            if reviews_dict[reviewer].is_approved():
                approver_list.append(reviewer)
        ret_str = ""
        for name in approver_list:
            ret_str += name + "%2C"

        return ret_str[:-3]

    def get_pull_request_paras(self, base_url, pr_api_url, pr_username, action):
        response = requests.get(pr_api_url)
        if response.status_code != 200:
            raise Exception("Get pull request info fail! From URL:" + self.PR_api_url)

        pull_data = response.json()
        paras = ""
        paras += base_url
        paras += u"?token=cisco"
        paras += u"&PULL_REQUEST_USER_NAME=" + pr_username
        paras += u"&PULL_REQUEST_FROM_REPO_NAME="
        paras += pull_data.get('base').get('repo').get('name')
        paras += u"&PULL_REQUEST_FROM_BRANCH="
        paras += pull_data.get('head').get('ref')
        paras += u"&PULL_REQUEST_FROM_HASH="
        paras += pull_data.get('head').get('sha')
        paras += u"&PULL_REQUEST_FROM_REPO_PROJECT_KEY="
        paras += pull_data.get('base').get('repo').get('full_name').split('/')[0]
        paras += u"&PULL_REQUEST_AUTHOR_NAME="
        paras += pull_data.get('user').get('login')
        paras += u"&PULL_REQUEST_ID="
        paras += str(pull_data.get('number'))
        paras += u"&PULL_REQUEST_TITLE="
        paras += pull_data.get('title').replace(' ', '+')
        paras += u"&PULL_REQUEST_TO_BRANCH="
        paras += pull_data.get('base').get('ref')
        paras += u"&PULL_REQUEST_ACTION=" + action
        paras += u"&PULL_REQUEST_REVIEWERS_APPROVED_NAME=" + self.get_pull_request_approver_list()
        paras += u"&PULL_REQUEST_URL=" + pull_data.get('html_url')

        return paras

    def get_pr_api_url(self):
        if self.trigger_event_type == Trigger_action.Manual_comment:
            self.PR_api_url = self.webhook_payload.get("issue").get("pull_request").get("url")
        else:
            self.PR_api_url = self.webhook_payload.get("pull_request").get("url")
        return self.PR_api_url

    def get_pr_user_name(self):
        if self.trigger_event_type == Trigger_action.Manual_comment:
            return self.webhook_payload.get("comment").get("user").get("login")
        elif self.trigger_event_type == Trigger_action.Pull_Request_Approved:
            return self.webhook_payload.get("review").get("user").get("login")
        elif self.trigger_event_type == Trigger_action.Pull_Request_Merged:
            return self.webhook_payload.get("pull_request").get("user").get("login")

    def get_action_name(self):
        if self.trigger_event_type == Trigger_action.Manual_comment:
            return u"BUTTON_TRIGGER"
        elif self.trigger_event_type == Trigger_action.Pull_Request_Approved:
            return u"APPROVED"
        elif self.trigger_event_type == Trigger_action.Pull_Request_Merged:
            return u"MERGED"


    def get_trigger_type(self):
        if self.webhook_payload.get("action") == "created":
            if self.webhook_payload.get("comment"):
                return Trigger_action.Manual_comment

        elif self.webhook_payload.get("action") == "submitted":
            if self.webhook_payload.get("review").get("state") == "approved":
                return Trigger_action.Pull_Request_Approved

        elif self.webhook_payload.get("action") == "closed":
            if self.webhook_payload.get("pull_request").get("merged") == True:
                return Trigger_action.Pull_Request_Merged

        return Trigger_action.UNKNOWN

    def gen_jenkins_request_url(self, is_production):

        webhook_paras = self.get_pull_request_paras(self.get_base_url(self.trigger_event_type, is_production),
                                                    self.get_pr_api_url(),
                                                    self.get_pr_user_name(),
                                                    self.get_action_name())
        self.jenkins_request_url = webhook_paras

    def do_jenkins_trigger(self):
        print("Jenkins Request URL: " + self.jenkins_request_url)

        res = requests.get(self.jenkins_request_url)
        print("Jenkins Request Response Status Code: %d " % res.status_code)


@app.route('/product', methods=['GET', 'POST'])
def webhook_handler_for_production():
    # with app.test_request_context():
    is_production = True
    print(request)
    if request.method == 'POST':
        try:
            webhook_payload = request.get_json()
            event = jenkins_req(webhook_payload, is_production)
            if event.trigger_event_type == Trigger_action.UNKNOWN:
                print("Unknow event type, not handle it")
            else:
                event.gen_jenkins_request_url(is_production)
                event.do_jenkins_trigger()
                if event.trigger_event_type != Trigger_action.Manual_comment:
                    event.gen_jenkins_request_url(False)
                    event.do_jenkins_trigger()

            return "Hello Jenkins!"

        except Exception as e:
            print(type(e).__name__ + ': ' + str(e))
            return (type(e).__name__ + ': ' + str(e))
    else:
        return "No! No GET!"

@app.route('/dev', methods=['GET', 'POST'])
def webhook_handler_for_production():
    # with app.test_request_context():
    is_production = False
    print(request)
    if request.method == 'POST':
        try:
            webhook_payload = request.get_json()
            event = jenkins_req(webhook_payload, is_production)
            if event.trigger_event_type == Trigger_action.UNKNOWN:
                print("Unknow event type, not handle it")
            else:
                event.gen_jenkins_request_url(is_production)
                event.do_jenkins_trigger()

            return "Hello Jenkins!"

        except Exception as e:
            print(type(e).__name__ + ': ' + str(e))
            return (type(e).__name__ + ': ' + str(e))
    else:
        return "No! No GET!"

if __name__ == '__main__':
    app.run()