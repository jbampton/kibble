# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import datetime
import hashlib
import re
import time

from kibble.scanners.utils import jsonapi

"""
This is a Kibble scanner plugin for Apache Pony Mail sources.
"""

title = "Scanner plugin for Apache Pony Mail"
version = "0.1.0"


def accepts(source):
    """ Test if source matches a Pony Mail archive """
    # If the source equals the plugin name, assume a yes
    if source["type"] == "ponymail":
        return True

    # If it's of type 'mail', check the URL
    if source["type"] == "mail":
        if re.match(r"(https?://.+)/list\.html\?(.+)@(.+)", source["sourceURL"]):
            return True

    # Default to not recognizing the source
    return False


def count_subs(struct, kids=0):
    """ Counts replies in a thread """
    if "children" in struct and len(struct["children"]) > 0:
        for child in struct["children"]:
            kids += 1
            kids += count_subs(child)
    return kids


def replied_to(emails, struct):
    my_list = {}
    for eml in struct:
        my_id = eml["tid"]
        if "children" in eml:
            for child in eml["children"]:
                my_list[child["tid"]] = my_id
                if len(child["children"]) > 0:
                    c_list = replied_to(emails, child["children"])
                    my_list.update(c_list)
    return my_list


def get_sender(email):
    sender = email["from"]
    m = re.match(r"(.+)\s*<(.+)>", email["from"], flags=re.UNICODE)
    if m:
        # name = m.group(1).replace('"', "").strip()
        sender = m.group(2)
    return sender


