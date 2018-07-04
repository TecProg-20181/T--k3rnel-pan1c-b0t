#!/usr/bin/env python3

import json
import requests
import time
import urllib
import sqlalchemy
import db

from datetime import datetime
from db import Task
from github_api import GithubIssuesApi


TOKEN_FILE = "token.txt"

HELP = """
 /new NAME
 /todo ID
 /doing ID
 /done ID
 /delete ID
 /list
 /rename ID NAME
 /dependson ID ID...
 /duplicate ID
 /priority ID PRIORITY {low, medium, high}
 /priorities
 /duedate ID DATE {dd/mm/yyyy}
 /status
 /help
"""


def read_token():
    file = open(TOKEN_FILE, 'r')

    return file.readline()


def get_url(url):
    response = requests.get(url)
    content = response.content.decode("utf8")
    return content


def get_json_from_url(url):
    content = get_url(url)
    js = json.loads(content)
    return js


def get_updates(offset=None):
    url = URL + "getUpdates?timeout=100"
    if offset:
        url += "&offset={}".format(offset)
    js = get_json_from_url(url)
    return js


def send_message(text, chat_id, reply_markup=None):
    text = urllib.parse.quote_plus(text)
    url = URL + \
        "sendMessage?text={}&chat_id={}&parse_mode=Markdown".format(
            text, chat_id)
    if reply_markup:
        url += "&reply_markup={}".format(reply_markup)
    get_url(url)


def get_last_update_id(updates):
    update_ids = []
    for update in updates["result"]:
        update_ids.append(int(update["update_id"]))

    return max(update_ids)


def deps_text(task, chat, preceed=''):
    text = ''

    for i in range(len(task.dependencies.split(',')[:-1])):
        line = preceed
        query = db.session.query(Task).filter_by(
            id=int(task.dependencies.split(',')[:-1][i]), chat=chat)
        dep = query.one()

        status_icon = '\U0001F195'
        if dep.status == 'DOING':
            status_icon = '\U000023FA'
        elif dep.status == 'DONE':
            status_icon = '\U00002611'

        priority_icon = '\U0001F535'
        if dep.priority == 'medium':
            priority_icon = '\U00002622'
        if dep.priority == 'high':
            priority_icon = '\U0001F534'

        duedate_info = ''
        if dep.duedate:
            duedate = dep.duedate.strftime('%d/%m/%Y')
            icon = '\U0001F4C6'
            duedate_info = '{} {}'.format(icon, duedate)

        if i + 1 == len(task.dependencies.split(',')[:-1]):
            line += '└── [[{}]] {} {} {} {}\n'.format(
                dep.id, status_icon, priority_icon, dep.name, duedate_info)
            line += deps_text(dep, chat, preceed + '    ')
        else:
            line += '├── [[{}]] {} {} {} {}\n'.format(
                dep.id, status_icon, priority_icon, dep.name, duedate_info)
            line += deps_text(dep, chat, preceed + '│   ')

        text += line

    return text


def validate_date_format(date_string):
    try:
        datetime.strptime(date_string, '%d/%m/%Y')
        return True
    except ValueError:
        return False


def handle_status(ids_array, chat, status):
    message = ''
    for id in ids_array:
        if not id.isdigit():
            return "\U00002757 You *must inform* numeric value(s) only"
        else:
            task_id = int(id)
            query = db.session.query(Task).filter_by(id=task_id, chat=chat)
            try:
                task = query.one()
            except sqlalchemy.orm.exc.NoResultFound:
                message += "\U00002757 _404_ Task {} not found x.x\n".format(
                    task_id)
                continue
            task.status = status
            db.session.commit()
            message += "*{}* task [[{}]] {}\n".format(
                status, task.id, task.name)

    return message


