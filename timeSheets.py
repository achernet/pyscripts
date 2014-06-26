
import requests
import urlparse
import re
from lxml.html import etree, HTMLParser
from datetime import datetime, timedelta
import dateutil.parser
import json

DEFAULT_LOGIN_PARAMS = {"client_height": 480,
                        "client_width": 640,
                        "flash_enabled": "false",
                        "language": "en_US"}


def parseNextLinkFromBrowserPage(loginResp):
    loginTree = etree.fromstring(loginResp.content, HTMLParser())
    loginTree.make_links_absolute(loginResp.url)
    nextLinkElems = loginTree.xpath("//input[@value=\'Continue to login\'][@onclick]")
    loginRespUrlDict = urlparse.urlparse(loginResp.url)._asdict()
    if not nextLinkElems:
        urlPath = "/desktop.do"
    else:
        urlPath = nextLinkElems[0].get("onclick").split("=")[-1].strip("\'")
    loginRespUrlDict["path"] = urlPath
    loginRespUrl = urlparse.ParseResult(**loginRespUrlDict).geturl()
    return loginRespUrl


def parseTimeSheetPage(tsResp):
    tsTree = etree.fromstring(tsResp.content, HTMLParser())
    headerNames = tsTree.xpath("//thead/tr/th/span[@class=\'clickable\']/text()")
    tsElems = tsTree.xpath("//tr[@class=\'evenRow\' or @class=\'oddRow\']")
    tsPages = []
    for elem in tsElems:
        values = elem.xpath("(td/nobr|td/nobr/a)/text()")
        tsDict = dict(zip(headerNames, values))
        for header, value in tsDict.items():
            if "/" in value:
                tsDict[header] = dateutil.parser.parse(value, ignoretz=True).date()
            if "." in value:
                tsDict[header] = float(value)
        tsPages.append(tsDict)
    return tsPages


def parseNumTimeSheetPages(tsResp):
    tsTree = etree.fromstring(tsResp.content, HTMLParser())
    pageElems = tsTree.xpath("//span[@class=\'pagingAreaLabel\']/text()")
    try:
        return int(pageElems[0].split(" ")[-1])
    except Exception as _:
        return 0


def doLogin(sess, username, password):
    loginPage = sess.get("https://www.fieldglass.net", headers={"user-agent": "Mozilla/5.0"})
    tree = etree.fromstring(loginPage.content, HTMLParser())
    inputElems = tree.xpath("//input[@name]")
    inputDict = {}
    for elem in inputElems:
        inputDict[elem.get("name")] = elem.value
    inputDict.update(DEFAULT_LOGIN_PARAMS)
    inputDict["username"] = username
    inputDict["password"] = password
    loginResp = sess.post("https://www.fieldglass.net/login.do",
                          data=inputDict,
                          headers=sess.headers,
                          cookies=sess.cookies)
    lastParsedUrl = urlparse.urlparse(loginResp.url)
    if lastParsedUrl.path == "/browser_version.jsp":
        nextLink = parseNextLinkFromBrowserPage(loginResp)
        return sess.get(nextLink)
    elif lastParsedUrl.path.endswith(".do"):
        return loginResp


def fetchTimeSheets(sess):
    timeSheetUrl = "https://www.fieldglass.net/time_sheet_list.do"
    timeSheetResp = sess.get(timeSheetUrl)
    sgjyMatch = re.search("[\"\']\&sgjy=(?P<value>[^\'\"]+)", timeSheetResp.content, flags=re.M | re.I)
    if not sgjyMatch:
        return []
    sgjyValue = sgjyMatch.group("value")
    numPages = parseNumTimeSheetPages(timeSheetResp)
    timeSheets = []
    for page in xrange(1, numPages + 1):
        timeSheetParams = {"sgjy": sgjyValue,
                           "filterStartDate": datetime(2011, 1, 1).strftime("%m/%d/%Y"),
                           "filterEndDate": (datetime.now() + timedelta(days=90)).strftime("%m/%d/%Y"),
                           "ttFilterButtonClicked": "false",
                           "timeSheet_worker_list_r": 20,
                           "timeSheet_worker_list_status_sch": "",
                           "timeSheet_worker_list_time_sheet_ref_sch": "",
                           "timeSheet_worker_list_refresh": "",
                           "timeSheet_worker_list_p": page}
        timeSheetFilterResp = sess.post(timeSheetUrl, data=timeSheetParams)
        nextTimeSheets = parseTimeSheetPage(timeSheetFilterResp)
        timeSheets.extend(nextTimeSheets)
    return timeSheets


def main(args):
    sess = requests.Session()
    loginResp = doLogin(sess, args[0], args[1])
    timeSheets = fetchTimeSheets(sess)
    with open("timesheets.json", "wb") as f:
        json.dump(timeSheets, f, indent=4)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