def scan(kibble_bit, source):
    # Validate URL first
    url = re.match(r"(https?://.+)/list\.html\?(.+)@(.+)", source["sourceURL"])
    if not url:
        kibble_bit.pprint(
            "Malformed or invalid Pony Mail URL passed to scanner: %s"
            % source["sourceURL"]
        )
        source["steps"]["mail"] = {
            "time": time.time(),
            "status": "Could not parse Pony Mail URL!",
            "running": False,
            "good": False,
        }
        kibble_bit.update_source(source)
        return

    # Pony Mail requires a UI cookie in order to work. Make sure we have one!
    cookie = None
    if "creds" in source and source["creds"]:
        cookie = source["creds"].get("cookie", None)
    if not cookie:
        kibble_bit.pprint(
            "Pony Mail instance at %s requires an authorized cookie, none found! Bailing."
            % source["sourceURL"]
        )
        source["steps"]["mail"] = {
            "time": time.time(),
            "status": "No authorized cookie found in source object.",
            "running": False,
            "good": False,
        }
        kibble_bit.update_source(source)
        return

    # Notify scanner and DB that this is valid and we've begun parsing
    kibble_bit.pprint("%s is a valid Pony Mail address, parsing" % source["sourceURL"])
    source["steps"]["mail"] = {
        "time": time.time(),
        "status": "Downloading Pony Mail statistics",
        "running": True,
        "good": True,
    }
    kibble_bit.update_source(source)

    # Get base URL, list and domain to parse
    u = url.group(1)
    l = url.group(2)
    d = url.group(3)

    # Get this month
    dt = time.gmtime(time.time())
    first_year = 1970
    year = dt[0]
    month = dt[1]
    if month <= 0:
        month += 12
        year -= 1
    months = 0

    # Hash for keeping records of who we know
    knowns = {}

    # While we have older archives, continue to parse
    while first_year <= year:
        statsurl = "%s/api/stats.lua?list=%s&domain=%s&d=%s" % (
            u,
            l,
            d,
            "%04u-%02u" % (year, month),
        )
        dhash = hashlib.sha224(
            ("%s %s" % (source["organisation"], statsurl)).encode(
                "ascii", errors="replace"
            )
        ).hexdigest()
        found = False
        if kibble_bit.exists("mailstats", dhash):
            found = True
        if months <= 1 or not found:  # Always parse this month's stats :)
            months += 1
            kibble_bit.pprint("Parsing %04u-%02u" % (year, month))
            kibble_bit.pprint(statsurl)
            pd = datetime.date(year, month, 1).timetuple()
            try:
                js = jsonapi.get(statsurl, cookie=cookie)
            except Exception as err:
                kibble_bit.pprint(f"Server error: {err}, skipping this month")
                month -= 1
                if month <= 0:
                    month += 12
                    year -= 1
                continue
            if "firstYear" in js:
                first_year = js["firstYear"]
                # print("First Year is %u" % firstYear)
            else:
                kibble_bit.pprint("JSON was missing fields, aborting!")
                break
            reply_list = replied_to(js["emails"], js["thread_struct"])
            topics = js["no_threads"]
            posters = {}
            no_posters = 0
            emails = len(js["emails"])
            top10 = []
            for eml in js["thread_struct"]:
                count = count_subs(eml, 0)
                subject = ""
                for reml in js["emails"]:
                    if reml["id"] == eml["tid"]:
                        subject = reml["subject"]
                        break
                if len(subject) > 0 and count > 0:
                    subject = re.sub(
                        r"^((re|fwd|aw|fw):\s*)+", "", subject, flags=re.IGNORECASE
                    )
                    subject = re.sub(r"[\r\n\t]+", "", subject, count=20)
                    emlid = hashlib.sha1(
                        subject.encode("ascii", errors="replace")
                    ).hexdigest()
                    top10.append([emlid, subject, count])
            i = 0
            for top in reversed(sorted(top10, key=lambda x: x[2])):
                i += 1
                if i > 10:
                    break
                kibble_bit.pprint("Found top 10: %s (%s emails)" % (top[1], top[2]))
                md = time.strftime("%Y/%m/%d %H:%M:%S", pd)
                mlhash = hashlib.sha224(
                    (
                        "%s%s%s%s"
                        % (top[0], source["sourceURL"], source["organisation"], md)
                    ).encode("ascii", errors="replace")
                ).hexdigest()  # one unique id per month per mail thread
                jst = {
                    "organisation": source["organisation"],
                    "sourceURL": source["sourceURL"],
                    "sourceID": source["sourceID"],
                    "date": md,
                    "emails": top[2],
                    "shash": top[0],
                    "subject": top[1],
                    "ts": time.mktime(pd),
                    "id": mlhash,
                }
                kibble_bit.index("mailtop", mlhash, jst)

            for email in js["emails"]:
                sender = email["from"]
                name = sender
                m = re.match(r"(.+)\s*<(.+)>", email["from"], flags=re.UNICODE)
                if m:
                    name = m.group(1).replace('"', "").strip()
                    sender = m.group(2)
                if not sender in posters:
                    posters[sender] = {"name": name, "email": sender}
                if not sender in knowns:
                    sid = hashlib.sha1(
                        ("%s%s" % (source["organisation"], sender)).encode(
                            "ascii", errors="replace"
                        )
                    ).hexdigest()
                    if kibble_bit.exists("person", sid):
                        knowns[sender] = True
                if not sender in knowns or name != sender:
                    kibble_bit.append(
                        "person",
                        {
                            "upsert": True,
                            "name": name,
                            "email": sender,
                            "organisation": source["organisation"],
                            "id": hashlib.sha1(
                                ("%s%s" % (source["organisation"], sender)).encode(
                                    "ascii", errors="replace"
                                )
                            ).hexdigest(),
                        },
                    )
                    knowns[sender] = True
                reply_to = None
                if email["id"] in reply_list:
                    rt = reply_list[email["id"]]
                    for eml in js["emails"]:
                        if eml["id"] == rt:
                            reply_to = get_sender(eml)
                            print("Email was reply to %s" % sender)
                jse = {
                    "organisation": source["organisation"],
                    "sourceURL": source["sourceURL"],
                    "sourceID": source["sourceID"],
                    "date": time.strftime(
                        "%Y/%m/%d %H:%M:%S", time.gmtime(email["epoch"])
                    ),
                    "sender": sender,
                    "address": sender,
                    "subject": email["subject"],
                    "replyto": reply_to,
                    "ts": email["epoch"],
                    "id": email["id"],
                    "upsert": True,
                }
                kibble_bit.append("email", jse)
            no_posters = len(posters)

            jso = {
                "organisation": source["organisation"],
                "sourceURL": source["sourceURL"],
                "sourceID": source["sourceID"],
                "date": time.strftime("%Y/%m/%d %H:%M:%S", pd),
                "authors": no_posters,
                "emails": emails,
                "topics": topics,
            }
            # print("Indexing as %s" % dhash)
            kibble_bit.index("mailstats", dhash, jso)
        month -= 1
        if month <= 0:
            month += 12
            year -= 1

    source["steps"]["mail"] = {
        "time": time.time(),
        "status": "Mail archives successfully scanned at "
        + time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(time.time())),
        "running": False,
        "good": True,
    }
    kibble_bit.update_source(source)
