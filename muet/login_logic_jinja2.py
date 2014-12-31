#
# Login Page logic using Twisted sessions
#
# Defines two functions used like before filters
#   current_user(reqeust) - return the username or ""
#   require_login(request) - go to login page if not logged in
#
# LoginResource()
# LogoutResource()
# IndexResource({ dict })
#
# pip install Jinja2
# python -m muet.login_logic_jinga2

import sys
import cgi
import random

from twisted.web.server import Site, NOT_DONE_YET
from twisted.web import static
from twisted.web.resource import Resource
from twisted.internet import reactor

from zope.interface import Interface, Attribute, implements
from twisted.web.server import Session
from twisted.python import log
from twisted.python.components import registerAdapter

from jinja2 import Template, Environment, PackageLoader
env = Environment(loader=PackageLoader('muet', 'templates')) # templates dir under muet package

#
# Access to session data is through a componentized interface
#

class ILoginSessionData(Interface):
    username = Attribute("the users name")
    csrf = Attribute("the csrf token")
    urlref = Attribute("where to go after login")

class LoginSessionData(object):
    implements(ILoginSessionData)

    def __init__(self, session):
        self.username = ""
        self.csrf = ""
        self.urlref = ""

registerAdapter(LoginSessionData, Session, ILoginSessionData)

#
# get the current user from the session
#

def current_user(request):
    session = request.getSession()
    login = ILoginSessionData(session)
    username = login.username
    print "CURRENT_USER:%s" % username
    return username

#
# guard a page and redirect if not logged in
#

def require_login(request):
    urlref = request.path
    print "REQURE_LOGIN:%s" % urlref

    session = request.getSession()
    login = ILoginSessionData(session)
    login.urlref = urlref

    print "DOING REDIRECT"
    request.redirect("/login")
    request.finish()
    return NOT_DONE_YET

#
# This is a very simple login page
#
    
class LoginPage(Resource):

    def __init__(self, db):
        self.db = db            # the database connection

        Resource.__init__(self)

    # unconditionally render the login page
    def render_GET(self, request):
        session = request.getSession()
        login = ILoginSessionData(session)
        login.csrf = str(random.randint(0, 1000000))

        ctx = {
            '_csrf' : login.csrf
            }
        template = env.get_template("login_greeting.html")

        return str(template.render(ctx))

    #
    # The following section implements the callback chain for login database query
    #

    def onResult(self, dbdata, request, username, password):

        log.msg("On Result:%s %s %s" % (dbdata, username, password))

        dbusername = ""
        dbpassword = ""

        success = False
        if len(dbdata) != 0:
            dbusername = dbdata[0][0]
            dbpassword = dbdata[0][1]

            if password == dbpassword:
                success = True

        if success:
            session = request.getSession()
            login = ILoginSessionData(session)
            login.username = username
            
            # retrieve from session and reset
            urlref = login.urlref
            login.urlref = ""

            log.msg("ON RESULT username, password, urlref:%s:%s:%s:" % (username, password, urlref))

            if urlref:
                request.redirect(urlref)
                request.finish()
            else:
                request.write("""<html><body>
                You are now logged in as %s
                </body></html>
                    """ % username)
                request.finish()

            pass

        else:
            request.redirect("/login")
            request.finish()

    #
    # Retrieve the username/password post data and start the database query
    #

    def render_POST(self, request):
        session = request.getSession()
        login = ILoginSessionData(session)

        # retrieve from post data
        username = cgi.escape(request.args["username"][0],)
        password = cgi.escape(request.args["password"][0],)
        csrf = cgi.escape(request.args["_csrf"][0],)

        log.msg("POST csrf:%s username:%s password:%s" % (csrf, username, password))

        if csrf != login.csrf:
            log.msg("CSRF ATTACK!")
            request.redirect("/login")
            request.finish()
            return NOT_DONE_YET
            

        # Run the query
        d = self.db.runQuery("SELECT username, password from Users WHERE username = ? LIMIT 1", (username,))
        d.addCallback(self.onResult, request, username, password)

        return NOT_DONE_YET


class LogoutPage(Resource):

    def render_GET(self, request):
        request.getSession().expire()

        ctx = {
            }
        template = env.get_template("logout_greeting.html")

        return str(template.render(ctx))

#
# Every site should have a main index.html
#  This is also the outline of how every page protects itself.
#

class IndexPage(Resource):
    
    isLeaf = True

    def __init__(self, ctx):
        self.ctx = ctx
        Resource.__init__(self)

    def render_GET(self, request):
        user = current_user(request)

        if not user:
            # this should store the current path, render the login page, and finally redirect back here
            return require_login(request)

        # add the user to the context
        ctx = self.ctx.copy()
        ctx['user'] = user

        template = env.get_template("index.html")
        return str(template.render(ctx))

#
# The root page usually wants to redirect to somewhere else
#

class RootPage(Resource):

    def render_GET(self, request):
        log.msg("ROOT REDIRECT")
        request.redirect("/index")
        request.finish()
        return NOT_DONE_YET


if __name__ == "__main__":

    log.startLogging(sys.stdout)
    from twisted.enterprise import adbapi
    connection = adbapi.ConnectionPool("sqlite3", "db/test.sqlite", check_same_thread=False)

    root = Resource()
    root.putChild("", RootPage())
    ctx = { }
    root.putChild("index", IndexPage(ctx))
    root.putChild("login", LoginPage(connection))
    root.putChild("logout", LogoutPage())

    root.putChild("javascript", static.File("javascript", "application/javascript"))
    factory = Site(root)
    reactor.listenTCP(8880, factory)
    reactor.run()
