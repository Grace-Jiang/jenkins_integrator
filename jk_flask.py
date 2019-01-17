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
    PR_APPROVED_URL_BASE = u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline1/buildWithParameters'

    COMMENT_MAGIC_WORDS = {
        'rerun p1': {
            'URL': u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline1/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        },
        'rerun p2': {
            'URL': u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline2_build/buildWithParameters',
            'NAME': u'Pipeline1-DEV'
        },
        'rerun dev': {
                    'URL': u'http://ccmts-pipeline:8080/job/Development/job/Github_Pipeline1/buildWithParameters',
                   'NAME': u'Pipeline1-DEV'
        }

    }
    PR_MERGED_URL = u'http://ccmts-pipeline.cisco.com:8080/job/Development/job/Pipeline2_build/buildWithParameters'

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

    def get_pull_request_paras(self):
        response = requests.get(self.PR_api_url)
        if response.status_code != 200:
            raise Exception("Get pull request info fail! From URL:" + self.PR_api_url)

        pull_data = response.json()
        paras = ""
        paras += u"&PULL_REQUEST_FROM_REPO_NAME="
        paras += pull_data.get('base').get('repo').get('name')
        paras += u"&PULL_REQUEST_FROM_BRANCH="
        paras += pull_data.get('head').get('ref')
        paras += u"&PULL_REQUEST_FROM_HASH="
        paras += pull_data.get('head').get('sha')
        paras += u"&PULL_REQUEST_FROM_REPO_PROJECT_KEY="
        paras += pull_data.get('base').get('repo').get('full_name').split('/')[0]
        paras += u"&PULL_REQUEST_AUTHOR_NAME="
        paras += pull_data.get('head').get('user').get('login')
        paras += u"&PULL_REQUEST_ID="
        paras += str(pull_data.get('number'))
        paras += u"&PULL_REQUEST_TITLE="
        paras += pull_data.get('title').replace(' ', '+')
        paras += u"&PULL_REQUEST_TO_BRANCH="
        paras += pull_data.get('base').get('ref')

        return paras

    def gen_jenkins_request_url__manual_comment(self):
        comment = self.webhook_payload.get("comment").get("body").strip()
        for key in self.COMMENT_MAGIC_WORDS.keys():
            if (comment == key):
                jenkins_request_url = self.COMMENT_MAGIC_WORDS[key]['URL']

                jenkins_request_url += u"?token=cisco"

                jenkins_request_url += u"&PULL_REQUEST_USER_NAME="
                jenkins_request_url += self.webhook_payload.get("comment").get("user").get("login")

                jenkins_request_url += u"&PULL_REQUEST_ACTION="
                jenkins_request_url += u"BUTTON_TRIGGER"

                jenkins_request_url += u"&PBUTTON_TRIGGER_TITLE="
                jenkins_request_url += self.COMMENT_MAGIC_WORDS[key]['NAME']

                jenkins_request_url += u"&PULL_REQUEST_REVIEWERS_APPROVED_NAME="

                self.PR_api_url = self.webhook_payload.get("issue").get("pull_request").get("url")
                self.PR_url = self.webhook_payload.get("issue").get("pull_request").get("html_url")

                jenkins_request_url += u"&PULL_REQUEST_URL="
                jenkins_request_url += self.PR_url

                jenkins_request_url += self.get_pull_request_paras()

                return jenkins_request_url

        raise Exception("No match pattern for comments")

    def gen_jenkins_request_url__pr_approved(self):

        self.PR_api_url = self.webhook_payload.get("pull_request").get("url")
        self.PR_url = self.webhook_payload.get("issue").get("pull_request").get("html_url")

        jenkins_request_url = self.PR_APPROVED_URL_BASE
        jenkins_request_url += u"?token=cisco"

        jenkins_request_url += u"&PULL_REQUEST_USER_NAME="
        jenkins_request_url += self.webhook_payload.get("review").get("user").get("login")

        ##########################
        jenkins_request_url += u"&PULL_REQUEST_ACTION="
        jenkins_request_url += u"APPROVED"

        jenkins_request_url += u"&PBUTTON_TRIGGER_TITLE="
        jenkins_request_url += ""

        jenkins_request_url += u"&PULL_REQUEST_URL="
        jenkins_request_url += self.PR_url

        jenkins_request_url += self.get_pull_request_paras()

        jenkins_request_url += u"&PULL_REQUEST_REVIEWERS_APPROVED_NAME="
        jenkins_request_url += self.get_pull_request_approver_list()

        return jenkins_request_url

    def gen_jenkins_request_url__pr_merged(self):
        self.notify()

        
        self.PR_api_url = self.webhook_payload.get("pull_request").get("url")
        self.PR_url = self.webhook_payload.get("issue").get("pull_request").get("html_url")

        jenkins_request_url = self.PR_MERGED_URL
        jenkins_request_url += u"?token=cisco"

        jenkins_request_url += u"&PULL_REQUEST_USER_NAME="
        jenkins_request_url += self.webhook_payload.get("pull_request").get("user").get("login")

        ##########################
        jenkins_request_url += u"&PULL_REQUEST_ACTION="
        jenkins_request_url += u"MERGED"

        jenkins_request_url += u"&PBUTTON_TRIGGER_TITLE="
        jenkins_request_url += ""

        jenkins_request_url += u"&PULL_REQUEST_URL="
        jenkins_request_url += self.PR_url

        jenkins_request_url += self.get_pull_request_paras()

        jenkins_request_url += u"&PULL_REQUEST_REVIEWERS_APPROVED_NAME="
        jenkins_request_url += self.get_pull_request_approver_list()

        return jenkins_request_url

    def notify(self):
        data = self.webhook_payload
        action = data.get("action")
        url = data.get("pull_request").get("html_url")
        body = data.get("pull_request").get("body")
        title = data.get("pull_request").get("title")
        uid = data.get("pull_request").get("user").get("login")
        ref = data.get("pull_request").get("head").get("ref")
        repo = data.get("pull_request").get("head").get("repo").get("full_name")

        msg = "<table><tr><td>" + url + "</td></tr>" \
              + "<tr><td> from </td><td>" + uid + "</td></tr>" \
              + "</table>"
        mail_title = repo + "/" + ref + "- Pull request: " + title
        send_mail("ruijiang@cisco.com", mail_title, msg, "")


    PARSE_WEBHOOK_PAYLOAD_CB = {
        Trigger_action.Pull_Request_Approved: gen_jenkins_request_url__pr_approved,
        Trigger_action.Pull_Request_Merged: gen_jenkins_request_url__pr_merged,
        Trigger_action.Manual_comment: gen_jenkins_request_url__manual_comment
    }

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

    def __init__(self, webhook_payload):
        self.webhook_payload = webhook_payload

        self.trigger_event_type = self.get_trigger_type()
        print("Trigger Event Type: %s" % self.trigger_event_type)

    def gen_jenkins_request_url(self):

        webhook_paras = self.PARSE_WEBHOOK_PAYLOAD_CB[self.trigger_event_type](self)

        self.jenkins_request_url = webhook_paras

    def do_jenkins_trigger(self):
        print("Jenkins Request URL: " + self.jenkins_request_url)

        res = requests.get(self.jenkins_request_url)
        print("Jenkins Request Response Status Code: %d " % res.status_code)