def handle_updates(updates):
    for update in updates["result"]:
        if 'message' in update:
            message = update['message']
        elif 'edited_message' in update:
            message = update['edited_message']
        else:
            print('Can\'t process! {}'.format(update))
            return

        command = message["text"].split(" ", 1)[0]
        msg = ''
        if len(message["text"].split(" ", 1)) > 1:
            msg = message["text"].split(" ", 1)[1].strip()

        chat = message["chat"]["id"]

        print(command, msg, chat)

        if command == '/new':
            task = Task(chat=chat, name=msg, status='TODO',
                        dependencies='', parents='', priority='', github_id='')
            db.session.add(task)
            db.session.commit()
            send_message(
                "New task *TODO* [[{}]] {}".format(task.id, task.name), chat)

            query = db.session.query(
                Task).filter_by(id=task.id, chat=chat)
            try:
                taskObj = query.one()
            except sqlalchemy.orm.exc.NoResultFound:
                send_message(
                    "_404_ Task {} not found x.x".format(taskObj.id), chat)
                return

            github = GithubIssuesApi()
            issue = github.post_issue(taskObj)
            send_message(
                "Issue [#{}]({}) created on github repository!".format(issue['number'], issue['html_url']), chat)

            taskObj.github_id = issue['id']
            db.session.commit()

            return

        elif command == '/rename':
            text = ''
            if msg != '':
                if len(msg.split(' ', 1)) > 1:
                    text = msg.split(' ', 1)[1]
                msg = msg.split(' ', 1)[0]

            if not msg.isdigit():
                send_message("You must inform the task id", chat)
            else:
                task_id = int(msg)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    send_message(
                        "_404_ Task {} not found x.x".format(task_id), chat)
                    return

                if text == '':
                    send_message(
                        "You want to modify task {}, but you didn't provide any new text".format(task_id), chat)
                    return

                old_text = task.name
                task.name = text
                db.session.commit()
                send_message("Task {} redefined from {} to {}".format(
                    task_id, old_text, text), chat)

        elif command == '/duplicate':
            if not msg.isdigit():
                send_message("You must inform the task id", chat)
            else:
                task_id = int(msg)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    send_message(
                        "_404_ Task {} not found x.x".format(task_id), chat)
                    return

                dtask = Task(chat=task.chat, name=task.name, status=task.status, dependencies=task.dependencies,
                             parents=task.parents, priority=task.priority, duedate=task.duedate)
                db.session.add(dtask)

                for t in task.dependencies.split(',')[:-1]:
                    qy = db.session.query(Task).filter_by(id=int(t), chat=chat)
                    t = qy.one()
                    t.parents += '{},'.format(dtask.id)

                db.session.commit()
                send_message(
                    "New task *TODO* [[{}]] {}".format(dtask.id, dtask.name), chat)

        elif command == '/delete':
            if not msg.isdigit():
                send_message("You must inform the task id", chat)
            else:
                task_id = int(msg)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    send_message(
                        "_404_ Task {} not found x.x".format(task_id), chat)
                    return
                for t in task.dependencies.split(',')[:-1]:
                    qy = db.session.query(Task).filter_by(id=int(t), chat=chat)
                    t = qy.one()
                    t.parents = t.parents.replace('{},'.format(task.id), '')
                db.session.delete(task)
                db.session.commit()
                send_message("Task [[{}]] deleted".format(task_id), chat)

        elif command == '/todo':
            ids_array = msg.split(' ')

            if ids_array[0] == '':
                send_message(
                    "\U00002757 You *must inform* at least one id", chat)
                return

            message = handle_status(ids_array, chat, 'TODO')
            send_message(message, chat)

        elif command == '/doing':
            ids_array = msg.split(' ')

            if ids_array[0] == '':
                send_message(
                    "\U00002757 You *must inform* at least one id", chat)
                return

            message = handle_status(ids_array, chat, 'DOING')
            send_message(message, chat)

        elif command == '/done':
            ids_array = msg.split(' ')

            if ids_array[0] == '':
                send_message(
                    "\U00002757 You *must inform* at least one id", chat)
                return

            message = handle_status(ids_array, chat, 'DONE')
            send_message(message, chat)

        elif command == '/list':
            a = ''

            a += '\U0001F4CB Task List\n\n'
            query = db.session.query(Task).filter_by(
                parents='', chat=chat).order_by(Task.id)
            for task in query.all():
                status_icon = '\U0001F195'
                if task.status == 'DOING':
                    status_icon = '\U000023FA'
                if task.status == 'DONE':
                    status_icon = '\U00002611'

                priority_icon = '\U0001F535'
                if task.priority == 'medium':
                    priority_icon = '\U00002622'
                if task.priority == 'high':
                    priority_icon = '\U0001F534'

                duedate_info = ''
                if task.duedate:
                    duedate = task.duedate.strftime('%d/%m/%Y')
                    icon = '\U0001F4C6'
                    duedate_info = '{} {}'.format(icon, duedate)

                a += '[[{}]] {} {} {} {}\n'.format(task.id,
                                                   status_icon,
                                                   priority_icon,
                                                   task.name,
                                                   duedate_info)
                a += deps_text(task, chat)

            send_message(a, chat)

        elif command == '/dependson':
            text = ''
            if msg != '':
                if len(msg.split(' ', 1)) > 1:
                    text = msg.split(' ', 1)[1]
                msg = msg.split(' ', 1)[0]

            if not msg.isdigit():
                send_message("You must inform the task id", chat)
            else:
                task_id = int(msg)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    send_message(
                        "_404_ Task {} not found x.x".format(task_id), chat)
                    return

                if text == '':
                    for i in task.dependencies.split(',')[:-1]:
                        i = int(i)
                        q = db.session.query(Task).filter_by(id=i, chat=chat)
                        t = q.one()
                        t.parents = t.parents.replace(
                            '{},'.format(task.id), '')

                    task.dependencies = ''
                    send_message(
                        "Dependencies removed from task {}".format(task_id), chat)
                else:
                    for depid in text.split(' '):
                        if not depid.isdigit():
                            send_message(
                                "All dependencies ids must be numeric, and not {}".format(depid), chat)
                        else:
                            depid = int(depid)
                            query = db.session.query(
                                Task).filter_by(id=depid, chat=chat)
                            try:
                                taskdep = query.one()
                                parents_list = taskdep.dependencies.split(',')
                                if str(task.id) not in parents_list:
                                    taskdep.parents += str(task.id) + ','
                                    deplist = task.dependencies.split(',')
                                    if str(depid) not in deplist:
                                        task.dependencies += str(depid) + ','

                                    db.session.commit()
                                    send_message(
                                        "Task {} dependencies up to date".format(task_id), chat)
                                else:
                                    send_message(
                                        "\U00002757 Dependencies *can not be circular*!", chat)
                            except sqlalchemy.orm.exc.NoResultFound:
                                send_message(
                                    "_404_ Task {} not found x.x".format(depid), chat)
                                continue

        elif command == '/priority':
            text = ''
            if msg != '':
                if len(msg.split(' ', 1)) > 1:
                    text = msg.split(' ', 1)[1]
                msg = msg.split(' ', 1)[0]

            if not msg.isdigit():
                send_message("You must inform the task id", chat)
            else:
                task_id = int(msg)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    send_message(
                        "_404_ Task {} not found x.x".format(task_id), chat)
                    return

                if text == '':
                    task.priority = ''
                    send_message(
                        "_Cleared_ all priorities from task {}".format(task_id), chat)
                else:
                    if text.lower() not in ['high', 'medium', 'low']:
                        send_message(
                            "The priority *must be* one of the following: high, medium, low", chat)
                    else:
                        task.priority = text.lower()
                        priority_icon = '\U0001F535'
                        if task.priority == 'medium':
                            priority_icon = '\U00002622'
                        if task.priority == 'high':
                            priority_icon = '\U0001F534'
                        send_message(
                            "*Task {}* priority has priority *{}* ({})".format(task_id, text.lower(), priority_icon), chat)
                db.session.commit()

        elif command == '/priorities':
            a = ''

            a += '\U0001F4CC _Priorities_\n'

            query = db.session.query(Task).filter_by(
                priority='low', chat=chat).order_by(Task.id)
            a += '\n\U0001F535 *LOW*\n'
            for task in query.all():
                status_icon = '\U0001F195'
                if task.status == 'DOING':
                    status_icon = '\U000023FA'
                if task.status == 'DONE':
                    status_icon = '\U00002611'
                a += '[[{}]] {} {}\n'.format(task.id, status_icon, task.name)

            query = db.session.query(Task).filter_by(
                priority='medium', chat=chat).order_by(Task.id)
            a += '\n\U00002622 *MEDIUM*\n'
            for task in query.all():
                status_icon = '\U0001F195'
                if task.status == 'DOING':
                    status_icon = '\U000023FA'
                if task.status == 'DONE':
                    status_icon = '\U00002611'
                a += '[[{}]] {} {}\n'.format(task.id, status_icon, task.name)

            query = db.session.query(Task).filter_by(
                priority='high', chat=chat).order_by(Task.id)
            a += '\n\U0001F534 *HIGH*\n'
            for task in query.all():
                status_icon = '\U0001F195'
                if task.status == 'DOING':
                    status_icon = '\U000023FA'
                if task.status == 'DONE':
                    status_icon = '\U00002611'
                a += '[[{}]] {} {}\n'.format(task.id, status_icon, task.name)

            send_message(a, chat)

        elif command == '/duedate':
            text = ''
            if msg != '':
                if len(msg.split(' ', 1)) > 1:
                    text = msg.split(' ', 1)[1]
                msg = msg.split(' ', 1)[0]

            if not msg.isdigit():
                send_message("You must inform the task id", chat)
            else:
                task_id = int(msg)
                query = db.session.query(Task).filter_by(id=task_id, chat=chat)
                try:
                    task = query.one()
                except sqlalchemy.orm.exc.NoResultFound:
                    send_message(
                        "_404_ Task {} not found x.x".format(task_id), chat)
                    return

                if text == '':
                    task.duedate = None
                    send_message(
                        "_Cleared_ duedate from task {}".format(task_id), chat)
                else:
                    if not validate_date_format(text):
                        send_message(
                            "The duedate *must follow* the 'dd/mm/yyyy' pattern", chat)
                    else:
                        task.duedate = datetime.strptime(
                            text, '%d/%m/%Y').date()
                        print(task.duedate)
                        send_message(
                            "*Task {}* duedate set to *{}*".format(task_id, text), chat)
                db.session.commit()

        elif command == '/status':
            a = ''

            a += '\U0001F4DD _Status_\n'
            query = db.session.query(Task).filter_by(
                status='TODO', chat=chat).order_by(Task.id)
            a += '\n\U0001F195 *TODO*\n'
            for task in query.all():
                priority_icon = '\U0001F535'
                if task.priority == 'medium':
                    priority_icon = '\U00002622'
                if task.priority == 'high':
                    priority_icon = '\U0001F534'
                a += '[[{}]] {} {}\n'.format(task.id, priority_icon, task.name)
            query = db.session.query(Task).filter_by(
                status='DOING', chat=chat).order_by(Task.id)
            a += '\n\U000023FA *DOING*\n'
            for task in query.all():
                priority_icon = '\U0001F535'
                if task.priority == 'medium':
                    priority_icon = '\U00002622'
                if task.priority == 'high':
                    priority_icon = '\U0001F534'
                a += '[[{}]] {} {}\n'.format(task.id, priority_icon, task.name)
            query = db.session.query(Task).filter_by(
                status='DONE', chat=chat).order_by(Task.id)
            a += '\n\U00002611 *DONE*\n'
            for task in query.all():
                priority_icon = '\U0001F535'
                if task.priority == 'medium':
                    priority_icon = '\U00002622'
                if task.priority == 'high':
                    priority_icon = '\U0001F534'
                a += '[[{}]] {} {}\n'.format(task.id, priority_icon, task.name)

            send_message(a, chat)

        elif command == '/start':
            send_message("Welcome! Here is a list of things you can do.", chat)
            send_message(HELP, chat)
        elif command == '/help':
            send_message("Here is a list of things you can do.", chat)
            send_message(HELP, chat)
        else:
            send_message("I'm sorry dave. I'm afraid I can't do that.", chat)


def main():
    last_update_id = None

    while True:
        print("Updates")
        updates = get_updates(last_update_id)

        if len(updates["result"]) > 0:
            last_update_id = get_last_update_id(updates) + 1
            handle_updates(updates)

        time.sleep(0.5)


if __name__ == '__main__':
    TOKEN = read_token()
    URL = "https://api.telegram.org/bot{}/".format(TOKEN)

    main()