@app.route('/', methods=['GET', 'POST'])
def webhook_handler():
    # with app.test_request_context():
    print(request)
    if request.method == 'POST':
        #try:
            webhook_payload = request.get_json()
            event = jenkins_req(webhook_payload)
            event.gen_jenkins_request_url()
            event.do_jenkins_trigger()

            return "Hello Jenkins!"

        #except Exception as e:
        #    print(type(e).__name__ + ': ' + str(e))
        #    return (type(e).__name__ + ': ' + str(e))
    else:
        return "No! No GET!"

def send_mail(recipients, subject, html, text=""):
     #cc_recipients = "test@cisco.com"  # , yuayu@cisco.com"
     smtpserver = smtplib.SMTP("outbound.cisco.com")
     smtpserver.ehlo()
     smtpserver.ehlo()
     from_user = 'ccmts-pipeline@cisco.com'
     msg = MIMEMultipart('alternative')
     msg['Subject'] = subject
     msg['From'] = from_user
     msg['To'] = recipients
     #msg['Cc'] = cc_recipients
     part1 = MIMEText(text, 'plain')
     part2 = MIMEText(html, 'html')
     msg.attach(part1)
     msg.attach(part2)

     smtpserver.sendmail(from_user, recipients, msg.as_string())
     smtpserver.close()


if __name__ == '__main__':
    app.run()
